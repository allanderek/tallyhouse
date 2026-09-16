import json

import pytest

from tallyhouse.config import load_agents, load_panel


def write_panel(root, year, domains, list_id="NX3JG"):
    path = root / "panel" / f"{year}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "year": year,
                "tranco_list_id": list_id,
                "captured": "2026-01-05T00:00:00Z",
                "domains": domains,
            }
        )
    )


def test_load_panel_exposes_provenance_and_domains(tmp_path):
    write_panel(tmp_path, 2026, ["example.com", "bbc.co.uk"])
    panel = load_panel(tmp_path, 2026)
    assert panel.year == 2026
    assert panel.tranco_list_id == "NX3JG"
    assert panel.domains == ["example.com", "bbc.co.uk"]


def test_panel_without_a_tranco_list_id_is_rejected(tmp_path):
    path = tmp_path / "panel" / "2026.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"year": 2026, "domains": ["a.com"]}))
    # The list id is what makes the panel falsifiable rather than asserted.
    with pytest.raises(KeyError):
        load_panel(tmp_path, 2026)


def test_duplicate_domains_in_a_panel_are_rejected(tmp_path):
    write_panel(tmp_path, 2026, ["a.com", "a.com"])
    with pytest.raises(ValueError):
        load_panel(tmp_path, 2026)


def test_load_agents_returns_the_tracked_set(tmp_path):
    path = tmp_path / "agents" / "v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "agents": ["GPTBot", "ClaudeBot"]}))
    assert load_agents(tmp_path, 1) == ["GPTBot", "ClaudeBot"]
