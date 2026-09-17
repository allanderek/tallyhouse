import json

import pytest

from tallyhouse.cli import main
from tallyhouse.ledger import read_rows
from tallyhouse.storage import store_body, write_manifest


def seed_config(root):
    (root / "agents").mkdir(parents=True, exist_ok=True)
    (root / "agents" / "v1.json").write_text(
        json.dumps({"version": 1, "agents": ["GPTBot"]})
    )
    (root / "panel").mkdir(parents=True, exist_ok=True)
    (root / "panel" / "2026.json").write_text(
        json.dumps({"year": 2026, "tranco_list_id": "TEST1",
                    "captured": "2026-01-05T00:00:00Z",
                    "domains": ["a.com", "b.com"]})
    )


def seed_raw(root):
    records = []
    for domain, body in [("a.com", "User-agent: GPTBot\nDisallow: /\n"),
                         ("b.com", "User-agent: *\nAllow: /\n")]:
        records.append({"domain": domain, "outcome": "Fetched",
                        "sha256": store_body(root, body.encode()),
                        "http_status": 200, "final_url": None,
                        "content_type": "text/plain", "bytes": len(body),
                        "fetched_at": "2026-09-14T00:00:00Z", "attempts": 1})
    write_manifest(root, "2026-09-14", records, collector_version="abc1234")


def test_derive_writes_tables(tmp_path):
    seed_config(tmp_path)
    seed_raw(tmp_path)
    assert main(["derive", "--root", str(tmp_path), "--period", "2026-09-14"]) == 0
    assert (tmp_path / "derived" / "verdicts.csv").exists()


def test_print_writes_a_ledger_row(tmp_path):
    seed_config(tmp_path)
    seed_raw(tmp_path)
    assert main(["print", "--root", str(tmp_path), "--period", "2026-09-14"]) == 0
    rows = read_rows(tmp_path / "prints.csv")
    assert rows[0]["value"] == "50.0"


def test_reprinting_an_unchanged_period_succeeds_without_duplicating(tmp_path):
    seed_config(tmp_path)
    seed_raw(tmp_path)
    main(["print", "--root", str(tmp_path), "--period", "2026-09-14"])
    assert main(["print", "--root", str(tmp_path), "--period", "2026-09-14"]) == 0
    assert len(read_rows(tmp_path / "prints.csv")) == 1


def test_changed_result_without_a_reason_exits_nonzero(tmp_path):
    seed_config(tmp_path)
    seed_raw(tmp_path)
    main(["print", "--root", str(tmp_path), "--period", "2026-09-14"])

    # Change the evidence so the computed value differs.
    write_manifest(tmp_path, "2026-09-14", [
        {"domain": "a.com", "outcome": "Fetched",
         "sha256": store_body(tmp_path, b"User-agent: *\nAllow: /\n"),
         "http_status": 200, "final_url": None, "content_type": "text/plain",
         "bytes": 24, "fetched_at": "2026-09-14T00:00:00Z", "attempts": 1},
    ], collector_version="abc1234")
    assert main(["print", "--root", str(tmp_path), "--period", "2026-09-14"]) != 0
    assert len(read_rows(tmp_path / "prints.csv")) == 1


def test_invalid_period_is_rejected(tmp_path):
    seed_config(tmp_path)
    with pytest.raises(SystemExit):
        main(["derive", "--root", str(tmp_path), "--period", "2026-09-16"])


def test_root_before_subcommand_is_rejected(tmp_path):
    seed_config(tmp_path)
    # --root before the subcommand should be rejected by argparse
    with pytest.raises(SystemExit):
        main(["--root", str(tmp_path), "derive", "--period", "2026-09-14"])


def test_derive_for_never_collected_period_exits_nonzero(tmp_path, capsys):
    seed_config(tmp_path)
    # No manifest written for this period
    exit_code = main(["derive", "--root", str(tmp_path), "--period", "2026-09-14"])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "2026-09-14" in captured.err


def test_print_for_never_collected_period_exits_nonzero(tmp_path, capsys):
    seed_config(tmp_path)
    # No manifest written for this period
    exit_code = main(["print", "--root", str(tmp_path), "--period", "2026-09-14"])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "2026-09-14" in captured.err


def test_malformed_agents_json_exits_nonzero(tmp_path, capsys):
    seed_config(tmp_path)
    # Write malformed agents JSON
    (tmp_path / "agents" / "v1.json").write_text("{invalid json")
    seed_raw(tmp_path)

    exit_code = main(["derive", "--root", str(tmp_path), "--period", "2026-09-14"])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "error:" in captured.err


def test_missing_body_file_in_previous_period_exits_nonzero(tmp_path, capsys):
    from tallyhouse.storage import body_path

    seed_config(tmp_path)

    # Seed previous period (2026-09-07) with distinctive content
    prev_body_text = "User-agent: GPTBot\nDisallow: /\n"
    prev_records = []
    for domain in ["a.com", "b.com"]:
        prev_sha = store_body(tmp_path, prev_body_text.encode())
        prev_records.append({"domain": domain, "outcome": "Fetched",
                            "sha256": prev_sha,
                            "http_status": 200, "final_url": None,
                            "content_type": "text/plain",
                            "bytes": len(prev_body_text),
                            "fetched_at": "2026-09-07T00:00:00Z", "attempts": 1})
    write_manifest(tmp_path, "2026-09-07", prev_records, collector_version="abc1234")

    # Seed current period (2026-09-14) with DIFFERENT content
    curr_body_text = "User-agent: *\nAllow: /\n"
    curr_records = []
    for domain in ["a.com", "b.com"]:
        curr_sha = store_body(tmp_path, curr_body_text.encode())
        curr_records.append({"domain": domain, "outcome": "Fetched",
                            "sha256": curr_sha,
                            "http_status": 200, "final_url": None,
                            "content_type": "text/plain",
                            "bytes": len(curr_body_text),
                            "fetched_at": "2026-09-14T00:00:00Z", "attempts": 1})
    write_manifest(tmp_path, "2026-09-14", curr_records, collector_version="abc1234")

    # Precondition: verify SHAs are different (not deduplicated)
    assert prev_sha != curr_sha, "Test requires different body content for each period"

    # Precondition: verify both blob files exist
    prev_blob = body_path(tmp_path, prev_sha)
    curr_blob = body_path(tmp_path, curr_sha)
    assert prev_blob.exists(), f"Previous period blob should exist: {prev_blob}"
    assert curr_blob.exists(), f"Current period blob should exist: {curr_blob}"

    # First: verify print succeeds when previous period blob is present
    exit_code = main(["print", "--root", str(tmp_path), "--period", "2026-09-14"])
    assert exit_code == 0, "Print should succeed with previous period blob intact"

    # Now delete ONLY the previous period's blob file
    prev_blob.unlink()
    assert not prev_blob.exists(), "Previous blob should be deleted"
    assert curr_blob.exists(), "Current blob should still exist (guard against test degradation)"

    # Second: verify print now fails because previous period blob is missing
    exit_code = main(["print", "--root", str(tmp_path), "--period", "2026-09-14"])
    assert exit_code != 0, "Print should fail when previous period blob is missing"
    captured = capsys.readouterr()
    assert "error:" in captured.err, "Should print error message"


def test_valid_previous_period_produces_change_wow_series(tmp_path):
    seed_config(tmp_path)
    seed_raw(tmp_path)
    # Print first period
    main(["print", "--root", str(tmp_path), "--period", "2026-09-14"])

    # Print second period - should have change_wow series since previous period exists
    records = []
    for domain, body in [("a.com", "User-agent: GPTBot\nDisallow: /\n"),
                         ("b.com", "User-agent: *\nAllow: /\n")]:
        records.append({"domain": domain, "outcome": "Fetched",
                        "sha256": store_body(tmp_path, body.encode()),
                        "http_status": 200, "final_url": None,
                        "content_type": "text/plain", "bytes": len(body),
                        "fetched_at": "2026-09-21T00:00:00Z", "attempts": 1})
    write_manifest(tmp_path, "2026-09-21", records, collector_version="abc1234")

    assert main(["print", "--root", str(tmp_path), "--period", "2026-09-21"]) == 0

    # Verify change_wow series appears
    series_rows = read_rows(tmp_path / "series.csv")
    change_wow_rows = [r for r in series_rows if r.get("series_id", "").startswith("change_wow")]
    assert len(change_wow_rows) > 0, "change_wow series should appear when previous period exists"


def seed_published(root, period="2026-09-14"):
    seed_config(root)
    seed_raw(root)
    assert main(["print", "--root", str(root), "--period", period]) == 0


def test_collect_refuses_a_period_that_is_already_published(tmp_path, monkeypatch, capsys):
    """Published evidence is not rewritten by accident.

    The ledger would still refuse to change the number, but the number would no
    longer be re-derivable from the raw tree, which is the promise the tree is
    there to keep.
    """
    import tallyhouse.cli as cli

    seed_published(tmp_path)
    manifest_before = (tmp_path / "raw" / "2026-09-14" / "manifest.json").read_bytes()

    called = []

    async def fake_collect(*args, **kwargs):
        called.append(kwargs)
        return []

    monkeypatch.setattr(cli, "collect_panel", fake_collect)

    assert main(["collect", "--root", str(tmp_path), "--period", "2026-09-14"]) != 0
    assert called == []
    assert (tmp_path / "raw" / "2026-09-14" / "manifest.json").read_bytes() == manifest_before
    assert "already published" in capsys.readouterr().err


def test_collect_force_overrides_the_refusal(tmp_path, monkeypatch):
    import tallyhouse.cli as cli

    seed_published(tmp_path)

    called = []

    async def fake_collect(*args, **kwargs):
        called.append(kwargs)
        return []

    monkeypatch.setattr(cli, "collect_panel", fake_collect)

    assert main(["collect", "--root", str(tmp_path), "--period", "2026-09-14",
                 "--force"]) == 0
    assert len(called) == 1


def test_collect_on_an_unpublished_period_proceeds(tmp_path, monkeypatch):
    import tallyhouse.cli as cli

    seed_config(tmp_path)
    called = []

    async def fake_collect(*args, **kwargs):
        called.append(kwargs)
        return []

    monkeypatch.setattr(cli, "collect_panel", fake_collect)

    assert main(["collect", "--root", str(tmp_path), "--period", "2026-09-14"]) == 0
    assert len(called) == 1
    assert called[0]["collector_version"]


def test_collector_version_failure_is_fatal(tmp_path, monkeypatch, capsys):
    """Refuse to collect rather than record unattributable evidence.

    The old code caught every exception and returned "unknown", so the one field
    that makes evidence attributable degraded silently in exactly the unattended
    cron path it exists for.
    """
    import tallyhouse.cli as cli

    seed_config(tmp_path)
    not_a_repo = tmp_path / "elsewhere"
    not_a_repo.mkdir()
    monkeypatch.setattr(cli, "REPO_DIR", not_a_repo)

    called = []

    async def fake_collect(*args, **kwargs):
        called.append(kwargs)
        return []

    monkeypatch.setattr(cli, "collect_panel", fake_collect)

    assert main(["collect", "--root", str(tmp_path), "--period", "2026-09-14"]) != 0
    assert called == []
    assert "CollectorVersionUnavailable" in capsys.readouterr().err


def test_collector_version_is_read_from_the_repository_not_the_cwd(tmp_path, monkeypatch):
    """Under cron the process cwd is not the repository."""
    import tallyhouse.cli as cli

    monkeypatch.chdir(tmp_path)
    assert cli.collector_version() == cli.collector_version(cli.REPO_DIR)
    assert len(cli.collector_version()) >= 7


def test_print_uses_the_collector_version_stamped_at_collect_time(tmp_path):
    """Evidence collected at commit A and printed at commit B is from A."""
    import tallyhouse.cli as cli

    seed_config(tmp_path)
    seed_raw(tmp_path)  # stamps "abc1234"

    assert main(["print", "--root", str(tmp_path), "--period", "2026-09-14"]) == 0
    row = read_rows(tmp_path / "prints.csv")[0]
    assert row["collector_version"] == "abc1234"
    assert row["collector_version"] != cli.collector_version()


def test_print_refuses_a_manifest_with_no_collector_version(tmp_path, capsys):
    import json as _json

    seed_config(tmp_path)
    seed_raw(tmp_path)
    path = tmp_path / "raw" / "2026-09-14" / "manifest.json"
    document = _json.loads(path.read_text())
    # Unattributable means the OBSERVATIONS carry no provenance. Deleting a
    # period-level field would no longer prove anything: provenance is derived
    # from the observations themselves.
    for observation in document["observations"]:
        observation.pop("collector_version", None)
    path.write_text(_json.dumps(document))

    assert main(["print", "--root", str(tmp_path), "--period", "2026-09-14"]) != 0
    assert "collector_version" in capsys.readouterr().err


def test_methodology_version_records_the_agent_set_and_the_parser(tmp_path):
    from importlib.metadata import version

    seed_config(tmp_path)
    seed_raw(tmp_path)
    assert main(["print", "--root", str(tmp_path), "--period", "2026-09-14"]) == 0
    row = read_rows(tmp_path / "prints.csv")[0]
    assert row["methodology_version"] == f"agents=1;protego={version('protego')}"


def test_agents_flag_selects_a_different_agent_set_and_bumps_methodology(tmp_path):
    seed_config(tmp_path)
    seed_raw(tmp_path)
    # v2 tracks an agent that a.com does not name, so the value differs too.
    (tmp_path / "agents" / "v2.json").write_text(
        json.dumps({"version": 2, "agents": ["ClaudeBot"]})
    )

    assert main(["print", "--root", str(tmp_path), "--period", "2026-09-14"]) == 0
    v1_row = read_rows(tmp_path / "prints.csv")[0]
    assert v1_row["value"] == "50.0"

    # Changing the agent set makes the series non-comparable, so it is a
    # restatement: a new vintage with a reason (spec 6.3).
    assert main(["print", "--root", str(tmp_path), "--period", "2026-09-14",
                 "--agents", "2", "--reason", "agent set v2"]) == 0
    rows = read_rows(tmp_path / "prints.csv")
    assert len(rows) == 2
    assert rows[1]["value"] == "0.0"
    assert rows[1]["methodology_version"].startswith("agents=2;")
    assert v1_row["methodology_version"].startswith("agents=1;")

    # And the derive stage reads the selected file too.
    assert main(["derive", "--root", str(tmp_path), "--period", "2026-09-14",
                 "--agents", "2"]) == 0
    verdicts = (tmp_path / "derived" / "verdicts.csv").read_text()
    assert "ClaudeBot" in verdicts
    assert "GPTBot" not in verdicts


def test_collect_derive_print_end_to_end(tmp_path, monkeypatch):
    """The real collect wiring, not a stubbed collect_panel.

    Exercises the whole chain a cron run takes: fetch, store, derive, print.
    """
    import httpx

    import tallyhouse.cli as cli

    seed_config(tmp_path)

    def handler(request):
        if request.url.host == "a.com":
            return httpx.Response(200, text="User-agent: GPTBot\nDisallow: /\n",
                                  headers={"content-type": "text/plain"})
        return httpx.Response(404, text="", headers={"content-type": "text/html"})

    class MockClient(httpx.AsyncClient):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(cli.httpx, "AsyncClient", MockClient)

    assert main(["collect", "--root", str(tmp_path), "--period", "2026-09-14"]) == 0
    assert main(["derive", "--root", str(tmp_path), "--period", "2026-09-14"]) == 0
    assert main(["print", "--root", str(tmp_path), "--period", "2026-09-14"]) == 0

    row = read_rows(tmp_path / "prints.csv")[0]
    # a.com blocks GPTBot; b.com has no robots.txt, which is conclusively not
    # blocking. Both are conclusive, so coverage is 100%.
    assert row["value"] == "50.0"
    assert row["denominator"] == "2"
    assert row["coverage"] == "100.0"
    assert row["collector_version"] == cli.collector_version()

    # b.com's 404 stored no blob, and only a.com's body is on disk.
    assert len(list(tmp_path.rglob("*.txt.gz"))) == 1

    # Collecting again now refuses: the period is published.
    assert main(["collect", "--root", str(tmp_path), "--period", "2026-09-14"]) != 0
