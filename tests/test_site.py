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


def _agent_fixture(tmp_path, agents, operators, purposes=None):
    d = tmp_path / "agents"
    d.mkdir(parents=True, exist_ok=True)
    (d / "descriptions.json").write_text(json.dumps({
        "agents": agents, "operators": operators,
        "purposes": purposes or {"training": "bulk crawl"},
    }))


def test_stance_counts_are_aggregated_per_agent(tmp_path):
    from tallyhouse.site import load_agent_data
    _agent_fixture(tmp_path,
                   {"GPTBot": {"operator": "OpenAI", "purpose": "training", "description": "d"}},
                   {"OpenAI": "desc"})
    verdicts = [{"domain": "a.com", "agent": "GPTBot", "stance": "FullBlock"},
                {"domain": "b.com", "agent": "GPTBot", "stance": "FullBlock"},
                {"domain": "c.com", "agent": "GPTBot", "stance": "Unmentioned"}]
    got = load_agent_data(tmp_path, verdicts)["agents"]["GPTBot"]
    assert got["stances"] == {"FullBlock": 2, "PartialBlock": 0, "Allowed": 0, "Unmentioned": 1}
    assert got["series_id"] == "agent:GPTBot"
    assert got["slug"] == "gptbot"


def test_an_agent_with_no_verdicts_still_appears_with_zeroes(tmp_path):
    from tallyhouse.site import load_agent_data
    _agent_fixture(tmp_path,
                   {"NewBot": {"operator": "X", "purpose": "training", "description": "d"}},
                   {"X": "desc"})
    got = load_agent_data(tmp_path, [])["agents"]["NewBot"]
    # A newly tracked crawler must not vanish from the site because nothing
    # blocked it yet — that absence is itself a fact worth showing.
    assert got["stances"]["FullBlock"] == 0


def test_divergent_domains_are_those_treating_an_operators_tokens_differently(tmp_path):
    from tallyhouse.site import load_agent_data
    _agent_fixture(tmp_path, {
        "A-Train": {"operator": "Acme", "purpose": "training", "description": "d"},
        "A-User": {"operator": "Acme", "purpose": "training", "description": "d"},
    }, {"Acme": "desc"})
    verdicts = [
        # splits the two tokens -> divergent
        {"domain": "split.com", "agent": "A-Train", "stance": "FullBlock"},
        {"domain": "split.com", "agent": "A-User", "stance": "Unmentioned"},
        # treats them alike -> not divergent
        {"domain": "same.com", "agent": "A-Train", "stance": "FullBlock"},
        {"domain": "same.com", "agent": "A-User", "stance": "FullBlock"},
    ]
    op = load_agent_data(tmp_path, verdicts)["operators"]["Acme"]
    assert op["divergent_count"] == 1
    assert [d["domain"] for d in op["divergent_examples"]] == ["split.com"]


def test_a_single_token_operator_has_no_divergence(tmp_path):
    from tallyhouse.site import load_agent_data
    _agent_fixture(tmp_path,
                   {"Solo": {"operator": "Lone", "purpose": "training", "description": "d"}},
                   {"Lone": "desc"})
    verdicts = [{"domain": "a.com", "agent": "Solo", "stance": "FullBlock"}]
    assert load_agent_data(tmp_path, verdicts)["operators"]["Lone"]["divergent_count"] == 0


def test_divergent_examples_are_capped_but_the_count_is_not(tmp_path):
    from tallyhouse.site import load_agent_data
    _agent_fixture(tmp_path, {
        "T1": {"operator": "Acme", "purpose": "training", "description": "d"},
        "T2": {"operator": "Acme", "purpose": "training", "description": "d"},
    }, {"Acme": "desc"})
    verdicts = []
    for i in range(40):
        verdicts += [{"domain": f"d{i:02}.com", "agent": "T1", "stance": "FullBlock"},
                     {"domain": f"d{i:02}.com", "agent": "T2", "stance": "Allowed"}]
    op = load_agent_data(tmp_path, verdicts)["operators"]["Acme"]
    # The page shows a sample; the headline count must still be the true total.
    assert op["divergent_count"] == 40
    assert len(op["divergent_examples"]) == 25


def test_site_data_renders_without_crawler_descriptions(tmp_path):
    # The site must build from prints alone. Descriptions are editorial; a
    # missing file should not stop a number being published.
    append_row(tmp_path / "prints.csv",
               {"index_id": "agent-accessibility", "period": "2026-09-14"}, meta(value="23.4"))
    data = load_site_data(tmp_path)
    assert data["prints"] and data["agents"] == {} and data["operators"] == {}


def test_the_historical_series_travels_as_its_own_index(tmp_path):
    # Not as more periods of the live series: the levels are not comparable,
    # and keeping them separate in the data is what stops a page charting them
    # together by accident.
    append_row(tmp_path / "prints.csv",
               {"index_id": "agent-accessibility", "period": "2026-09-14"},
               meta(value="23.4"))
    for period, value in [("2023-01", "1.28"), ("2026-08", "27.85")]:
        append_row(tmp_path / "prints.csv",
                   {"index_id": "agent-accessibility-history", "period": period},
                   meta(value=value, denominator="390", coverage="63.8"))
    data = load_site_data(tmp_path)
    assert [p["value"] for p in data["prints"]] == ["23.4"]
    assert [p["period"] for p in data["history"]["prints"]] == ["2023-01", "2026-08"]
    assert [p["value"] for p in data["history"]["prints"]] == ["1.28", "27.85"]


def test_the_historical_panel_and_crawl_list_travel(tmp_path):
    # The page has to be able to say what it measured and which crawls it read,
    # because neither is derivable from the numbers.
    (tmp_path / "panel").mkdir()
    (tmp_path / "panel" / "historical.json").write_text(json.dumps({
        "domains": ["a.com", "b.com"],
        "endpoints": [{"tranco_list_id": "K2K4W", "date": "2023-02-01", "size": 1000}],
        "construction": {"rule": "present at BOTH endpoints", "churn": "389 of 1000"},
    }))
    (tmp_path / "crawls").mkdir()
    (tmp_path / "crawls" / "historical.json").write_text(json.dumps({
        "crawls": [{"crawl": "CC-MAIN-2023-06", "period": "2023-01"}],
        "selection": "roughly quarterly",
    }))
    history = load_site_data(tmp_path)["history"]
    assert history["panel"]["size"] == 2
    assert history["panel"]["construction"]["churn"] == "389 of 1000"
    assert history["panel"]["endpoints"][0]["tranco_list_id"] == "K2K4W"
    assert history["crawls"] == [{"crawl": "CC-MAIN-2023-06", "period": "2023-01"}]
    assert history["selection"] == "roughly quarterly"


def test_a_restated_historical_period_keeps_its_superseded_vintage(tmp_path):
    key = {"index_id": "agent-accessibility-history", "period": "2024-05"}
    append_row(tmp_path / "prints.csv", key, meta(value="13.38"))
    append_row(tmp_path / "prints.csv", key, meta(value="22.14"), reason="lost bodies")
    history = load_site_data(tmp_path)["history"]
    assert [p["value"] for p in history["prints"]] == ["22.14"]
    assert [p["value"] for p in history["superseded"]] == ["13.38"]


def test_history_is_present_even_with_nothing_published(tmp_path):
    # The generator's decoder requires the field; an index with no prints yet
    # must yield an empty series rather than a missing key.
    history = load_site_data(tmp_path)["history"]
    assert history["prints"] == [] and history["panel"]["size"] == 0
