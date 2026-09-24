from tallyhouse.parse import blanket_stance, classify, is_mentioned

FULL = "User-agent: GPTBot\nDisallow: /\n"
PARTIAL = "User-agent: CCBot\nDisallow: /about\n"
ALLOW_ALL = "User-agent: *\nAllow: /\n"
BLANKET = "User-agent: *\nDisallow: /\n"


def test_agent_named_and_fully_disallowed_is_full_block():
    assert classify(FULL, "GPTBot") == "FullBlock"


def test_agent_named_and_partly_disallowed_is_partial_block():
    assert classify(PARTIAL, "CCBot") == "PartialBlock"


def test_agent_not_named_anywhere_is_unmentioned():
    assert classify(FULL, "ClaudeBot") == "Unmentioned"


def test_unmentioned_takes_precedence_over_blanket_rules():
    # The site blocks everyone via *, but says nothing about ClaudeBot.
    # The targeted headline must not count this as targeting ClaudeBot.
    assert classify(BLANKET, "ClaudeBot") == "Unmentioned"


def test_agent_named_and_explicitly_allowed_is_allowed():
    body = BLANKET + "\nUser-agent: GPTBot\nAllow: /\nDisallow:\n"
    assert classify(body, "GPTBot") == "Allowed"


def test_agent_matching_is_case_insensitive():
    assert is_mentioned("user-agent: gptbot\nDisallow: /\n", "GPTBot")
    assert classify("user-agent: gptbot\nDisallow: /\n", "GPTBot") == "FullBlock"


def test_substring_of_another_agent_name_does_not_count_as_mentioned():
    # "Applebot-Extended" being present must not imply "Applebot" is named.
    assert not is_mentioned("User-agent: Applebot-Extended\nDisallow: /\n", "Applebot")


def test_blanket_stance_detects_a_site_closed_to_everyone():
    assert blanket_stance(BLANKET) == "FullBlock"


def test_blanket_stance_of_an_open_site_is_allowed():
    assert blanket_stance(ALLOW_ALL) == "Allowed"


def test_empty_body_is_unmentioned_and_open():
    assert classify("", "GPTBot") == "Unmentioned"
    assert blanket_stance("") == "Allowed"


# Tests for directive-based PartialBlock detection (catches real blocking not in probe set)
def test_disallow_articles_is_partial_block():
    body = "User-agent: GPTBot\nDisallow: /articles/\n"
    assert classify(body, "GPTBot") == "PartialBlock"


def test_disallow_premium_is_partial_block():
    body = "User-agent: GPTBot\nDisallow: /premium\n"
    assert classify(body, "GPTBot") == "PartialBlock"


def test_disallow_wp_admin_is_partial_block():
    body = "User-agent: GPTBot\nDisallow: /wp-admin/\n"
    assert classify(body, "GPTBot") == "PartialBlock"


def test_empty_disallow_value_is_allowed():
    body = "User-agent: GPTBot\nDisallow:\n"
    assert classify(body, "GPTBot") == "Allowed"


def test_disallow_cancelled_by_allow_is_allowed():
    body = "User-agent: GPTBot\nDisallow: /x\nAllow: /x\n"
    assert classify(body, "GPTBot") == "Allowed"


def test_multi_agent_group_applies_to_both_agents():
    body = "User-agent: GPTBot\nUser-agent: CCBot\nDisallow: /x\n"
    assert classify(body, "GPTBot") == "PartialBlock"
    assert classify(body, "CCBot") == "PartialBlock"


def test_disallow_in_different_agent_group_does_not_apply():
    body = "User-agent: OtherBot\nDisallow: /x\n\nUser-agent: GPTBot\nDisallow:\n"
    assert classify(body, "GPTBot") == "Allowed"


def test_full_disallow_takes_precedence_over_directive_based():
    # Even with directive-based PartialBlock detection, FullBlock (all probes denied) wins
    body = "User-agent: GPTBot\nDisallow: /\n"
    assert classify(body, "GPTBot") == "FullBlock"


def test_unmentioned_precedence_unchanged():
    # Blanket block does not make an unmentioned agent anything but Unmentioned
    body = "User-agent: *\nDisallow: /\nUser-agent: OtherBot\nDisallow: /api\n"
    assert classify(body, "GPTBot") == "Unmentioned"


# Tests for RFC 9309 comment handling (# to EOL)
def test_agent_mention_with_inline_comment():
    body = "User-agent: GPTBot  # block the AI scrapers\nDisallow: /\n"
    assert is_mentioned(body, "GPTBot")
    assert classify(body, "GPTBot") == "FullBlock"


def test_disallow_with_inline_comment_value_extracted_correctly():
    body = "User-agent: GPTBot\nDisallow: /articles/  # paywalled\n"
    assert classify(body, "GPTBot") == "PartialBlock"
    # Test the shared extraction helper directly so the value is pinned
    from tallyhouse.parse import _parse_directive_line
    parsed = _parse_directive_line("Disallow: /articles/  # paywalled")
    assert parsed == ("disallow", "/articles/")


def test_full_line_comment_between_directives_does_not_break_parsing():
    body = "User-agent: GPTBot\nDisallow: /x\n# just a comment\nDisallow: /y\n"
    # Both /x and /y should be disallowed for GPTBot
    from tallyhouse.parse import _parse_groups
    groups = _parse_groups(body)
    assert len(groups) == 1
    assert groups[0][0] == ["GPTBot"]
    # Both disallows should be in the group
    assert len(groups[0][1]) == 2
    assert groups[0][1][0] == ("disallow", "/x")
    assert groups[0][1][1] == ("disallow", "/y")


def test_comment_after_user_agent_does_not_affect_following_disallows():
    body = "User-agent: GPTBot  # test agent\nDisallow: /x\n"
    from tallyhouse.parse import _parse_groups
    groups = _parse_groups(body)
    assert len(groups) == 1
    assert groups[0][0] == ["GPTBot"]
    assert groups[0][1][0] == ("disallow", "/x")


# Group boundaries: a User-agent line after ANY directive starts a new group.
def test_named_group_of_only_non_rule_directives_does_not_absorb_the_next_group():
    from tallyhouse.parse import _parse_groups
    body = (
        "User-agent: GPTBot\n"
        "Crawl-delay: 10\n"
        "User-agent: *\n"
        "Disallow: /\n"
    )
    assert _parse_groups(body) == [
        (["GPTBot"], []),
        (["*"], [("disallow", "/")]),
    ]
    # GPTBot is named but the blocking rule belongs to the wildcard group, so
    # the targeted headline must not count this domain (spec 6.4).
    assert classify(body, "GPTBot") == "Allowed"
    assert blanket_stance(body) == "FullBlock"


def test_sitemap_between_groups_does_not_merge_them():
    from tallyhouse.parse import _parse_groups
    body = (
        "User-agent: OtherBot\n"
        "Sitemap: https://example.com/sitemap.xml\n"
        "User-agent: GPTBot\n"
        "Disallow: /x\n"
    )
    assert _parse_groups(body) == [
        (["OtherBot"], []),
        (["GPTBot"], [("disallow", "/x")]),
    ]


def test_host_directive_between_groups_does_not_merge_them():
    from tallyhouse.parse import _parse_groups
    body = (
        "User-agent: GPTBot\n"
        "Host: example.com\n"
        "User-agent: CCBot\n"
        "Disallow: /y\n"
    )
    assert _parse_groups(body) == [
        (["GPTBot"], []),
        (["CCBot"], [("disallow", "/y")]),
    ]
    assert classify(body, "GPTBot") == "Allowed"
    assert classify(body, "CCBot") == "PartialBlock"


def test_consecutive_user_agents_still_share_one_group():
    from tallyhouse.parse import _parse_groups
    body = "User-agent: GPTBot\nUser-agent: CCBot\nDisallow: /x\n"
    assert _parse_groups(body) == [(["GPTBot", "CCBot"], [("disallow", "/x")])]


def test_rules_before_any_user_agent_line_are_discarded():
    from tallyhouse.parse import _parse_groups
    body = "Disallow: /orphan\nUser-agent: GPTBot\nDisallow: /x\n"
    assert _parse_groups(body) == [(["GPTBot"], [("disallow", "/x")])]


def test_unsanitisable_pattern_is_not_a_block_without_protego_agreeing():
    # "Disallow: $" sanitises to nothing testable. It must not be asserted as a
    # block on the strength of that failure alone. The rule has to sit in
    # GPTBot's OWN group: put it under "*" and GPTBot's group has no rules at
    # all, so the sanitisation branch is never reached and the test proves
    # nothing.
    body = "User-agent: GPTBot\nDisallow: $\n"
    assert classify(body, "GPTBot") == "Allowed"


def test_wildcard_pattern_still_counts_when_protego_agrees():
    # "*" sanitises to "/", which protego confirms is blocked, so the block
    # stands: the fix skips only patterns nothing can confirm.
    body = "User-agent: GPTBot\nDisallow: /private*/data\n"
    assert classify(body, "GPTBot") == "PartialBlock"


def test_a_body_is_parsed_once_however_many_agents_are_classified():
    """Classification is per agent; parsing is per body.

    A period is classified one domain at a time against every tracked agent, so
    without this the real 997-domain panel cost 8.2 Protego parses and 45 line
    scans per domain -- all of the same body -- and a site render took 102
    seconds. Caching cannot change a verdict because both functions are pure
    functions of the body; this test is here so the cache cannot be lost by
    accident.
    """
    from tallyhouse import parse as parse_module

    parse_module._parsed.cache_clear()
    parse_module._named_tokens.cache_clear()

    body = "User-agent: GPTBot\nDisallow: /private\nUser-agent: *\nAllow: /\n"
    agents = ["GPTBot", "CCBot", "Bytespider", "ClaudeBot", "Applebot-Extended"]
    parse_module.blanket_stance(body)
    for agent in agents:
        parse_module.classify(body, agent)

    assert parse_module._parsed.cache_info().misses == 1
    assert parse_module._named_tokens.cache_info().misses == 1


def test_caching_does_not_leak_between_different_bodies():
    # Two sites, one blocking and one not. A cache keyed wrongly would report
    # the first site's policy for the second.
    blocking = "User-agent: GPTBot\nDisallow: /\n"
    permissive = "User-agent: GPTBot\nAllow: /\n"
    assert classify(blocking, "GPTBot") == "FullBlock"
    assert classify(permissive, "GPTBot") == "Allowed"
    assert classify(blocking, "GPTBot") == "FullBlock"


def test_mentioned_matching_stays_whole_token_and_case_insensitive():
    # The property the token-set rewrite had to preserve: Applebot-Extended
    # must not imply Applebot, and case must not matter.
    body = "User-agent: Applebot-Extended\nDisallow: /\n"
    assert is_mentioned(body, "Applebot-Extended")
    assert is_mentioned(body, "applebot-extended")
    assert not is_mentioned(body, "Applebot")
    assert not is_mentioned(body, "Extended")
