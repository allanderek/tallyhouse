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
    write_manifest(root, "2026-09-14", records)


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
    ])
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
    from tallyhouse.storage import manifest_path
    import os

    seed_config(tmp_path)
    seed_raw(tmp_path)
    # Do a first print
    main(["print", "--root", str(tmp_path), "--period", "2026-09-14"])

    # Now print a second period with different content
    # This ensures the second period can fully derive, but the first period
    # will need its original bodies
    records = []
    for domain, body in [("a.com", "Different body for a.com\n"),
                         ("b.com", "Different body for b.com\n")]:
        records.append({"domain": domain, "outcome": "Fetched",
                        "sha256": store_body(tmp_path, body.encode()),
                        "http_status": 200, "final_url": None,
                        "content_type": "text/plain", "bytes": len(body),
                        "fetched_at": "2026-09-21T00:00:00Z", "attempts": 1})
    write_manifest(tmp_path, "2026-09-21", records)

    # Now delete ONLY the body directory to simulate corruption
    # This makes both periods underiable, testing that the code properly
    # fails when accessing previous period
    import shutil
    bodies_dir = tmp_path / "raw" / "bodies"
    if bodies_dir.exists():
        shutil.rmtree(bodies_dir)

    # Printing the second period should fail when deriving it
    # (because its bodies are also missing)
    exit_code = main(["print", "--root", str(tmp_path), "--period", "2026-09-21"])
    assert exit_code != 0
    captured = capsys.readouterr()
    # Should fail with a FileNotFoundError about blob, not "never collected"
    assert "error:" in captured.err
    assert "was never collected" not in captured.err


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
    write_manifest(tmp_path, "2026-09-21", records)

    assert main(["print", "--root", str(tmp_path), "--period", "2026-09-21"]) == 0

    # Verify change_wow series appears
    series_rows = read_rows(tmp_path / "series.csv")
    change_wow_rows = [r for r in series_rows if r.get("series_id", "").startswith("change_wow")]
    assert len(change_wow_rows) > 0, "change_wow series should appear when previous period exists"
