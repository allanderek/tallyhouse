"""Orchestrates a collection run across the whole panel.

Concurrency is capped deliberately: the index is about crawler etiquette, so
the crawler that produces it must be beyond reproach. One request per domain
per week is negligible load, but a burst of a thousand simultaneous
connections is not a good look.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import httpx

from tallyhouse.collect import fetch_domain
from tallyhouse.constants import CONCLUSIVE_OUTCOMES
from tallyhouse.storage import manifest_path, read_manifest, store_body, write_manifest


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def collect_panel(
    root: Path,
    period: str,
    domains: list[str],
    *,
    client: httpx.AsyncClient,
    collector_version: str,
    concurrency: int = 8,
    attempts: int = 3,
) -> list[dict]:
    # A re-run for a period already collected MERGES into the existing manifest:
    # every conclusive observation is kept exactly as recorded, and only the
    # domains we learned nothing about are re-attempted. This is what actually
    # spans the 72-hour collection window of spec 5.1/6.1 — cron re-runs collect
    # during the window and coverage improves — rather than one process sleeping
    # for three days. Overwriting instead would destroy the raw evidence behind
    # an already-derived number and break the promise that a stranger can clone
    # the repo and re-derive every figure.
    existing = {}
    if manifest_path(root, period).exists():
        existing = {r["domain"]: r for r in read_manifest(root, period)}

    settled = {
        domain: record
        for domain, record in existing.items()
        if record.get("outcome") in CONCLUSIVE_OUTCOMES
    }
    pending = [d for d in domains if d not in settled]

    semaphore = asyncio.Semaphore(concurrency)

    async def one(domain: str) -> dict:
        async with semaphore:
            try:
                return await fetch_domain(client, domain, attempts=attempts)
            except Exception:
                # Catch unexpected exceptions and return a TransportError outcome
                # rather than aborting the entire run. This ensures one bad domain
                # doesn't destroy the whole weekly collection.
                return {
                    "domain": domain,
                    "outcome": "TransportError",
                    "http_status": None,
                    "final_url": None,
                    "content_type": None,
                    "bytes": None,
                    "body": None,
                    "fetched_at": _now(),
                    "attempts": attempts,
                }

    results = await asyncio.gather(*(one(d) for d in pending))

    merged = dict(existing)
    for result in results:
        record = dict(result)
        body = record.pop("body")
        record["sha256"] = store_body(root, body) if body is not None else None
        # Stamp provenance on the records THIS run fetched. Records carried
        # over from a previous run keep the version that actually produced
        # them: a period collected across two commits is evidence from two
        # commits, and a single period-level stamp would silently attribute
        # all of it to whichever run happened to write the manifest last.
        record["collector_version"] = collector_version
        merged[record["domain"]] = record

    records = list(merged.values())
    write_manifest(root, period, records, collector_version=collector_version)
    return sorted(records, key=lambda r: r["domain"])
