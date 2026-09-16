from tallyhouse import constants


def test_user_agent_identifies_and_links_to_crawler_page():
    assert constants.USER_AGENT.startswith("TallyhouseIndexBot/1.0")
    assert "/about/crawler/" in constants.USER_AGENT


def test_probe_paths_include_root_and_varied_subpaths():
    assert "/" in constants.PROBE_PATHS
    assert len(constants.PROBE_PATHS) >= 5


def test_only_fetched_and_no_robots_are_conclusive():
    assert constants.CONCLUSIVE_OUTCOMES == frozenset({"Fetched", "NoRobotsTxt"})
