from tallyhouse.derive import derive_period, write_tables
from tallyhouse.storage import store_body, write_manifest

AGENTS = ["GPTBot", "CCBot"]


def seed(root, period, entries):
    """entries: list of (domain, outcome, body_or_None)"""
    records = []
    for domain, outcome, body in entries:
        sha = store_body(root, body.encode()) if body is not None else None
        records.append({"domain": domain, "outcome": outcome, "sha256": sha,
                        "http_status": 200 if body is not None else None,
                        "fetched_at": "2026-09-14T00:00:00Z", "attempts": 1,
                        "final_url": None, "content_type": None,
                        "bytes": len(body) if body is not None else None})
    write_manifest(root, period, records)


def test_verdicts_are_produced_for_every_agent_on_conclusive_domains(tmp_path):
    seed(tmp_path, "2026-09-14", [("a.com", "Fetched", "User-agent: GPTBot\nDisallow: /\n")])
    tables = derive_period(tmp_path, "2026-09-14", AGENTS)
    stances = {v["agent"]: v["stance"] for v in tables["verdicts"]}
    assert stances == {"GPTBot": "FullBlock", "CCBot": "Unmentioned"}


def test_domains_without_robots_txt_are_conclusive_and_unmentioned(tmp_path):
    seed(tmp_path, "2026-09-14", [("a.com", "NoRobotsTxt", None)])
    tables = derive_period(tmp_path, "2026-09-14", AGENTS)
    stances = {v["stance"] for v in tables["verdicts"]}
    assert stances == {"Unmentioned"}
    assert tables["blanket"]["a.com"] == "Allowed"


def test_inconclusive_domains_produce_no_verdicts(tmp_path):
    seed(tmp_path, "2026-09-14", [("a.com", "Timeout", None)])
    tables = derive_period(tmp_path, "2026-09-14", AGENTS)
    assert tables["verdicts"] == []
    assert "a.com" not in tables["blanket"]


def test_blanket_stance_is_recorded_per_domain(tmp_path):
    seed(tmp_path, "2026-09-14", [("a.com", "Fetched", "User-agent: *\nDisallow: /\n")])
    tables = derive_period(tmp_path, "2026-09-14", AGENTS)
    assert tables["blanket"]["a.com"] == "FullBlock"


def test_derive_is_deterministic(tmp_path):
    seed(tmp_path, "2026-09-14", [
        ("b.com", "Fetched", "User-agent: CCBot\nDisallow: /x\n"),
        ("a.com", "Fetched", "User-agent: GPTBot\nDisallow: /\n"),
    ])
    first = derive_period(tmp_path, "2026-09-14", AGENTS)
    second = derive_period(tmp_path, "2026-09-14", AGENTS)
    assert first == second


def test_write_tables_produces_sorted_csv(tmp_path):
    seed(tmp_path, "2026-09-14", [
        ("b.com", "Fetched", "User-agent: GPTBot\nDisallow: /\n"),
        ("a.com", "Fetched", "User-agent: GPTBot\nDisallow: /\n"),
    ])
    tables = derive_period(tmp_path, "2026-09-14", AGENTS)
    write_tables(tmp_path / "derived", "2026-09-14", tables)
    text = (tmp_path / "derived" / "verdicts.csv").read_text()
    assert text.index("a.com") < text.index("b.com")


def test_404_with_a_directive_bearing_body_is_never_parsed(tmp_path):
    # Belt and braces: even if a body somehow reaches the manifest alongside a
    # NoRobotsTxt outcome, derive must treat the domain as having no policy.
    sha = store_body(tmp_path, b"User-agent: GPTBot\nDisallow: /\n")
    write_manifest(tmp_path, "2026-09-14", [
        {"domain": "gone.com", "outcome": "NoRobotsTxt", "sha256": sha,
         "http_status": 404, "final_url": None, "content_type": "text/plain",
         "bytes": 31, "fetched_at": "2026-09-14T00:00:00Z", "attempts": 1},
    ])

    tables = derive_period(tmp_path, "2026-09-14", AGENTS)
    stances = {v["agent"]: v["stance"] for v in tables["verdicts"]}
    assert stances == {"GPTBot": "Unmentioned", "CCBot": "Unmentioned"}
    assert tables["blanket"]["gone.com"] == "Allowed"
