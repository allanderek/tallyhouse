import gzip
import io
from datetime import datetime

import duckdb
import pytest

from tallyhouse.commoncrawl import (
    IndexUnavailable,
    fetch_body,
    locate,
    robotstxt_parts,
    to_observation,
)


class FakeResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def opener_for(items):
    calls = {"n": 0}
    def opener(req, timeout=None):
        item = items[min(calls["n"], len(items) - 1)]
        calls["n"] += 1
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)
    opener.calls = calls
    return opener


def make_parquet(tmp_path, rows):
    """A local Parquet with the columnar index's schema, so the SQL is tested."""
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE idx (
          url_surtkey VARCHAR, url VARCHAR, url_host_name VARCHAR,
          url_host_registered_domain VARCHAR, url_path VARCHAR,
          fetch_time TIMESTAMP, fetch_status INTEGER,
          warc_filename VARCHAR, warc_record_offset BIGINT, warc_record_length BIGINT
        )""")
    for r in rows:
        con.execute("INSERT INTO idx VALUES (?,?,?,?,?,?,?,?,?,?)", [
            "k", r["url"], r["host"], r["dom"], r.get("path", "/robots.txt"),
            datetime.fromisoformat(r["time"]), r["status"], "w.warc.gz", 0, 10,
        ])
    path = tmp_path / "part.parquet"
    con.execute(f"COPY idx TO '{path}' (FORMAT PARQUET)")
    return str(path)


def row(dom, status, time, host=None, url=None, path="/robots.txt"):
    host = host or dom
    return {"dom": dom, "host": host, "status": status, "time": time,
            "url": url or f"https://{host}/robots.txt", "path": path}


def test_paths_are_filtered_to_the_robotstxt_subset(tmp_path):
    listing = gzip.compress(b"a/subset=warc/p.parquet\nb/subset=robotstxt/q.parquet\n")
    parts = robotstxt_parts("CC-X", opener=opener_for([listing]))
    assert len(parts) == 1 and "subset=robotstxt" in parts[0]


def test_paths_are_cached_so_a_backfill_refetches_nothing(tmp_path):
    listing = gzip.compress(b"b/subset=robotstxt/q.parquet\n")
    opener = opener_for([listing])
    robotstxt_parts("CC-X", cache=tmp_path, opener=opener)
    robotstxt_parts("CC-X", cache=tmp_path, opener=opener)
    assert opener.calls["n"] == 1


def test_unreachable_index_paths_fail_loudly(tmp_path):
    with pytest.raises(IndexUnavailable):
        robotstxt_parts("CC-X", opener=opener_for([OSError("503")]))


def test_a_200_is_preferred_over_a_newer_redirect(tmp_path):
    # The apex 301 is newer, but the readable file is what we want.
    parts = [make_parquet(tmp_path, [
        row("a.com", 301, "2026-07-10T10:00:00"),
        row("a.com", 200, "2026-07-10T09:00:00", host="www.a.com"),
    ])]
    got = locate(duckdb.connect(), parts, ["a.com"])
    assert got["a.com"]["status"] == "200"
    assert got["a.com"]["url"] == "https://www.a.com/robots.txt"


def test_a_conclusive_absence_beats_a_redirect(tmp_path):
    parts = [make_parquet(tmp_path, [
        row("a.com", 301, "2026-07-10T10:00:00"),
        row("a.com", 404, "2026-07-10T09:00:00"),
    ])]
    assert locate(duckdb.connect(), parts, ["a.com"])["a.com"]["status"] == "404"


def test_the_newest_is_chosen_within_a_class(tmp_path):
    parts = [make_parquet(tmp_path, [
        row("a.com", 200, "2026-07-10T09:00:00", url="https://a.com/old"),
        row("a.com", 200, "2026-07-10T22:00:00", url="https://a.com/new"),
    ])]
    assert locate(duckdb.connect(), parts, ["a.com"])["a.com"]["url"].endswith("/new")


def test_only_apex_and_www_hosts_count(tmp_path):
    # en.wikipedia.org shares a registered domain but is a different site's
    # policy; the live collector would never fetch it, so neither does this.
    parts = [make_parquet(tmp_path, [
        row("wikipedia.org", 200, "2026-07-10T09:00:00", host="en.wikipedia.org"),
    ])]
    assert locate(duckdb.connect(), parts, ["wikipedia.org"]) == {}


def test_one_row_per_domain(tmp_path):
    parts = [make_parquet(tmp_path, [
        row("a.com", 200, "2026-07-10T09:00:00"),
        row("a.com", 200, "2026-07-10T10:00:00"),
        row("b.com", 200, "2026-07-10T09:00:00"),
    ])]
    got = locate(duckdb.connect(), parts, ["a.com", "b.com"])
    assert sorted(got) == ["a.com", "b.com"]


def test_non_robots_paths_are_ignored(tmp_path):
    parts = [make_parquet(tmp_path, [row("a.com", 200, "2026-07-10T09:00:00", path="/")]) ]
    assert locate(duckdb.connect(), parts, ["a.com"]) == {}


def test_fetch_body_extracts_from_the_warc():
    warc = gzip.compress(b"WARC/1.0\r\nWARC-Type: response\r\n\r\n"
                         b"HTTP/1.1 200 OK\r\n\r\nUser-agent: *\nDisallow: /\n")
    body = fetch_body({"filename": "f", "offset": 0, "length": 10},
                      opener=opener_for([warc]))
    assert body == b"User-agent: *\nDisallow: /\n"


def test_a_domain_absent_from_the_crawl_is_not_in_crawl():
    obs = to_observation("a.com", "CC-X", None, None)
    # Absence of evidence about the CRAWL, not about the site.
    assert obs["outcome"] == "NotInCrawl" and obs["body"] is None


def test_outcomes_map_to_the_live_vocabulary():
    def out(status):
        rec = {"url": "u", "status": status, "fetch_time": "2026-07-10T09:00:00Z"}
        return to_observation("a.com", "CC-X", rec, b"x" if status == "200" else None)["outcome"]
    assert out("200") == "Fetched"
    assert out("404") == "NoRobotsTxt"
    assert out("301") == "TransportError"
    assert out("403") == "ServerError"


def test_fetched_at_is_when_common_crawl_saw_it():
    rec = {"url": "u", "status": "200", "fetch_time": "2023-01-26T21:09:53Z"}
    obs = to_observation("a.com", "CC-X", rec, b"body")
    assert obs["fetched_at"] == "2023-01-26T21:09:53Z"
    assert obs["crawl"] == "CC-X"
