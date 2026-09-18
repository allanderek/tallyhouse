"""Assembles the data the site generator renders from.

The generator is a pure function of committed data, so everything it needs is
gathered here and handed over as one JSON document. Nothing is computed during
rendering: the numbers on the site are the numbers in the ledger, read back
rather than recalculated, so a page can never disagree with the published record.
"""

import csv
import json
from pathlib import Path

from tallyhouse.ledger import read_rows

INDEX_ID = "agent-accessibility"


def _latest_by(rows: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
    """Keep only the highest vintage of each key — what the site should show."""
    best: dict[tuple, dict] = {}
    for row in rows:
        key = tuple(row[f] for f in key_fields)
        current = best.get(key)
        if current is None or int(row["vintage"]) > int(current["vintage"]):
            best[key] = row
    return list(best.values())


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def load_site_data(root: Path, *, index_id: str = INDEX_ID) -> dict:
    """Everything the generator needs, as plain JSON-serialisable data."""
    prints = [r for r in read_rows(root / "prints.csv") if r["index_id"] == index_id]
    series = [r for r in read_rows(root / "series.csv") if r["index_id"] == index_id]

    latest_prints = sorted(
        _latest_by(prints, ("index_id", "period")), key=lambda r: r["period"]
    )
    latest_series = _latest_by(series, ("index_id", "period", "series_id"))

    # Vintages matter: a restated period must be visible as restated, so the
    # superseded rows travel too rather than being silently dropped.
    superseded = [
        r for r in prints
        if not any(l["period"] == r["period"] and l["vintage"] == r["vintage"]
                   for l in latest_prints)
    ]

    verdicts = _read_csv(root / "derived" / "verdicts.csv")
    fetches = _read_csv(root / "derived" / "fetches.csv")

    panel_path = root / "panel" / "2026.json"
    panel = json.loads(panel_path.read_text()) if panel_path.exists() else {}

    return {
        "index": {
            "id": index_id,
            "title": "Agent Accessibility Index",
            "question": "How many of the top 1000 websites tell AI crawlers to stay out?",
        },
        "prints": latest_prints,
        "superseded": sorted(superseded, key=lambda r: (r["period"], r["vintage"])),
        "series": sorted(latest_series, key=lambda r: (r["period"], r["series_id"])),
        "panel": {
            "tranco_list_id": panel.get("tranco_list_id"),
            "captured": panel.get("captured"),
            "size": len(panel.get("domains", [])),
            "qualification": panel.get("qualification", {}),
        },
        "verdicts": verdicts,
        "fetches": fetches,
    }


def write_site(files: dict[str, str], out: Path) -> list[Path]:
    """Write the rendered site. Python does all file writing; Elm never does."""
    written = []
    for path, content in sorted(files.items()):
        target = out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        written.append(target)
    return written
