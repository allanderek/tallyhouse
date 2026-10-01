"""Derive classified tables from retained raw evidence.

Pure with respect to the network and the clock: given the same raw/ tree and
the same agent set, it produces identical output forever.
"""

import csv
from pathlib import Path

from tallyhouse.config import load_removals, removals_in_effect
from tallyhouse.constants import CONCLUSIVE_OUTCOMES
from tallyhouse.parse import blanket_stance, classify
from tallyhouse.storage import load_body, read_manifest

VERDICT_FIELDS = ["domain", "period", "agent", "stance"]
FETCH_FIELDS = [
    "domain", "period", "outcome", "http_status", "final_url",
    "content_type", "bytes", "sha256", "fetched_at", "attempts",
]


def derive_period(root: Path, period: str, agents: list[str]) -> dict:
    # Invariant: the manifest holds exactly one record per domain per period.
    # collect enforces it by keying its merge on domain, and everything
    # downstream depends on it -- `blanket` is a dict keyed by domain, so a
    # duplicate would silently overwrite rather than double-count, while
    # `verdicts` is a list, so the same duplicate WOULD double-count there. The
    # two tables would then disagree about the same domain.
    #
    # A domain withdrawn at its owner's request is not part of this period's
    # population at all, so its observations are dropped here rather than
    # filtered by each caller. Dropping them in one place is deliberate: when
    # the denominator excluded them but the numerator did not, coverage came out
    # at 200%. One decision about who is being measured, made once.
    withdrawn = removals_in_effect(load_removals(root), period)
    observations = sorted(
        (r for r in read_manifest(root, period) if r["domain"] not in withdrawn),
        key=lambda r: r["domain"],
    )
    verdicts: list[dict] = []
    blanket: dict[str, str] = {}

    for record in observations:
        if record["outcome"] not in CONCLUSIVE_OUTCOMES:
            continue
        # Only a Fetched outcome has a body that is this domain's robots.txt.
        # A NoRobotsTxt (404/410) outcome is a conclusive *absence* of policy, so
        # it is parsed as the empty file no matter what bytes the server sent
        # back with the error -- some serve a full HTML page, and a few of those
        # contain text that would otherwise parse as directives. collect already
        # declines to store those bodies; this is the second of two locks on the
        # same door, because the consequence of getting it wrong is a domain
        # entering the targeted headline numerator for having no robots.txt.
        sha = record.get("sha256") if record["outcome"] == "Fetched" else None
        # errors="replace" rather than "strict": a robots.txt is not required to
        # be valid UTF-8, and a mojibake comment must not fail a whole period's
        # derivation. Undecodable bytes become U+FFFD, which parses as ordinary
        # text and can never form a directive.
        body = load_body(root, sha).decode("utf-8", errors="replace") if sha else ""
        blanket[record["domain"]] = blanket_stance(body)
        for agent in agents:
            verdicts.append(
                {
                    "domain": record["domain"],
                    "period": period,
                    "agent": agent,
                    "stance": classify(body, agent),
                }
            )

    return {"observations": observations, "verdicts": verdicts, "blanket": blanket}


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_tables(out_dir: Path, period: str, tables: dict) -> None:
    verdicts = sorted(tables["verdicts"], key=lambda r: (r["domain"], r["agent"]))
    _write_csv(out_dir / "verdicts.csv", VERDICT_FIELDS, verdicts)

    fetches = [dict(o, period=period) for o in tables["observations"]]
    _write_csv(out_dir / "fetches.csv", FETCH_FIELDS, fetches)
