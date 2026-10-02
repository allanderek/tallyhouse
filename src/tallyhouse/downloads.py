"""The CSV downloads published alongside the site.

Spec 7 promises these as the project's only data interface, and there is one
principle behind how they are built: **a download of the ledger is the ledger**.
`prints.csv` and `series.csv` are served as the exact bytes committed to the
repository, not re-serialised from parsed rows. Re-serialising would introduce a
transformation that could quietly disagree with the record it claims to be — a
float reformatted, a quoted reason requoted — and the whole point of an
append-only ledger is that what was published is what you get.

The per-period files have no committed CSV to copy, so they are generated. They
are built from the same rows the site renders from, so a figure on a page and a
row in a download cannot come from different derivations.
"""

import csv
import io
import json
from pathlib import Path

# Which index a file belongs to. Empty means both: the two ledgers carry every
# index's rows and are filtered by index_id within the file. Everything else is
# one index's own, and must not be offered on the other's page -- the live panel
# is 1000 Tranco-qualified domains over a week, the historical panel is 611
# balanced-panel domains over a quarter, and a reader handed the wrong one has
# been handed the wrong population.
SHARED = ""

PANEL_FIELDS = ["rank", "domain"]
BALANCED_PANEL_FIELDS = ["rank_late", "rank_early", "domain"]
VERDICT_FIELDS = ["domain", "period", "agent", "stance"]


def _csv(fields: list[str], rows: list[dict]) -> str:
    # newline="" per the csv module's contract, and \r\n line endings because
    # that is what RFC 4180 specifies and what spreadsheets expect.
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _verbatim(path: Path) -> str | None:
    """The file's exact characters, line endings included.

    `newline=""` is what makes "verbatim" true. The ledger is written by the csv
    module, which ends lines with CRLF per RFC 4180; reading it with universal
    newlines silently rewrites those to LF, and the download then differs from
    the committed file it claims to be -- 20 bytes different on the first
    attempt, and invisible in any diff that ignores line endings.
    """
    if not path.exists():
        return None
    with path.open(newline="") as handle:
        return handle.read()


def catalogue(root: Path, data: dict) -> list[dict]:
    """Every published download: where it goes, what it is, and its content.

    A pure function of the committed tree and the already-loaded site data, so
    it adds no derivation of its own and cannot disagree with the pages.
    """
    period = data["prints"][-1]["period"] if data["prints"] else None
    entries = []

    for name, label, description in [
        (
            "prints.csv",
            "Headline ledger",
            "Every headline figure ever published, for both indices, including "
            "superseded vintages and the reason each was restated. Served as "
            "the exact bytes committed to the repository.",
        ),
        (
            "series.csv",
            "Series ledger",
            "Every sub-series: the per-crawler rates, effective and blanket "
            "blocking, coverage, the unreadable share and the like-for-like "
            "change. Same vintage rules as the headline ledger, same exact "
            "bytes.",
        ),
    ]:
        content = _verbatim(root / name)
        if content is not None:
            entries.append(
                {
                    "path": f"data/{name}",
                    "index_id": SHARED,
                    "label": label,
                    "description": description,
                    "content": content,
                }
            )

    if period is not None:
        panel_path = root / "panel" / f"{period[:4]}.json"
        if panel_path.exists():
            panel = json.loads(panel_path.read_text())
            ranks = panel.get("ranks", {})
            rows = [
                {"rank": ranks.get(domain, ""), "domain": domain}
                for domain in panel["domains"]
            ]
            rows.sort(key=lambda r: (r["rank"] == "", r["rank"], r["domain"]))
            entries.append(
                {
                    "path": f"data/panel-{period}.csv",
                    "index_id": data["index"]["id"],
                    "label": f"Panel, {period}",
                    "description": "The domains measured in this period, with "
                    "their Tranco rank. This is the denominator of every figure "
                    "published for the period.",
                    "content": _csv(PANEL_FIELDS, rows),
                }
            )

        if data["verdicts"]:
            entries.append(
                {
                    "path": f"data/verdicts-{period}.csv",
                    "index_id": data["index"]["id"],
                    "label": f"Verdicts, {period}",
                    "description": "One row per domain per tracked crawler: the "
                    "stance that domain's robots.txt takes toward that token. "
                    "The evidence behind every rate published for the period.",
                    "content": _csv(
                        VERDICT_FIELDS,
                        sorted(
                            (dict(v, period=v.get("period", period)) for v in data["verdicts"]),
                            key=lambda v: (v["domain"], v["agent"]),
                        ),
                    ),
                }
            )

    history = data.get("history") or {}
    balanced = root / "panel" / "historical.json"
    if history.get("id") and balanced.exists():
        panel = json.loads(balanced.read_text())
        ranks = panel.get("ranks", {})
        rows = [
            {
                "domain": domain,
                "rank_early": ranks.get(domain, {}).get("early", ""),
                "rank_late": ranks.get(domain, {}).get("late", ""),
            }
            for domain in panel.get("domains", [])
        ]
        if rows:
            entries.append(
                {
                    "path": "data/panel-historical.csv",
                    "index_id": history["id"],
                    "label": "Balanced panel",
                    "description": "The domains measured by the historical "
                    "index: those in the Tranco top 1000 at both ends of the "
                    "span, with their rank at each end. Fixed across every "
                    "period, which is what makes a change in that series a "
                    "change in behaviour rather than in membership.",
                    "content": _csv(BALANCED_PANEL_FIELDS, rows),
                }
            )

    return entries


def manifest(entries: list[dict]) -> list[dict]:
    """What the site needs to render a download link, without the content.

    The content is deliberately left behind: `verdicts-<period>.csv` is tens of
    thousands of rows, and pushing it through the generator to be handed
    straight back would cost a megabyte of string for nothing. The generator
    renders links and sizes; Python writes the files.
    """
    return [
        {
            "path": entry["path"],
            "indexId": entry["index_id"],
            "label": entry["label"],
            "description": entry["description"],
            "bytes": len(entry["content"].encode()),
            "rows": max(entry["content"].count("\n") - 1, 0),
        }
        for entry in entries
    ]


def files(entries: list[dict]) -> dict[str, str]:
    """The downloads as the {path: content} mapping write_site already takes."""
    return {entry["path"]: entry["content"] for entry in entries}
