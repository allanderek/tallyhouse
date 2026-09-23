"""Serialised, resumable backfill of the historical index from Common Crawl.

The live index gathers one period at a time and can afford to be a single
burst of work. The backfill cannot: it reads sixteen crawls, each costing a
few hundred range requests against a shared public archive, and the archive
will refuse us if we ask too fast — three of four crawls in an early probe
came back 403 when they were requested back to back.

So this is built as a command rather than a script. Three properties follow
from that, and each is load-bearing:

**Serialised.** One crawl at a time, with a delay between them. Nothing here
is urgent enough to justify hammering data.commoncrawl.org, and the whole
index is an argument about crawler etiquette.

**Resumable.** A crawl's manifest is written when that crawl completes, and a
crawl whose manifest already exists is skipped. Being refused therefore costs
one crawl rather than the whole run, and the fix is to run the same command
again.

**Survivable.** One crawl failing does not abort the rest. The run reports
what it got and what it did not, and the missing crawls are simply the ones
the next run will attempt.

Which crawls constitute the series is NOT an argument to this module — it is
`data/crawls/historical.json`. Adding or removing a crawl changes the
published series, which makes it methodology.
"""

import collections
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tallyhouse.commoncrawl import (
    IndexUnavailable,
    fetch_body,
    locate,
    robotstxt_parts,
    to_observation,
)
from tallyhouse.storage import (
    manifest_path,
    read_manifest,
    store_body,
    write_manifest,
)


def load_crawls(root: Path, name: str = "historical") -> list[dict]:
    """The crawl series: which crawls, and what period each one stands for."""
    document = json.loads((root / "crawls" / f"{name}.json").read_text())
    crawls = document["crawls"]
    periods = [entry["period"] for entry in crawls]
    if len(set(periods)) != len(periods):
        raise ValueError(
            f"crawl series {name} maps two crawls to the same period; each "
            f"period is one published point, so the mapping must be injective"
        )
    return crawls


def outstanding(root: Path, crawls: list[dict]) -> list[dict]:
    """The crawls not yet collected — what a resumed run would actually do."""
    return [c for c in crawls if not manifest_path(root, c["period"]).exists()]


def collect_crawl(
    root: Path,
    crawl: str,
    period: str,
    domains: list[str],
    *,
    connection,
    parts: list[str],
    collector_version: str,
    fetch=fetch_body,
    workers: int = 12,
    body_attempts: int = 4,
    body_backoff: int = 2,
    sleep=None,
) -> dict:
    """Locate and fetch one crawl's robots.txt for the whole panel.

    The manifest is written once, at the end. A crawl is therefore either
    collected or not collected, never half — which is what lets the next run
    decide what to do by asking whether the file exists.
    """
    sleep = time.sleep if sleep is None else sleep
    located = locate(connection, parts, domains)

    def body_for(domain: str):
        record = located.get(domain)
        if record is None or record["status"] != "200":
            return domain, record, None
        # Range requests get the same patience as the index query. Without it a
        # single transient 503 loses a body, and a lost body is not a neutral
        # gap: it was being recorded as a readable file that blocks nobody.
        # 124 of 2024-05's 380 captures were lost this way on the first run.
        for attempt in range(1, body_attempts + 1):
            try:
                return domain, record, fetch(record)
            except Exception:
                if attempt == body_attempts:
                    # Still nothing. The observation stays, with no body, and
                    # to_observation records it as BodyUnavailable rather than
                    # Fetched: "we could not read it" is a different claim from
                    # "it allowed everyone".
                    return domain, record, None
                sleep(body_backoff * attempt)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(body_for, domains))

    records = []
    for domain, record, body in results:
        observation = to_observation(domain, crawl, record, body)
        # `is not None`, not falsiness: an empty robots.txt is a real file that
        # really does allow everyone, and storing it under the hash of b"" is
        # what keeps it distinguishable from a body we never got.
        observation["sha256"] = store_body(root, body) if body is not None else None
        observation.pop("body")
        observation["collector_version"] = collector_version
        records.append(observation)

    write_manifest(root, period, records, collector_version=collector_version)
    return {
        "crawl": crawl,
        "period": period,
        "status": "collected",
        "located": len(located),
        "outcomes": dict(collections.Counter(r["outcome"] for r in records)),
    }


def parts_with_retry(
    crawl: str,
    *,
    parts_for=robotstxt_parts,
    sleep=None,
    attempts: int = 3,
    backoff: int = 30,
) -> list[str]:
    """Read a crawl's index paths, backing off when the archive refuses us.

    A 403 here is the archive asking us to slow down, not a permanent answer,
    so waiting is the correct response and retrying immediately is not.
    """
    sleep = time.sleep if sleep is None else sleep
    for attempt in range(1, attempts + 1):
        try:
            return parts_for(crawl)
        except IndexUnavailable:
            if attempt == attempts:
                raise
            sleep(backoff * attempt)
    raise AssertionError("unreachable")


def backfill(
    root: Path,
    crawls: list[dict],
    domains: list[str],
    *,
    connect,
    collector_version: str,
    parts_for=robotstxt_parts,
    fetch=fetch_body,
    sleep=None,
    delay: int = 60,
    workers: int = 12,
    crawl_attempts: int = 2,
    log=print,
) -> list[dict]:
    """Collect every outstanding crawl in the series, one at a time."""
    # Resolved here rather than as a default argument: a default binds
    # time.sleep at import, which silently ignores a patched clock and makes a
    # test of the retry path wait for real.
    sleep = time.sleep if sleep is None else sleep
    results = []
    todo = {c["period"] for c in outstanding(root, crawls)}
    attempted = False
    for entry in crawls:
        crawl, period = entry["crawl"], entry["period"]
        if period not in todo:
            results.append({**entry, "status": "skipped"})
            log(f"{crawl} -> {period}: already collected, skipping")
            continue
        # Between attempts only. A resumed run that skips eight collected
        # crawls should not also sit through eight delays for them.
        if attempted:
            sleep(delay)
        attempted = True
        log(f"{crawl} -> {period}: starting")
        try:
            parts = parts_with_retry(crawl, parts_for=parts_for, sleep=sleep)
            # Locating a crawl is four minutes of querying, and a single
            # transient refusal near the end would otherwise discard all of it.
            # Retrying the whole crawl is expensive but rare, and a hole in the
            # series costs more than the repeated query does.
            for attempt in range(1, crawl_attempts + 1):
                try:
                    result = collect_crawl(
                        root, crawl, period, domains,
                        connection=connect(), parts=parts,
                        collector_version=collector_version, fetch=fetch,
                        workers=workers, sleep=sleep,
                    )
                    break
                except Exception as exc:
                    if attempt == crawl_attempts:
                        raise
                    log(f"{crawl} -> {period}: attempt {attempt} failed ({exc}), retrying")
                    sleep(delay)
        except Exception as exc:
            # Keep going. The series is sixteen independent readings; losing
            # one is a gap the next run fills, while aborting loses the ones
            # that would have worked.
            result = {**entry, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            log(f"{crawl} -> {period}: FAILED {result['error']}")
        else:
            log(f"{crawl} -> {period}: {result['outcomes']}")
        results.append(result)
    return results


def repair_period(
    root: Path,
    period: str,
    *,
    collector_version: str,
    fetch=fetch_body,
    sleep=None,
    workers: int = 8,
    attempts: int = 6,
    backoff: int = 5,
) -> dict:
    """Re-fetch the bodies of observations recorded BodyUnavailable.

    The archive refuses us in bursts, and a burst can cost a whole crawl's
    bodies: 2023-03 came back with 237 of its 367 captures unread while every
    other crawl in the series was clean. Re-running the collector would work,
    but it would also re-run the four-minute index query to rediscover
    coordinates already written down.

    So this repairs from the manifest instead, using the WARC filename, offset
    and length recorded on each observation. Only observations that failed are
    touched; a Fetched record is never re-read, so a repair cannot change
    evidence that was already good. Patience is higher than the collector's,
    because reaching here means the archive has already refused us once.
    """
    sleep = time.sleep if sleep is None else sleep
    records = read_manifest(root, period)
    pending = [
        r for r in records
        if r["outcome"] == "BodyUnavailable" and r.get("warc_filename")
    ]

    def repair(record: dict):
        coordinates = {
            "filename": record["warc_filename"],
            "offset": record["warc_offset"],
            "length": record["warc_length"],
        }
        for attempt in range(1, attempts + 1):
            try:
                return record, fetch(coordinates)
            except Exception:
                if attempt == attempts:
                    return record, None
                sleep(backoff * attempt)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(repair, pending))

    repaired = 0
    for record, body in results:
        if body is None:
            continue
        record["outcome"] = "Fetched"
        record["sha256"] = store_body(root, body)
        record["bytes"] = len(body)
        # The body in hand was fetched by THIS commit, so this is the commit a
        # stranger needs to reproduce the observation, not the one that failed
        # to fetch it.
        record["collector_version"] = collector_version
        repaired += 1

    if repaired:
        write_manifest(root, period, records, collector_version=collector_version)
    return {"period": period, "attempted": len(pending), "repaired": repaired}
