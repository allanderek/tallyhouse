import json

import pytest

from tallyhouse.ledger import append_row
from tallyhouse.site import load_site_data, write_site
from tallyhouse.storage import store_body, write_manifest


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


def seed_evidence(root, period, bodies, *, agents_version=2, agents=("GPTBot", "CCBot")):
    """Committed raw evidence for one period, plus the agent set to read it with."""
    (root / "agents").mkdir(parents=True, exist_ok=True)
    (root / "agents" / f"v{agents_version}.json").write_text(
        json.dumps({"version": agents_version, "agents": list(agents)})
    )
    records = []
    for domain, body in bodies.items():
        records.append({
            "domain": domain, "outcome": "Fetched", "http_status": 200,
            "final_url": None, "content_type": "text/plain", "bytes": len(body),
            "sha256": store_body(root, body.encode()),
            "fetched_at": f"{period}T00:00:00Z", "attempts": 1,
        })
    write_manifest(root, period, records, collector_version="abc1234")


def test_stance_counts_are_derived_from_committed_evidence(tmp_path):
    """The crawler pages must not need a gitignored derived/ tree.

    generate is supposed to be a pure function of committed data -- that is the
    claim the project rests on -- and reading derived/*.csv meant a fresh clone
    rendered a different site, with every stance count zeroed.
    """
    seed_evidence(tmp_path, "2026-09-14", {
        "a.com": "User-agent: GPTBot\nDisallow: /\n",
        "b.com": "User-agent: *\nAllow: /\n",
    })
    append_row(tmp_path / "prints.csv",
               {"index_id": "agent-accessibility", "period": "2026-09-14"},
               meta(value="50.0", methodology_version="agents=2;protego=0.6.2"))
    assert not (tmp_path / "derived").exists()

    data = load_site_data(tmp_path)
    stances = {a: s for a, s in
               [(row["agent"], row["stance"]) for row in data["verdicts"]
                if row["domain"] == "a.com"]}
    assert stances["GPTBot"] == "FullBlock"
    assert stances["CCBot"] == "Unmentioned"
    assert {row["period"] for row in data["verdicts"]} == {"2026-09-14"}


def test_the_described_period_is_the_one_the_headline_is_about(tmp_path):
    """Not whichever period someone last ran derive for.

    derived/ held exactly one period, overwritten on each run, so the crawler
    pages could describe one week while the headline above them described
    another, with nothing on the page saying so.
    """
    seed_evidence(tmp_path, "2026-09-07", {"a.com": "User-agent: GPTBot\nDisallow: /\n"})
    seed_evidence(tmp_path, "2026-09-14", {"a.com": "User-agent: *\nAllow: /\n"})
    for period in ("2026-09-07", "2026-09-14"):
        append_row(tmp_path / "prints.csv",
                   {"index_id": "agent-accessibility", "period": period},
                   meta(value="50.0", methodology_version="agents=2;protego=0.6.2"))

    data = load_site_data(tmp_path)
    assert {row["period"] for row in data["verdicts"]} == {"2026-09-14"}
    # The later period does not block GPTBot, so the count must reflect that
    # rather than the earlier week's FullBlock.
    gptbot = [r for r in data["verdicts"] if r["agent"] == "GPTBot"]
    assert [r["stance"] for r in gptbot] == ["Unmentioned"]


def test_stances_are_counted_over_the_agent_set_that_produced_the_print(tmp_path):
    """Read off the print, not passed in alongside it.

    Otherwise a site can be rendered with 45 tokens under a headline computed
    from 16, and no page would say so.
    """
    seed_evidence(tmp_path, "2026-09-14", {"a.com": "User-agent: GPTBot\nDisallow: /\n"},
                  agents_version=1, agents=("GPTBot",))
    seed_evidence(tmp_path, "2026-09-14", {"a.com": "User-agent: GPTBot\nDisallow: /\n"},
                  agents_version=2, agents=("GPTBot", "CCBot", "Bytespider"))
    append_row(tmp_path / "prints.csv",
               {"index_id": "agent-accessibility", "period": "2026-09-14"},
               meta(value="100.0", methodology_version="agents=1;protego=0.6.2"))

    data = load_site_data(tmp_path)
    # The print says agents=1, so one token is counted -- not the three that
    # happen to be available in v2.
    assert {row["agent"] for row in data["verdicts"]} == {"GPTBot"}


def test_a_print_that_does_not_name_its_agent_set_is_refused(tmp_path):
    # Counting stances over a guessed agent set would publish numbers the
    # headline cannot vouch for. Zeroed counts would look like real data.
    from tallyhouse.site import UnreadableMethodology

    seed_evidence(tmp_path, "2026-09-14", {"a.com": "User-agent: *\nAllow: /\n"})
    append_row(tmp_path / "prints.csv",
               {"index_id": "agent-accessibility", "period": "2026-09-14"},
               meta(value="0.0", methodology_version="protego=0.6.2"))
    with pytest.raises(UnreadableMethodology, match="which agent set"):
        load_site_data(tmp_path)


def test_a_published_period_with_no_committed_evidence_yields_empty_sections(tmp_path):
    # A checkout without the raw tree still renders; it just cannot describe
    # per-crawler behaviour.
    append_row(tmp_path / "prints.csv",
               {"index_id": "agent-accessibility", "period": "2026-09-14"},
               meta(value="23.4", methodology_version="agents=2;protego=0.6.2"))
    data = load_site_data(tmp_path)
    assert data["verdicts"] == [] and data["fetches"] == []
    assert data["prints"][0]["value"] == "23.4"


def test_the_crawler_identity_takes_its_user_agent_from_the_collector(tmp_path):
    """Not from the JSON, so the published identity cannot drift from reality.

    An identity document that disagrees with the requests it describes is worse
    than none: it is precisely what a bot-verification reviewer would reject.
    """
    from tallyhouse.constants import USER_AGENT
    from tallyhouse.site import load_crawler_data

    (tmp_path / "crawler.json").write_text(json.dumps({
        "token": "TallyhouseIndexBot",
        "category": "Academic Research",
        "user_agent": "SomethingElse/9.9",
        "egress": {"prefixes": [{"ipv4Prefix": "203.0.113.7/32"}]},
    }))
    crawler = load_crawler_data(tmp_path)
    assert crawler["userAgent"] == USER_AGENT
    assert "SomethingElse" not in crawler["userAgent"]
    assert crawler["prefixes"] == ["203.0.113.7/32"]


def test_crawler_identity_is_empty_rather_than_absent_when_unconfigured(tmp_path):
    # The generator's decoder requires the field; a checkout without the file
    # must still render.
    from tallyhouse.site import load_crawler_data

    crawler = load_crawler_data(tmp_path)
    assert crawler["prefixes"] == [] and crawler["token"] == ""


def test_methodology_parameters_come_from_the_code_that_runs(tmp_path):
    """Not restated on the page.

    A methodology page that drifts from the pipeline documents a method nobody
    ran. Same reasoning as keeping the crawler's user-agent out of its JSON.
    """
    from tallyhouse.constants import CONCLUSIVE_OUTCOMES, PROBE_PATHS
    from tallyhouse.periods import COLLECTION_WINDOW_HOURS
    from tallyhouse.publish import PROVISIONAL_COVERAGE_THRESHOLD
    from tallyhouse.site import load_methodology_data

    parameters = load_methodology_data(tmp_path)["parameters"]
    assert parameters["probePaths"] == list(PROBE_PATHS)
    assert parameters["conclusiveOutcomes"] == sorted(CONCLUSIVE_OUTCOMES)
    assert parameters["collectionWindowHours"] == COLLECTION_WINDOW_HOURS
    assert parameters["provisionalCoverageThreshold"] == PROVISIONAL_COVERAGE_THRESHOLD


def test_a_superseded_methodology_version_says_so_rather_than_showing_nothing(tmp_path):
    # A version used only by restated rows is a different fact from one never
    # used, and "no periods" would read as the latter.
    from tallyhouse.site import load_methodology_data

    key = {"index_id": "agent-accessibility", "period": "2026-09-14"}
    append_row(tmp_path / "prints.csv", key, meta(value="23.4", methodology_version="agents=1;protego=0.6.2"))
    append_row(tmp_path / "prints.csv", key, meta(value="23.9", methodology_version="agents=2;protego=0.6.2"),
               reason="agent set expanded")
    (tmp_path / "methodology.json").write_text(json.dumps({"versions": [
        {"version": "agents=1;protego=0.6.2", "summary": "first"},
        {"version": "agents=2;protego=0.6.2", "summary": "45 tokens"},
    ]}))

    versions = {v["version"]: v for v in load_methodology_data(tmp_path)["versions"]}
    old = versions["agents=1;protego=0.6.2"]
    assert old["periods"] == [] and old["supersededPeriods"] == ["2026-09-14"]
    new = versions["agents=2;protego=0.6.2"]
    assert new["periods"] == ["2026-09-14"] and new["supersededPeriods"] == []


def test_a_published_version_with_no_changelog_entry_is_named(tmp_path):
    """So the gap is detectable rather than invisible.

    A figure published under a methodology nobody documented is exactly what
    this page exists to prevent.
    """
    from tallyhouse.site import load_methodology_data

    append_row(tmp_path / "prints.csv",
               {"index_id": "agent-accessibility", "period": "2026-09-14"},
               meta(value="23.4", methodology_version="agents=9;protego=9.9.9"))
    (tmp_path / "methodology.json").write_text(json.dumps({"versions": []}))
    assert load_methodology_data(tmp_path)["undocumented"] == ["agents=9;protego=9.9.9"]


def test_methodology_without_its_changelog_file_still_reports_parameters(tmp_path):
    from tallyhouse.site import load_methodology_data

    data = load_methodology_data(tmp_path)
    assert data["versions"] == [] and data["parameters"]["probePaths"]
