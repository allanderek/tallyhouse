"""The append-only ledger.

This module is the only place allowed to decide that a published number may
change, and it never lets one change silently. Values are stored as strings
so that a round-trip through the file cannot alter them.
"""

import csv
from pathlib import Path

PRINT_FIELDS = [
    "index_id",
    "period",
    "vintage",
    "value",
    "denominator",
    "coverage",
    "methodology_version",
    "collector_version",
    "computed_at",
    "reason",
]

_COMPARED_FIELDS = ("value", "denominator", "coverage")


class LedgerConflict(Exception):
    """Raised when a published value would change without a stated reason."""


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _matching(rows: list[dict], key: dict) -> list[dict]:
    return [r for r in rows if all(r[k] == v for k, v in key.items())]


def latest(path: Path, key: dict) -> dict | None:
    matches = _matching(read_rows(path), key)
    if not matches:
        return None
    return max(matches, key=lambda r: int(r["vintage"]))


def append_row(path: Path, key: dict, row: dict, *, reason: str | None = None) -> dict | None:
    """Append a row, enforcing the vintage rules.

    Returns the appended row, or None when the value is unchanged.
    """
    existing = latest(path, key)
    if existing is not None:
        if all(existing[f] == str(row[f]) for f in _COMPARED_FIELDS):
            return None
        if not reason:
            raise LedgerConflict(
                f"{key} is published as {existing['value']} and would become "
                f"{row['value']}. Supply a reason to append a new vintage."
            )
        vintage = int(existing["vintage"]) + 1
    else:
        vintage = 1

    # Key fields not already in PRINT_FIELDS (e.g. series_id) are appended, so
    # the same ledger code serves both prints.csv and series.csv.
    fields = list(dict.fromkeys([*PRINT_FIELDS, *key]))
    record = {f: "" for f in fields}
    record.update({k: str(v) for k, v in key.items()})
    record.update({k: str(v) for k, v in row.items()})
    record["vintage"] = str(vintage)
    record["reason"] = reason or ""

    is_new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if is_new:
            writer.writeheader()
        writer.writerow(record)
    return record
