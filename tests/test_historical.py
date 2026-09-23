"""Tests for publishing the historical index.

What is tested here is only what makes the historical index differ from the
live one: a separate index_id, no provisional flag, and a change row that
refuses to span a gap. Everything else is the live index's machinery, tested
against the live index.
"""

from tallyhouse.historical import CHANGE_SERIES, INDEX_ID, publish_series
from tallyhouse.ledger import read_rows
from tallyhouse.storage import store_body, write_manifest

CRAWLS = [
    {"crawl": "CC-MAIN-2023-06", "period": "2023-01"},
    {"crawl": "CC-MAIN-2023-14", "period": "2023-03"},
    {"crawl": "CC-MAIN-2023-23", "period": "2023-05"},
]
META = {"methodology_version": "agents=2;protego=0.5.0", "computed_at": "2026-09-23T00:00:00Z"}


def seed(root, period, blocked: list[str], total: int = 10, version="commoncrawl"):
    """One period's manifest: `blocked` domains disallow GPTBot, the rest allow."""
    records = []
    for i in range(total):
        domain = f"d{i}.com"
        body = (
            "User-agent: GPTBot\nDisallow: /\n"
            if domain in blocked
            else "User-agent: *\nAllow: /\n"
        )
        records.append({
            "domain": domain, "outcome": "Fetched", "http_status": 200,
            "final_url": f"https://{domain}/robots.txt", "content_type": None,
            "bytes": len(body), "sha256": store_body(root, body.encode()),
            "fetched_at": "2023-01-26T21:10:16Z", "attempts": 1,
        })
    write_manifest(root, period, records, collector_version=version)


def published(root, ledger="prints.csv"):
    return [r for r in read_rows(root / ledger) if r["index_id"] == INDEX_ID]


def test_publishes_under_its_own_index_id(tmp_path):
    # The levels are not comparable with the live index. Sharing an index_id
    # would put both series on one chart.
    seed(tmp_path, "2023-01", ["d0.com", "d1.com"])
    publish_series(tmp_path, CRAWLS[:1], ["GPTBot"], panel_size=12, log=lambda *a: None, **META)
    rows = published(tmp_path)
    assert len(rows) == 1
    assert rows[0]["index_id"] == "agent-accessibility-history"
    assert float(rows[0]["value"]) == 20.0


def test_is_never_provisional_however_thin_the_coverage(tmp_path):
    # 10 of 100 panel domains read: far below the live index's 97% threshold,
    # but no further evidence can ever arrive, so the number is final.
    seed(tmp_path, "2023-01", ["d0.com"])
    publish_series(tmp_path, CRAWLS[:1], ["GPTBot"], panel_size=100, log=lambda *a: None, **META)
    row = published(tmp_path)[0]
    assert row["provisional"] == "false"
    assert float(row["coverage"]) == 10.0


def test_records_the_change_from_the_previous_published_point(tmp_path):
    seed(tmp_path, "2023-01", ["d0.com"])
    seed(tmp_path, "2023-03", ["d0.com", "d1.com", "d2.com"])
    publish_series(tmp_path, CRAWLS[:2], ["GPTBot"], panel_size=10, log=lambda *a: None, **META)
    changes = [r for r in published(tmp_path, "series.csv") if r["series_id"] == CHANGE_SERIES]
    assert len(changes) == 1
    assert changes[0]["period"] == "2023-03"
    assert float(changes[0]["value"]) == 20.0


def test_a_missing_crawl_breaks_the_chain_rather_than_spanning_it(tmp_path):
    # 2023-03 was never collected. A change row on 2023-05 would describe two
    # steps in a field that claims to describe one.
    seed(tmp_path, "2023-01", ["d0.com"])
    seed(tmp_path, "2023-05", ["d0.com", "d1.com", "d2.com"])
    results = publish_series(tmp_path, CRAWLS, ["GPTBot"], panel_size=10, log=lambda *a: None, **META)
    assert [r["status"] for r in results] == ["published", "not collected", "published"]
    assert not [r for r in published(tmp_path, "series.csv") if r["series_id"] == CHANGE_SERIES]


def test_carries_the_crawl_the_evidence_came_from(tmp_path):
    # Provenance for evidence we did not gather ourselves: which collector
    # commit read it, recorded at collection time.
    seed(tmp_path, "2023-01", ["d0.com"], version="abc1234")
    publish_series(tmp_path, CRAWLS[:1], ["GPTBot"], panel_size=10, log=lambda *a: None, **META)
    assert published(tmp_path)[0]["collector_version"] == "abc1234"


def test_republishing_unchanged_evidence_adds_no_vintage(tmp_path):
    seed(tmp_path, "2023-01", ["d0.com"])
    for _ in range(2):
        publish_series(tmp_path, CRAWLS[:1], ["GPTBot"], panel_size=10, log=lambda *a: None, **META)
    assert len(published(tmp_path)) == 1
