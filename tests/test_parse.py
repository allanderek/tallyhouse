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
