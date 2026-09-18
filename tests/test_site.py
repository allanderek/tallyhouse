import json

from tallyhouse.ledger import append_row
from tallyhouse.site import load_site_data, write_site


def meta(**over):
    base = {"denominator": "997", "coverage": "99.7", "provisional": "false",
            "methodology_version": "1", "collector_version": "abc",
            "computed_at": "2026-09-17T00:00:00Z"}
    base.update(over)
    return base


def test_prints_are_ordered_by_period(tmp_path):
    for period, value in [("2026-09-14", "23.4"), ("2026-09-07", "22.1")]:
        append_row(tmp_path / "prints.csv",
                   {"index_id": "agent-accessibility", "period": period},
                   meta(value=value))
    data = load_site_data(tmp_path)
    assert [p["period"] for p in data["prints"]] == ["2026-09-07", "2026-09-14"]


def test_only_the_latest_vintage_is_shown(tmp_path):
    key = {"index_id": "agent-accessibility", "period": "2026-09-14"}
    append_row(tmp_path / "prints.csv", key, meta(value="23.4"))
    append_row(tmp_path / "prints.csv", key, meta(value="24.9"), reason="parser fix")
    data = load_site_data(tmp_path)
    assert [p["value"] for p in data["prints"]] == ["24.9"]


def test_a_superseded_vintage_still_travels_to_the_site(tmp_path):
    # A restatement must be visible as a restatement. Dropping the old value
    # would make the correction invisible, which is the opposite of the point.
    key = {"index_id": "agent-accessibility", "period": "2026-09-14"}
    append_row(tmp_path / "prints.csv", key, meta(value="23.4"))
    append_row(tmp_path / "prints.csv", key, meta(value="24.9"), reason="parser fix")
    data = load_site_data(tmp_path)
    assert [s["value"] for s in data["superseded"]] == ["23.4"]
    assert data["superseded"][0]["reason"] == ""
    assert data["prints"][0]["reason"] == "parser fix"


def test_another_index_is_not_mixed_in(tmp_path):
    append_row(tmp_path / "prints.csv",
               {"index_id": "agent-accessibility", "period": "2026-09-14"}, meta(value="23.4"))
    append_row(tmp_path / "prints.csv",
               {"index_id": "something-else", "period": "2026-09-14"}, meta(value="99.9"))
    data = load_site_data(tmp_path)
    assert [p["value"] for p in data["prints"]] == ["23.4"]


def test_panel_provenance_travels(tmp_path):
    panel = tmp_path / "panel" / "2026.json"
    panel.parent.mkdir(parents=True)
    panel.write_text(json.dumps({"tranco_list_id": "N2P2W", "captured": "2026-09-17",
                                 "domains": ["a.com", "b.com"],
                                 "qualification": {"excluded": 556}}))
    data = load_site_data(tmp_path)
    assert data["panel"]["tranco_list_id"] == "N2P2W"
    assert data["panel"]["size"] == 2
    # The exclusion count is published so a reader can size the stated bias.
    assert data["panel"]["qualification"]["excluded"] == 556


def test_missing_data_yields_empty_sections_rather_than_failing(tmp_path):
    data = load_site_data(tmp_path)
    assert data["prints"] == [] and data["verdicts"] == []


def test_write_site_creates_nested_directories(tmp_path):
    written = write_site({"index.html": "a", "about/crawler/index.html": "b"}, tmp_path)
    assert (tmp_path / "about" / "crawler" / "index.html").read_text() == "b"
    assert len(written) == 2
