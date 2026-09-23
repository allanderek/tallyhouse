"""Tests for the resumable Common Crawl backfill.

Every outward call is injected, so the suite never touches the network.
"""

import json
from pathlib import Path

import pytest

from tallyhouse.backfill import (
    backfill,
    collect_crawl,
    load_crawls,
    outstanding,
    parts_with_retry,
)
from tallyhouse.commoncrawl import IndexUnavailable
from tallyhouse.storage import load_body, manifest_path, read_manifest

CRAWLS = [
    {"crawl": "CC-MAIN-2023-06", "period": "2023-01", "name": "January 2023"},
    {"crawl": "CC-MAIN-2023-40", "period": "2023-09", "name": "September 2023"},
]


def write_series(root: Path, crawls=CRAWLS, name="historical") -> Path:
    path = root / "crawls" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"crawls": crawls}))
    return path


class FakeConnection:
    """Stands in for DuckDB: returns a fixed capture per domain."""

    def __init__(self, located: dict[str, dict]):
        self.located = located
        self.queries = 0

    def execute(self, query):
        self.queries += 1
        self.query = query
        return self

    def fetchall(self):
        class When:
            def strftime(self, fmt):
                return "2023-01-26T21:10:16Z"

        return [
            (domain, r["url"], r["status"], r["filename"], r["offset"], r["length"], When())
            for domain, r in self.located.items()
        ]


def capture(domain, status="200"):
    return {
        "url": f"https://{domain}/robots.txt",
        "status": status,
        "filename": "crawl-data/warc/part.warc.gz",
        "offset": 0,
        "length": 100,
    }


def test_load_crawls_reads_the_series(tmp_path):
    write_series(tmp_path)
    assert [c["crawl"] for c in load_crawls(tmp_path)] == [
        "CC-MAIN-2023-06",
        "CC-MAIN-2023-40",
    ]


def test_load_crawls_rejects_two_crawls_for_one_period(tmp_path):
    # Each period is one published point. Two crawls mapping to the same one
    # would silently make the second overwrite the first's evidence.
    write_series(
        tmp_path,
        [
            {"crawl": "CC-MAIN-2023-06", "period": "2023-01"},
            {"crawl": "CC-MAIN-2023-07", "period": "2023-01"},
        ],
    )
    with pytest.raises(ValueError, match="same period"):
        load_crawls(tmp_path)


def test_outstanding_excludes_crawls_already_collected(tmp_path):
    path = manifest_path(tmp_path, "2023-01")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"period": "2023-01", "observations": []}))
    assert [c["crawl"] for c in outstanding(tmp_path, CRAWLS)] == ["CC-MAIN-2023-40"]


def test_collect_crawl_writes_a_manifest_with_bodies(tmp_path):
    connection = FakeConnection({"a.com": capture("a.com")})
    result = collect_crawl(
        tmp_path, "CC-MAIN-2023-06", "2023-01", ["a.com", "b.com"],
        connection=connection, parts=["s3://part-0.parquet"],
        collector_version="abc1234", fetch=lambda record: b"User-agent: GPTBot\nDisallow: /\n",
    )
    assert result["outcomes"] == {"Fetched": 1, "NotInCrawl": 1}
    records = {r["domain"]: r for r in read_manifest(tmp_path, "2023-01")}
    assert records["a.com"]["outcome"] == "Fetched"
    assert records["a.com"]["crawl"] == "CC-MAIN-2023-06"
    assert records["a.com"]["collector_version"] == "abc1234"
    assert load_body(tmp_path, records["a.com"]["sha256"]) == b"User-agent: GPTBot\nDisallow: /\n"
    # A domain absent from the crawl is recorded as absent, not dropped: the
    # denominator has to know the difference.
    assert records["b.com"]["outcome"] == "NotInCrawl"
    assert records["b.com"]["sha256"] is None


def test_collect_crawl_keeps_going_when_one_body_cannot_be_fetched(tmp_path):
    def fetch(record):
        if "b.com" in record["url"]:
            raise OSError("range request failed")
        return b"User-agent: *\nAllow: /\n"

    connection = FakeConnection({"a.com": capture("a.com"), "b.com": capture("b.com")})
    collect_crawl(
        tmp_path, "CC-MAIN-2023-06", "2023-01", ["a.com", "b.com"],
        connection=connection, parts=["p"], collector_version="abc1234", fetch=fetch,
    )
    records = {r["domain"]: r for r in read_manifest(tmp_path, "2023-01")}
    assert records["a.com"]["sha256"] is not None
    # The index promised a capture we could not read. That is not the same as
    # the file being absent, and derive must see no body rather than an empty one.
    assert records["b.com"]["sha256"] is None


def test_collect_crawl_writes_nothing_when_it_fails_partway(tmp_path):
    # Atomicity is what makes resumption safe: the next run decides by asking
    # whether the manifest exists, so a half-collected crawl must not leave one.
    class Exploding(FakeConnection):
        def fetchall(self):
            raise RuntimeError("index went away")

    with pytest.raises(RuntimeError):
        collect_crawl(
            tmp_path, "CC-MAIN-2023-06", "2023-01", ["a.com"],
            connection=Exploding({}), parts=["p"], collector_version="abc1234",
        )
    assert not manifest_path(tmp_path, "2023-01").exists()


def test_parts_with_retry_backs_off_then_succeeds():
    calls, slept = [], []

    def parts_for(crawl):
        calls.append(crawl)
        if len(calls) < 3:
            raise IndexUnavailable("403")
        return ["p"]

    assert parts_with_retry("CC", parts_for=parts_for, sleep=slept.append, backoff=30) == ["p"]
    assert slept == [30, 60]


def test_parts_with_retry_gives_up_after_the_last_attempt():
    def parts_for(crawl):
        raise IndexUnavailable("403")

    with pytest.raises(IndexUnavailable):
        parts_with_retry("CC", parts_for=parts_for, sleep=lambda s: None, attempts=2)


def run_backfill(root, crawls=CRAWLS, **kwargs):
    slept = []
    kwargs.setdefault("parts_for", lambda crawl: ["p"])
    kwargs.setdefault("connect", lambda: FakeConnection({"a.com": capture("a.com")}))
    kwargs.setdefault("fetch", lambda record: b"User-agent: *\nDisallow:\n")
    results = backfill(
        root, crawls, ["a.com"],
        collector_version="abc1234", sleep=slept.append, delay=60,
        log=lambda *a: None, **kwargs,
    )
    return results, slept


def test_backfill_collects_every_crawl_in_the_series(tmp_path):
    results, _ = run_backfill(tmp_path)
    assert [r["status"] for r in results] == ["collected", "collected"]
    assert read_manifest(tmp_path, "2023-01") and read_manifest(tmp_path, "2023-09")


def test_backfill_delays_between_crawls(tmp_path):
    _, slept = run_backfill(tmp_path)
    assert slept == [60]


def test_backfill_skips_crawls_already_collected_and_does_not_delay_for_them(tmp_path):
    run_backfill(tmp_path, [CRAWLS[0]])
    results, slept = run_backfill(tmp_path)
    assert [r["status"] for r in results] == ["skipped", "collected"]
    # One crawl left to do, so no delay: a resumed run must not pay the
    # politeness cost of work it is not doing.
    assert slept == []


def test_backfill_survives_one_crawl_failing(tmp_path):
    def parts_for(crawl):
        if crawl == "CC-MAIN-2023-06":
            raise IndexUnavailable("403 Forbidden")
        return ["p"]

    results, _ = run_backfill(tmp_path, parts_for=parts_for)
    assert [r["status"] for r in results] == ["failed", "collected"]
    assert "IndexUnavailable" in results[0]["error"]
    # The surviving crawl is on disk, and the failed one is simply outstanding.
    assert manifest_path(tmp_path, "2023-09").exists()
    assert [c["crawl"] for c in outstanding(tmp_path, CRAWLS)] == ["CC-MAIN-2023-06"]
