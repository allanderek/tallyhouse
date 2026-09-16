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
from tallyhouse.ledger import append_row

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
    append_row(
        root / "prints.csv",
        {"index_id": INDEX_ID, "period": period},
        built["headline"],
        reason=reason,
    )
    for series_id, row in sorted(built["series"].items()):
        append_row(
            root / "series.csv",
            {"index_id": INDEX_ID, "period": period, "series_id": series_id},
            row,
            reason=reason,
        )
