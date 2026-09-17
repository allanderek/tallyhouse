import pytest

from tallyhouse.compute import (
    blanket_rate,
    conclusive_domains,
    coverage,
    effective_rate,
    like_for_like_change,
    per_agent_rates,
    targeted_rate,
)

BLOCKING = [{"domain": "a.com", "agent": "GPTBot", "stance": "FullBlock"}]
PARTIAL = [{"domain": "b.com", "agent": "CCBot", "stance": "PartialBlock"}]
QUIET = [{"domain": "c.com", "agent": "GPTBot", "stance": "Unmentioned"}]


def test_only_fetched_and_no_robots_count_as_conclusive():
    observations = [
        {"domain": "a.com", "outcome": "Fetched"},
        {"domain": "b.com", "outcome": "NoRobotsTxt"},
        {"domain": "c.com", "outcome": "Timeout"},
        {"domain": "d.com", "outcome": "ServerError"},
    ]
    assert conclusive_domains(observations) == {"a.com", "b.com"}


def test_coverage_is_conclusive_over_panel_size():
    observations = [
        {"domain": "a.com", "outcome": "Fetched"},
        {"domain": "b.com", "outcome": "Timeout"},
    ]
    assert coverage(observations, panel_size=4) == 25.0


def test_targeted_rate_counts_domains_not_verdict_rows():
    # One domain blocking three agents is still one blocking domain.
    verdicts = [
        {"domain": "a.com", "agent": "GPTBot", "stance": "FullBlock"},
        {"domain": "a.com", "agent": "CCBot", "stance": "FullBlock"},
        {"domain": "a.com", "agent": "ClaudeBot", "stance": "PartialBlock"},
    ]
    assert targeted_rate(verdicts, {"a.com", "b.com"}) == 50.0


def test_partial_block_counts_toward_targeted_rate():
    assert targeted_rate(PARTIAL, {"b.com"}) == 100.0


def test_unmentioned_does_not_count_toward_targeted_rate():
    assert targeted_rate(QUIET, {"c.com"}) == 0.0


def test_targeted_rate_ignores_domains_outside_the_conclusive_set():
    assert targeted_rate(BLOCKING, {"z.com"}) == 0.0


def test_effective_rate_includes_blanket_blocked_domains():
    blanket = {"c.com": "FullBlock"}
    assert effective_rate(QUIET, blanket, {"c.com"}) == 100.0
    # ...whereas the targeted headline must not count it.
    assert targeted_rate(QUIET, {"c.com"}) == 0.0


def test_effective_rate_does_not_double_count():
    blanket = {"a.com": "FullBlock"}
    assert effective_rate(BLOCKING, blanket, {"a.com"}) == 100.0


def test_per_agent_rates_are_reported_separately():
    verdicts = [
        {"domain": "a.com", "agent": "GPTBot", "stance": "FullBlock"},
        {"domain": "b.com", "agent": "GPTBot", "stance": "Unmentioned"},
        {"domain": "a.com", "agent": "CCBot", "stance": "Unmentioned"},
        {"domain": "b.com", "agent": "CCBot", "stance": "Unmentioned"},
    ]
    rates = per_agent_rates(verdicts, {"a.com", "b.com"})
    assert rates == {"GPTBot": 50.0, "CCBot": 0.0}


def test_blanket_rate_counts_fully_closed_sites():
    assert blanket_rate({"a.com": "FullBlock", "b.com": "Allowed"}, {"a.com", "b.com"}) == 50.0


def test_like_for_like_change_uses_only_domains_seen_in_both_weeks():
    # b.com times out this week. Counting it last week but not this week
    # would invent a fall that never happened.
    prev = [
        {"domain": "a.com", "agent": "GPTBot", "stance": "FullBlock"},
        {"domain": "b.com", "agent": "GPTBot", "stance": "FullBlock"},
    ]
    cur = [{"domain": "a.com", "agent": "GPTBot", "stance": "FullBlock"}]
    change = like_for_like_change(prev, {"a.com", "b.com"}, cur, {"a.com"})
    assert change == 0.0


def test_like_for_like_change_detects_a_real_change():
    prev = [{"domain": "a.com", "agent": "GPTBot", "stance": "Unmentioned"},
            {"domain": "b.com", "agent": "GPTBot", "stance": "Unmentioned"}]
    cur = [{"domain": "a.com", "agent": "GPTBot", "stance": "FullBlock"},
           {"domain": "b.com", "agent": "GPTBot", "stance": "Unmentioned"}]
    change = like_for_like_change(prev, {"a.com", "b.com"}, cur, {"a.com", "b.com"})
    assert change == 50.0


def test_like_for_like_change_is_none_without_a_previous_period():
    assert like_for_like_change([], set(), [], set()) is None


def test_rates_with_no_conclusive_domains_raise_rather_than_divide_by_zero():
    with pytest.raises(ValueError):
        targeted_rate([], set())


def test_blanket_partial_block_is_not_counted_as_blanket_blocking():
    # A blanket partial block (e.g. Disallow: /wp-admin/ under User-agent: *)
    # is ordinary site hygiene, not a stance toward AI crawlers, so it does
    # not count toward blanket_rate.
    blanket = {"a.com": "PartialBlock"}
    assert blanket_rate(blanket, {"a.com"}) == 0.0


def test_blanket_partial_block_is_not_counted_in_effective_rate():
    # The same domain with blanket PartialBlock is excluded from effective_rate
    # when it has no targeted (named-agent) blocking verdict.
    blanket = {"a.com": "PartialBlock"}
    verdicts = []
    assert effective_rate(verdicts, blanket, {"a.com"}) == 0.0


def test_blanket_partial_block_with_targeted_verdict_is_counted_in_effective_rate():
    # When a blanket-partial domain ALSO has a targeted (named-agent) blocking
    # verdict, it is counted in effective_rate. This proves the exclusion is
    # specific to blanket partials, not a general issue with PartialBlock.
    blanket = {"a.com": "PartialBlock"}
    verdicts = [{"domain": "a.com", "agent": "GPTBot", "stance": "PartialBlock"}]
    assert effective_rate(verdicts, blanket, {"a.com"}) == 100.0
