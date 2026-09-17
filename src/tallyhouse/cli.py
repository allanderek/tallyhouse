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

from tallyhouse.config import load_agents, load_panel, methodology_version
from tallyhouse.derive import derive_period, write_tables
from tallyhouse.ledger import LedgerConflict, latest
from tallyhouse.periods import InvalidPeriod, parse_period, period_for, previous_period
from tallyhouse.publish import INDEX_ID, build_print, record_print
from tallyhouse.run_collect import collect_panel
from tallyhouse.qualify import qualify, read_tranco, write_panel
from tallyhouse.storage import manifest_collector_version, manifest_path

# The repository whose commit is the collector's version. Resolved from this
# file rather than the process working directory: under cron the cwd is whatever
# the crontab happened to leave it as, and asking git there answers about a
# different repository or about none at all.
REPO_DIR = Path(__file__).resolve().parents[2]


class CollectorVersionUnavailable(Exception):
    """Raised when the collector's own commit cannot be determined."""


def collector_version(repo_dir: Path | None = None) -> str:
    """The git commit of the collector, stamped into evidence at collect time.

    Failure is fatal rather than a fallback string. This field exists precisely
    for the unattended path, so a bare except returning "unknown" would let the
    one field that makes evidence attributable degrade silently in the only
    situation it was added for.
    """
    repo_dir = REPO_DIR if repo_dir is None else repo_dir
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo_dir), "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CollectorVersionUnavailable(
            f"cannot determine the collector's commit from {repo_dir}: {exc}. "
            f"Refusing to record unattributable evidence."
        ) from exc


def _load(root: Path, period: str, agents_version: int):
    year = parse_period(period).year
    panel = load_panel(root, year)
    agents = load_agents(root, agents_version)
    return panel, agents


def _already_published(root: Path, period: str) -> bool:
    return latest(root / "prints.csv", {"index_id": INDEX_ID, "period": period}) is not None


def _cmd_collect(args) -> int:
    try:
        root = Path(args.root)
        # Collecting again for a period whose number is already published would
        # rewrite the evidence behind it. The ledger would still refuse to change
        # the number, but the number would no longer be re-derivable, which is the
        # promise the raw tree exists to keep.
        if not args.force and _already_published(root, args.period):
            print(
                f"error: {args.period} is already published in prints.csv. "
                f"Collecting again would rewrite the evidence behind a published "
                f"number. Pass --force if that is genuinely what you want.",
                file=sys.stderr,
            )
            return 1
        panel, _ = _load(root, args.period, args.agents)
        version = collector_version()

        async def run():
            async with httpx.AsyncClient(timeout=20.0) as client:
                await collect_panel(
                    root,
                    args.period,
                    panel.domains,
                    client=client,
                    collector_version=version,
                )

        asyncio.run(run())
        return 0
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _cmd_derive(args) -> int:
    try:
        root = Path(args.root)
        _, agents = _load(root, args.period, args.agents)
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
        panel, agents = _load(root, args.period, args.agents)
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
            methodology_version=methodology_version(args.agents),
            # Read from the manifest, not recomputed here: the evidence was
            # produced by the collector as it stood at collection time, which is
            # not necessarily the commit this print is running from.
            collector_version=manifest_collector_version(root, args.period),
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


def _cmd_qualify(args) -> int:
    """Build the frozen annual panel from a Tranco list.

    Panel construction is methodology, not setup: the panel is the denominator
    of every published number. Running this again over the same Tranco list
    reproduces the same panel, modulo sites that changed their behaviour.
    """
    try:
        root = Path(args.root)
        candidates = read_tranco(Path(args.tranco))

        async def run():
            async with httpx.AsyncClient(timeout=20.0) as client:
                return await qualify(
                    candidates,
                    client=client,
                    size=args.size,
                    concurrency=args.concurrency,
                )

        qualified, examined = asyncio.run(run())
        if len(qualified) < args.size:
            print(
                f"error: only {len(qualified)} of {args.size} domains qualified "
                f"from {examined} candidates; supply a longer Tranco list",
                file=sys.stderr,
            )
            return 1

        path = write_panel(
            root,
            args.year,
            tranco_list_id=args.list_id,
            qualified=qualified,
            examined=examined,
        )
        rejected = examined - len(qualified)
        print(
            f"panel: {len(qualified)} domains from {examined} candidates "
            f"({rejected} rejected as unobservable) -> {path}"
        )
        return 0
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tallyhouse")
    sub = parser.add_subparsers(dest="command", required=True)

    qual = sub.add_parser("qualify", help="build the frozen annual panel")
    qual.add_argument("--root", default="data")
    qual.add_argument("--tranco", required=True, help="path to a Tranco rank,domain CSV")
    qual.add_argument("--list-id", required=True, dest="list_id")
    qual.add_argument("--year", type=int, required=True)
    qual.add_argument("--size", type=int, default=1000)
    qual.add_argument("--concurrency", type=int, default=8)

    for name in ("collect", "derive", "print"):
        child = sub.add_parser(name)
        child.add_argument("--root", default="data")
        child.add_argument("--period", default=period_for(datetime.now(timezone.utc)))
        child.add_argument(
            "--agents",
            type=int,
            default=1,
            help="agent-set version to use (data/agents/v<n>.json)",
        )
        if name == "print":
            child.add_argument("--reason", default=None)
        if name == "collect":
            child.add_argument(
                "--force",
                action="store_true",
                help="collect even though this period is already published",
            )

    args = parser.parse_args(argv)
    if args.command == "qualify":
        return _cmd_qualify(args)

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
