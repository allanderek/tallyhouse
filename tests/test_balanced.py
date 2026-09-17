import json

import pytest

from tallyhouse.balanced import balanced_panel, load_balanced_panel, write_balanced_panel


def test_only_domains_present_at_both_endpoints_are_retained():
    early = [(1, "a.com"), (2, "gone.com"), (3, "b.com")]
    late = [(1, "b.com"), (2, "new.com"), (3, "a.com")]
    assert [e["domain"] for e in balanced_panel(early, late)] == ["b.com", "a.com"]


def test_both_ranks_are_retained_so_movement_is_visible():
    early = [(7, "a.com")]
    late = [(2, "a.com")]
    entry = balanced_panel(early, late)[0]
    assert entry["rank_early"] == 7
    assert entry["rank_late"] == 2


def test_ordering_is_deterministic():
    early = [(1, "a.com"), (2, "b.com"), (3, "c.com")]
    late = [(3, "a.com"), (1, "c.com"), (2, "b.com")]
    first = [e["domain"] for e in balanced_panel(early, late)]
    assert first == ["c.com", "b.com", "a.com"]
    assert first == [e["domain"] for e in balanced_panel(early, late)]


def test_an_empty_intersection_is_empty_not_an_error():
    assert balanced_panel([(1, "a.com")], [(1, "b.com")]) == []


def test_written_panel_records_both_endpoints_and_its_biases(tmp_path):
    entries = balanced_panel([(1, "a.com"), (2, "gone.com")], [(1, "a.com")])
    write_balanced_panel(tmp_path, "historical",
                         early_list_id="K2K4W", early_date="2023-02-01",
                         late_list_id="N2P2W", late_date="2026-09-16",
                         entries=entries, early_size=2, late_size=1)

    document = json.loads((tmp_path / "panel" / "historical.json").read_text())
    assert [e["tranco_list_id"] for e in document["endpoints"]] == ["K2K4W", "N2P2W"]
    c = document["construction"]
    assert c["retained"] == 1
    # The biases are recorded in the artifact, not only in prose elsewhere.
    assert "durably significant" in c["known_bias"]
    assert "not comparable" in c["not_comparable"].lower()
    assert load_balanced_panel(tmp_path, "historical") == ["a.com"]


def test_loading_rejects_a_panel_with_duplicates(tmp_path):
    path = tmp_path / "panel" / "dup.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"domains": ["a.com", "a.com"]}))
    with pytest.raises(ValueError):
        load_balanced_panel(tmp_path, "dup")
