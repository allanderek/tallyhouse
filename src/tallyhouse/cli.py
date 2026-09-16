"""Command line entry points for the pipeline stages.

Each stage is separately runnable so that a failed collect never corrupts
published data, and derive/print can be re-run freely at any time.
"""

import argparse
import asyncio
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

from tallyhouse.config import load_agents, load_panel
from tallyhouse.derive import derive_period, write_tables
from tallyhouse.ledger import LedgerConflict
from tallyhouse.periods import InvalidPeriod, parse_period, period_for, previous_period
from tallyhouse.publish import build_print, record_print
from tallyhouse.run_collect import collect_panel
from tallyhouse.storage import manifest_path

METHODOLOGY_VERSION = "1"


def _collector_version() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def _load(root: Path, period: str):
    year = parse_period(period).year
    panel = load_panel(root, year)
    agents = load_agents(root, 1)
    return panel, agents


def _cmd_collect(args) -> int:
    try:
        root = Path(args.root)
        panel, _ = _load(root, args.period)

        async def run():
            async with httpx.AsyncClient(timeout=20.0) as client:
                await collect_panel(root, args.period, panel.domains, client=client)

        asyncio.run(run())
        return 0
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _cmd_derive(args) -> int:
    try:
        root = Path(args.root)
        _, agents = _load(root, args.period)
        tables = derive_period(root, args.period, agents)
        write_tables(root / "derived", args.period, tables)
        return 0
    except FileNotFoundError as exc:
        # Check if this is a "period never collected" error
        root = Path(args.root)
        mfst_path = manifest_path(root, args.period)
        if not mfst_path.exists():
            print(f"error: period {args.period} was never collected", file=sys.stderr)
        else:
            print(f"error: FileNotFoundError: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _cmd_print(args) -> int:
    try:
        root = Path(args.root)
        panel, agents = _load(root, args.period)
        tables = derive_period(root, args.period, agents)

        previous = previous_period(args.period)
        # Explicitly check if previous period's manifest exists before deriving
        prev_mfst_path = manifest_path(root, previous)
        prev_tables = None
        if prev_mfst_path.exists():
            # Manifest exists, so derive it (may fail if blob is corrupt)
            prev_tables = derive_period(root, previous, agents)

        built = build_print(
            tables,
            prev_tables,
            panel_size=len(panel.domains),
            methodology_version=METHODOLOGY_VERSION,
            collector_version=_collector_version(),
            computed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        try:
            record_print(root, args.period, built, reason=args.reason)
        except LedgerConflict as exc:
            print(f"refusing to change a published number: {exc}", file=sys.stderr)
            return 1
        if built["provisional"]:
            print("warning: coverage below threshold, print marked provisional", file=sys.stderr)
        return 0
    except FileNotFoundError as exc:
        # Check if this is a "period never collected" error
        root = Path(args.root)
        mfst_path = manifest_path(root, args.period)
        if not mfst_path.exists():
            print(f"error: period {args.period} was never collected", file=sys.stderr)
        else:
            print(f"error: FileNotFoundError: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tallyhouse")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("collect", "derive", "print"):
        child = sub.add_parser(name)
        child.add_argument("--root", default="data")
        child.add_argument("--period", default=period_for(datetime.now(timezone.utc)))
        if name == "print":
            child.add_argument("--reason", default=None)

    args = parser.parse_args(argv)
    try:
        parse_period(args.period)
    except InvalidPeriod as exc:
        parser.error(str(exc))

    return {
        "collect": _cmd_collect,
        "derive": _cmd_derive,
        "print": _cmd_print,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
