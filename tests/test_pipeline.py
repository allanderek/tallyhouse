"""Walks a tiny panel from raw evidence through to a published print."""

import pytest

from tallyhouse.compute import conclusive_domains, coverage, targeted_rate
from tallyhouse.derive import derive_period
from tallyhouse.ledger import append_row, read_rows
from tallyhouse.storage import store_body, write_manifest

AGENTS = ["GPTBot", "CCBot"]
PERIOD = "2026-09-14"
KEY = {"index_id": "agent-accessibility", "period": PERIOD}


def seed(root):
    bodies = {
        "blocks.com": "User-agent: GPTBot\nDisallow: /\n",
        "open.com": "User-agent: *\nAllow: /\n",
        "closed.com": "User-agent: *\nDisallow: /\n",
    }
    records = [
        {"domain": d, "outcome": "Fetched", "sha256": store_body(root, b.encode()),
         "http_status": 200, "final_url": f"https://{d}/robots.txt",
         "content_type": "text/plain", "bytes": len(b),
         "fetched_at": "2026-09-14T00:00:00Z", "attempts": 1}
        for d, b in bodies.items()
    ]
    records.append({"domain": "down.com", "outcome": "Timeout", "sha256": None,
                    "http_status": None, "final_url": None, "content_type": None,
                    "bytes": None, "fetched_at": "2026-09-14T00:00:00Z", "attempts": 3})
    write_manifest(root, PERIOD, records)


def test_pipeline_produces_a_print_matching_hand_computation(tmp_path):
    seed(tmp_path)
    tables = derive_period(tmp_path, PERIOD, AGENTS)

    conclusive = conclusive_domains(tables["observations"])
    assert conclusive == {"blocks.com", "open.com", "closed.com"}

    # Of 4 panel domains, 3 were conclusively observed.
    assert coverage(tables["observations"], panel_size=4) == 75.0

    # Only blocks.com names an AI agent and disallows it. closed.com is shut to
    # everyone but targets nobody, so it must not count here.
    assert targeted_rate(tables["verdicts"], conclusive) == pytest.approx(33.3333, abs=1e-3)

    path = tmp_path / "prints.csv"
    append_row(path, KEY, {
        "value": "33.3333", "denominator": "3", "coverage": "75.0",
        "methodology_version": "1", "collector_version": "test",
        "computed_at": "2026-09-17T00:00:00Z",
    })
    assert read_rows(path)[0]["vintage"] == "1"


def test_rerunning_the_pipeline_changes_nothing(tmp_path):
    seed(tmp_path)
    path = tmp_path / "prints.csv"
    row = {"value": "33.3333", "denominator": "3", "coverage": "75.0",
           "methodology_version": "1", "collector_version": "test",
           "computed_at": "2026-09-17T00:00:00Z"}
    append_row(path, KEY, row)
    assert append_row(path, KEY, row) is None
    assert len(read_rows(path)) == 1
