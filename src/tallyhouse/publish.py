"""Assemble a candidate print and record it in the ledgers.

PROVISIONAL_COVERAGE_THRESHOLD is a placeholder pending calibration from a
real collection run, per the spec. Changing it changes which prints are
labelled provisional, so treat it as methodology.
"""

from pathlib import Path

from tallyhouse.compute import (
    blanket_rate,
    conclusive_domains,
    coverage,
    effective_rate,
    like_for_like_change,
    per_agent_rates,
    targeted_rate,
)
from tallyhouse.ledger import LedgerConflict, append_row, would_conflict

INDEX_ID = "agent-accessibility"
PROVISIONAL_COVERAGE_THRESHOLD = 97.0


def build_print(
    tables: dict,
    prev_tables: dict | None,
    panel_size: int,
    *,
    methodology_version: str,
    collector_version: str,
    computed_at: str,
) -> dict:
    conclusive = conclusive_domains(tables["observations"])
    cov = coverage(tables["observations"], panel_size)
    meta = {
        "denominator": len(conclusive),
        "coverage": cov,
        "methodology_version": methodology_version,
        "collector_version": collector_version,
        "computed_at": computed_at,
    }

    headline = dict(meta, value=targeted_rate(tables["verdicts"], conclusive))

    series = {
        "effective": dict(
            meta,
            value=effective_rate(tables["verdicts"], tables["blanket"], conclusive),
        ),
        "blanket": dict(meta, value=blanket_rate(tables["blanket"], conclusive)),
        "coverage": dict(meta, value=cov),
    }
    for agent, rate in per_agent_rates(tables["verdicts"], conclusive).items():
        series[f"agent:{agent}"] = dict(meta, value=rate)

    if prev_tables is not None:
        change = like_for_like_change(
            prev_tables["verdicts"],
            conclusive_domains(prev_tables["observations"]),
            tables["verdicts"],
            conclusive,
        )
        if change is not None:
            series["change_wow"] = dict(meta, value=change)

    return {
        "headline": headline,
        "series": series,
        "provisional": cov < PROVISIONAL_COVERAGE_THRESHOLD,
    }


def record_print(root: Path, period: str, built: dict, *, reason: str | None = None) -> None:
    """Record print to both prints.csv and series.csv with atomicity and idempotency.

    Args:
        root: Directory containing the ledger CSV files
        period: Period identifier (e.g., "2026-09-14")
        built: Dict from build_print() with headline, series, and provisional flag
        reason: Optional explanation if any value has changed. Required if any row
                (headline or series) would change from its last published value.

    Raises:
        LedgerConflict: If any intended row would change without a reason being supplied.
                       This is raised before any row is written to either ledger,
                       ensuring the two-phase validate-then-write contract.

    Two-phase contract: All rows (headline plus every series entry) are first validated
    against their current ledger state. Only if all checks pass are any rows written.
    If any conflict is detected, LedgerConflict is raised before the first write,
    preventing partial ledger corruption across the two files.
    """
    root.mkdir(parents=True, exist_ok=True)

    # Phase 1: validate all rows before writing any
    # Collect all conflicts across headline and series, then raise once with the complete list.
    conflicts = []

    # Check headline
    headline_key = {"index_id": INDEX_ID, "period": period}
    headline_with_provisional = dict(built["headline"], provisional="true" if built["provisional"] else "false")
    if would_conflict(root / "prints.csv", headline_key, headline_with_provisional, reason=reason):
        conflicts.append(("prints", headline_key))

    # Check all series
    for series_id, row in sorted(built["series"].items()):
        series_key = {"index_id": INDEX_ID, "period": period, "series_id": series_id}
        series_with_provisional = dict(row, provisional="true" if built["provisional"] else "false")
        if would_conflict(root / "series.csv", series_key, series_with_provisional, reason=reason):
            conflicts.append(("series", series_key))

    if conflicts:
        conflict_list = ", ".join(f"{ledger}:{key}" for ledger, key in conflicts)
        raise LedgerConflict(
            f"The following rows would change without a reason: {conflict_list}"
        )

    # Phase 2: write all rows
    append_row(
        root / "prints.csv",
        headline_key,
        headline_with_provisional,
        reason=reason,
    )
    # Broadcasting a single reason across all series rows is safe: append_row
    # short-circuits any row unchanged on every compared field (value,
    # denominator, coverage, provisional), so the reason only lands on rows that
    # actually moved.
    for series_id, row in sorted(built["series"].items()):
        series_with_provisional = dict(row, provisional="true" if built["provisional"] else "false")
        append_row(
            root / "series.csv",
            {"index_id": INDEX_ID, "period": period, "series_id": series_id},
            series_with_provisional,
            reason=reason,
        )
