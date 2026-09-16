"""The append-only ledger.

This module is the only place allowed to decide that a published number may
change, and it never lets one change silently. Values are stored as strings
so that a round-trip through the file cannot alter them.

VINTAGE SEMANTICS: A vintage represents a point at which the published number
(value, denominator, coverage) was established under a particular methodology.
If a later methodology bump reproduces the same number, it does NOT create a
new vintage—instead, it leaves a record showing the earlier methodology produced
this value. This avoids vintage churn (52 periods × every bump = churning ledger)
and provides useful provenance: after a methodology change, the series shows
exactly which periods actually moved and which didn't.
"""

import csv
import io
import os
from pathlib import Path

PRINT_FIELDS = [
    "index_id",
    "period",
    "vintage",
    "value",
    "denominator",
    "coverage",
    "provisional",
    "methodology_version",
    "collector_version",
    "computed_at",
    "reason",
]

# Only these fields determine whether a value has actually changed.
# methodology_version and collector_version record the context under which
# THIS vintage's value was first established, but do not trigger a new vintage
# if a later methodology produces the same result.
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

    # Validate all vintages before finding max—fail loudly on corruption.
    for row in matches:
        if "vintage" not in row or not row["vintage"]:
            raise LedgerConflict(
                f"Ledger {path} contains a row with missing or empty vintage: {row}. "
                f"The ledger may be corrupted and requires manual inspection."
            )
        try:
            int(row["vintage"])
        except ValueError:
            raise LedgerConflict(
                f"Ledger {path} contains a row with non-integer vintage '{row['vintage']}': {row}. "
                f"The ledger may be corrupted and requires manual inspection."
            )

    return max(matches, key=lambda r: int(r["vintage"]))


def would_conflict(path: Path, key: dict, row: dict, *, reason: str | None = None) -> bool:
    """Check if appending this row would conflict with an existing published value.

    Returns True if an existing row exists for the key, differs on any _COMPARED_FIELDS,
    and no reason was supplied. This is the single authoritative definition of conflict.
    """
    existing = latest(path, key)
    if existing is None:
        return False
    # Row is unchanged on all compared fields
    if all(existing[f] == str(row[f]) for f in _COMPARED_FIELDS):
        return False
    # Row differs and no reason supplied
    return not reason


def append_row(path: Path, key: dict, row: dict, *, reason: str | None = None) -> dict | None:
    """Append a row, enforcing the vintage rules.

    Returns the appended row, or None when the value is unchanged.
    """
    # Key fields not already in PRINT_FIELDS (e.g. series_id) are appended, so
    # the same ledger code serves both prints.csv and series.csv.
    fields = list(dict.fromkeys([*PRINT_FIELDS, *key]))

    # If file has content, validate that the key shape matches the existing header
    # BEFORE calling latest() to avoid KeyError when trying to match with wrong key shape.
    # Mixed key shapes would silently misalign columns with no error.
    if path.exists() and path.stat().st_size > 0:
        existing_header = _read_header(path)
        if existing_header != fields:
            raise LedgerConflict(
                f"Ledger {path} header mismatch. Expected {fields}, "
                f"but file has {existing_header}. "
                f"Key shape must remain consistent (misaligned rows would corrupt the ledger)."
            )

    existing = latest(path, key)
    if existing is not None:
        if all(existing[f] == str(row[f]) for f in _COMPARED_FIELDS):
            return None
        if would_conflict(path, key, row, reason=reason):
            raise LedgerConflict(
                f"{key} is published as {existing['value']} and would become "
                f"{row['value']}. Supply a reason to append a new vintage."
            )
        vintage = int(existing["vintage"]) + 1
    else:
        vintage = 1

    record = {f: "" for f in fields}
    record.update({k: str(v) for k, v in key.items()})
    record.update({k: str(v) for k, v in row.items()})
    record["vintage"] = str(vintage)
    record["reason"] = reason or ""

    # Treat zero-byte file as new (header not written, needs to be added).
    # This can happen if fsync widened the window for empty file creation.
    is_new = not path.exists() or path.stat().st_size == 0

    path.parent.mkdir(parents=True, exist_ok=True)

    # Format the row into text in memory, then write atomically with fsync.
    # This removes the multi-write window and ensures acknowledged data is
    # really on disk, protecting against corruption from mid-write crashes.
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields)
    if is_new:
        writer.writeheader()
    writer.writerow(record)
    text = buffer.getvalue()

    with path.open("a", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    return record


def _read_header(path: Path) -> list[str]:
    """Read the CSV header from a file. Returns empty list if file is empty or has no header."""
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="") as handle:
        reader = csv.reader(handle)
        try:
            return next(reader, [])
        except StopIteration:
            return []
