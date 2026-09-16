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
from tallyhouse.ledger import LedgerConflict, append_row, latest

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
    """Record print to both ledgers, validating all before writing any.

    This two-phase contract prevents partial writes: if any row would conflict,
    LedgerConflict is raised before a single row is written to either ledger.
    """
    root.mkdir(parents=True, exist_ok=True)

    # Phase 1: validate all rows before writing any
    # Check headline
    headline_key = {"index_id": INDEX_ID, "period": period}
    headline_with_provisional = dict(built["headline"], provisional="true" if built["provisional"] else "false")
    existing_headline = latest(root / "prints.csv", headline_key)
    if existing_headline is not None:
        if existing_headline["value"] != str(headline_with_provisional["value"]) and not reason:
            raise LedgerConflict(
                f"{headline_key} is published as {existing_headline['value']} and would become "
                f"{headline_with_provisional['value']}. Supply a reason to append a new vintage."
            )

    # Check all series
    conflicts = []
    for series_id, row in sorted(built["series"].items()):
        series_key = {"index_id": INDEX_ID, "period": period, "series_id": series_id}
        series_with_provisional = dict(row, provisional="true" if built["provisional"] else "false")
        existing_series = latest(root / "series.csv", series_key)
        if existing_series is not None:
            if existing_series["value"] != str(series_with_provisional["value"]) and not reason:
                conflicts.append(series_key)

    if conflicts:
        raise LedgerConflict(
            f"The following series rows would change without a reason: {conflicts}"
        )

    # Phase 2: write all rows
    append_row(
        root / "prints.csv",
        headline_key,
        headline_with_provisional,
        reason=reason,
    )
    for series_id, row in sorted(built["series"].items()):
        series_with_provisional = dict(row, provisional="true" if built["provisional"] else "false")
        append_row(
            root / "series.csv",
            {"index_id": INDEX_ID, "period": period, "series_id": series_id},
            series_with_provisional,
            reason=reason,
        )
