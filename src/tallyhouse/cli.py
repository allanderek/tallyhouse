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

from tallyhouse.commoncrawl import robotstxt_parts
from tallyhouse.config import load_agents, load_panel, methodology_version
from tallyhouse.derive import derive_period, write_tables
from tallyhouse.historical import publish_series
from tallyhouse.ledger import LedgerConflict, latest
from tallyhouse.periods import (
    InvalidPeriod,
    is_within_window,
    parse_period,
    period_for,
    previous_period,
    window_end,
    window_start,
)
from tallyhouse.publish import INDEX_ID, build_print, record_print
from tallyhouse.run_collect import collect_panel
from tallyhouse.backfill import backfill, load_crawls, outstanding
from tallyhouse.balanced import balanced_panel, load_balanced_panel, write_balanced_panel
from tallyhouse.qualify import qualify, read_tranco, write_panel
from tallyhouse.render import RenderError, render_site
from tallyhouse.site import load_site_data, write_site
from tallyhouse.storage import manifest_collector_version, manifest_path

# The repository whose commit is the collector's version. Resolved from this
# file rather than the process working directory: under cron the cwd is whatever
# the crontab happened to leave it as, and asking git there answers about a
# different repository or about none at all.
REPO_DIR = Path(__file__).resolve().parents[2]


class CollectorVersionUnavailable(Exception):
    """Raised when the collector's own commit cannot be determined."""


def _utcnow() -> datetime:
    """The current instant, as a seam so tests need not depend on the real clock.

    Without this, any test that collects for a fixed period silently starts
    failing once that period's collection window closes in real time.
    """
    return datetime.now(timezone.utc)


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
        now = _utcnow()
        if not is_within_window(args.period, now) and not args.ignore_window:
            print(
                f"error: the collection window for {args.period} ran "
                f"{window_start(args.period):%Y-%m-%dT%H:%M:%SZ} to "
                f"{window_end(args.period):%Y-%m-%dT%H:%M:%SZ}; it is now "
                f"{now:%Y-%m-%dT%H:%M:%SZ}. Collecting outside the window labels "
                f"observations with a week they were not gathered in. Pass "
                f"--ignore-window if that is genuinely what you want.",
                file=sys.stderr,
            )
            return 1

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
        # fetched_at already records when each observation was gathered, so
        # lateness is derivable from the evidence rather than needing its own
        # field. A forced late collection must not yield a clean-looking print.
        stale = [
            o["domain"]
            for o in tables["observations"]
            if o.get("fetched_at")
            and not is_within_window(
                args.period, datetime.strptime(o["fetched_at"], "%Y-%m-%dT%H:%M:%SZ")
                .replace(tzinfo=timezone.utc)
            )
        ]
        if stale:
            print(
                f"warning: {len(stale)} of {len(tables['observations'])} observations "
                f"were gathered outside the {args.period} collection window",
                file=sys.stderr,
            )

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

        qualified, examined, excluded = asyncio.run(run())
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
            excluded=excluded,
        )
        # Not examined - qualified: a conclusive domain arriving after the
        # panel is full is surplus, not unobservable.
        print(
            f"panel: {len(qualified)} domains from {examined} candidates "
            f"({len(excluded)} excluded as unobservable) -> {path}"
        )
        return 0
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _cmd_balanced_panel(args) -> int:
    """Build the balanced panel for the historical index."""
    try:
        early = read_tranco(Path(args.early))
        late = read_tranco(Path(args.late))
        entries = balanced_panel(early, late)
        if not entries:
            print("error: the two endpoints share no domains", file=sys.stderr)
            return 1
        path = write_balanced_panel(
            Path(args.root), args.name,
            early_list_id=args.early_list_id, early_date=args.early_date,
            late_list_id=args.late_list_id, late_date=args.late_date,
            entries=entries, early_size=len(early), late_size=len(late),
        )
        churn = len(early) - len(entries)
        print(
            f"balanced panel: {len(entries)} domains present at both endpoints "
            f"({churn} of {len(early)} churned) -> {path}"
        )
        return 0
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _duckdb_connect(threads: int):
    """A DuckDB connection able to read Parquet over HTTP range requests.

    The retry settings are raised well above DuckDB's defaults, which give up
    after 0.1s, 0.4s and 1.6s. data.commoncrawl.org answers a sustained query
    with an occasional 503, and three tries inside two seconds treats a busy
    archive as a broken one — one such 503 cost a whole crawl on the first run.
    These give it about four minutes to recover instead, which is the right
    order of magnitude for a query that takes minutes itself. http_timeout is
    deliberately left at DuckDB's default: its documented unit and its actual
    unit could not be told apart by experiment, and a setting whose meaning is
    unclear is worse than the default it would replace.
    """
    import duckdb

    connection = duckdb.connect()
    connection.execute(
        f"INSTALL httpfs; LOAD httpfs; SET threads={int(threads)};"
        "SET http_retries=10; SET http_retry_wait_ms=2000;"
        "SET http_retry_backoff=1.5;"
    )
    return connection


def _cmd_backfill(args) -> int:
    """Collect the historical series from Common Crawl, one crawl at a time.

    Safe to interrupt and safe to re-run: crawls already collected are skipped,
    so a run that is refused partway costs one crawl rather than the whole
    backfill.
    """
    try:
        root = Path(args.root)
        crawls = load_crawls(root, args.series)
        if args.crawl:
            wanted = set(args.crawl)
            unknown = wanted - {c["crawl"] for c in crawls}
            if unknown:
                print(
                    f"error: {', '.join(sorted(unknown))} not in the {args.series} "
                    f"series. The series is data/crawls/{args.series}.json; add a "
                    f"crawl there if it belongs in the published series.",
                    file=sys.stderr,
                )
                return 1
            crawls = [c for c in crawls if c["crawl"] in wanted]
        domains = load_balanced_panel(root, args.panel)

        todo = outstanding(root, crawls)
        print(
            f"{len(crawls)} crawls in the {args.series} series, {len(todo)} "
            f"outstanding, {len(domains)} panel domains"
        )
        if args.dry_run:
            for entry in todo:
                print(f"  would collect {entry['crawl']} -> {entry['period']}")
            return 0
        if not todo:
            return 0

        cache = Path(args.cache)
        cache.mkdir(parents=True, exist_ok=True)
        version = collector_version()

        results = backfill(
            root,
            crawls,
            domains,
            connect=lambda: _duckdb_connect(args.threads),
            collector_version=version,
            parts_for=lambda crawl: robotstxt_parts(crawl, cache=cache),
            delay=args.delay,
            workers=args.workers,
            crawl_attempts=args.attempts,
        )
        failed = [r for r in results if r["status"] == "failed"]
        collected = [r for r in results if r["status"] == "collected"]
        print(f"backfill: {len(collected)} collected, {len(failed)} failed")
        for result in failed:
            print(f"  {result['crawl']}: {result['error']}", file=sys.stderr)
        # A failed crawl is not a broken run — it is a crawl the next run will
        # pick up — but the exit status has to say something happened, or cron
        # will report a partial backfill as a success.
        return 1 if failed else 0
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _cmd_historical_print(args) -> int:
    """Derive and publish every collected period of the historical series.

    Unlike the live index this runs over the whole series at once: the points
    are not arriving one per week, they are all sitting in raw/ already, and
    the like-for-like change on each one needs the point before it.
    """
    try:
        root = Path(args.root)
        crawls = load_crawls(root, args.series)
        agents = load_agents(root, args.agents)
        domains = load_balanced_panel(root, args.panel)
        results = publish_series(
            root,
            crawls,
            agents,
            panel_size=len(domains),
            methodology_version=methodology_version(args.agents),
            computed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            reason=args.reason,
        )
        missing = [r["period"] for r in results if r["status"] != "published"]
        published = len(results) - len(missing)
        print(f"historical: {published} of {len(results)} periods published")
        if missing:
            print(
                f"note: {', '.join(missing)} not collected; run `tallyhouse "
                f"backfill` to fill the gaps, then print again",
                file=sys.stderr,
            )
        return 0
    except LedgerConflict as exc:
        print(f"refusing to change a published number: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _cmd_generate(args) -> int:
    """Render the site from committed data.

    A pure function of what is in the repository: the generator never opens a
    socket, and the numbers it shows are read back from the ledger rather than
    recomputed, so a page cannot disagree with the published record.
    """
    try:
        program = Path(args.program)
        if not program.exists():
            print(
                f"error: {program} does not exist. Build it first with:\n"
                f"  cd generate && elm make src/Site.elm --optimize --output={program}",
                file=sys.stderr,
            )
            return 1
        # A compiled program older than its sources renders a stale site with
        # no error at all — the same silently-wrong-output failure this project
        # refuses elsewhere. The fix is one command, so say it.
        sources = sorted(Path("generate/src").rglob("*.elm")) if Path("generate/src").exists() else []
        newest = max((f.stat().st_mtime for f in sources), default=0)
        if sources and program.stat().st_mtime < newest:
            stale = [f.name for f in sources if f.stat().st_mtime > program.stat().st_mtime]
            print(
                f"error: {program} is older than {', '.join(stale)}. It would render a "
                f"stale site. Rebuild with:\n"
                f"  cd generate && elm make src/Site.elm --optimize --output={program.name}",
                file=sys.stderr,
            )
            return 1

        data = load_site_data(Path(args.root))
        if not data["prints"]:
            print("error: no published prints to render", file=sys.stderr)
            return 1
        files = render_site(program.read_text(), data)
        written = write_site(files, Path(args.out))
        print(f"site: {len(written)} files -> {args.out}")
        return 0
    except RenderError as exc:
        print(f"error: the generator failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tallyhouse")
    sub = parser.add_subparsers(dest="command", required=True)

    back = sub.add_parser("backfill", help="collect the historical series from Common Crawl")
    back.add_argument("--root", default="data")
    back.add_argument("--series", default="historical",
                      help="crawl series in data/crawls/<series>.json")
    back.add_argument("--panel", default="historical",
                      help="balanced panel in data/panel/<panel>.json")
    back.add_argument("--crawl", action="append",
                      help="collect only this crawl (repeatable); must be in the series")
    back.add_argument("--delay", type=int, default=60,
                      help="seconds to wait between crawls")
    back.add_argument("--workers", type=int, default=12,
                      help="concurrent WARC range requests within one crawl")
    back.add_argument("--threads", type=int, default=8, help="DuckDB threads")
    back.add_argument("--attempts", type=int, default=2,
                      help="attempts per crawl before giving up on it for this run")
    back.add_argument("--cache", default=".cache/ccpaths",
                      help="where to keep downloaded index path lists")
    back.add_argument("--dry-run", action="store_true", dest="dry_run",
                      help="report what would be collected and stop")

    bal = sub.add_parser("balanced-panel", help="build a balanced panel from two Tranco endpoints")
    bal.add_argument("--root", default="data")
    bal.add_argument("--name", default="historical")
    bal.add_argument("--early", required=True, help="early Tranco rank,domain CSV")
    bal.add_argument("--early-list-id", required=True, dest="early_list_id")
    bal.add_argument("--early-date", required=True, dest="early_date")
    bal.add_argument("--late", required=True, help="late Tranco rank,domain CSV")
    bal.add_argument("--late-list-id", required=True, dest="late_list_id")
    bal.add_argument("--late-date", required=True, dest="late_date")

    hist = sub.add_parser("historical-print",
                          help="publish the historical series from collected crawls")
    hist.add_argument("--root", default="data")
    hist.add_argument("--series", default="historical")
    hist.add_argument("--panel", default="historical")
    hist.add_argument("--agents", type=int, default=2)
    hist.add_argument("--reason", default=None,
                      help="required to restate an already-published number")

    gen = sub.add_parser("generate", help="render the static site from committed data")
    gen.add_argument("--root", default="data")
    gen.add_argument("--out", default="site")
    gen.add_argument("--program", default="generate/site.js",
                     help="compiled output of `elm make src/Site.elm`")

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
        child.add_argument("--period", default=period_for(_utcnow()))
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
            child.add_argument(
                "--ignore-window",
                action="store_true",
                dest="ignore_window",
                help="collect outside this period's 72-hour collection window",
            )

    args = parser.parse_args(argv)
    if args.command == "qualify":
        return _cmd_qualify(args)
    if args.command == "balanced-panel":
        return _cmd_balanced_panel(args)
    if args.command == "backfill":
        return _cmd_backfill(args)
    if args.command == "historical-print":
        return _cmd_historical_print(args)
    if args.command == "generate":
        return _cmd_generate(args)

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
