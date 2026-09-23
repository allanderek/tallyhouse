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
    unreadable_rate,
    targeted_rate,
)
from tallyhouse.ledger import LedgerConflict, append_row, would_conflict

INDEX_ID = "agent-accessibility"
PROVISIONAL_COVERAGE_THRESHOLD = 97.0

# Distinguishes "caller said nothing" from "caller said no threshold applies".
# The threshold cannot be a default argument: that would bind the constant at
# import, and recalibrating it — which spec 6.5 anticipates — would then leave
# already-published prints flagged forever with no way to correct them.
_UNSET = object()


def build_print(
    tables: dict,
    prev_tables: dict | None,
    panel_size: int,
    *,
    methodology_version: str,
    collector_version: str,
    computed_at: str,
    change_series: str = "change_wow",
    provisional_threshold: float | None = _UNSET,
) -> dict:
    """Assemble one period's published rows.

    `change_series` names the like-for-like change row. It is an argument
    because the row's name states a cadence, and a quarterly index whose change
    row is called change_wow would be publishing a falsehood in a field name.

    `provisional_threshold` of None means no coverage threshold applies. That
    is not a way to silence the flag: it is for an index reading a closed
    archive, where no further evidence can arrive and a number can therefore
    never be restated on coverage grounds. Such a number is final the moment it
    is computed, however much of the panel it covers — which is what the
    separately published coverage row is for.
    """
    if provisional_threshold is _UNSET:
        provisional_threshold = PROVISIONAL_COVERAGE_THRESHOLD
    conclusive = conclusive_domains(tables["observations"])
    cov = coverage(tables["observations"], panel_size)
    context = {
        "coverage": cov,
        "methodology_version": methodology_version,
        "collector_version": collector_version,
        "computed_at": computed_at,
    }

    def row(value, denominator: int) -> dict:
        """One published row.

        `denominator` is the population the row's value was actually computed
        over, and every series must carry its own. Sharing the headline's
        conclusive count across all of them published a denominator a reader
        could not reconcile the row against: `coverage` is a share of the panel,
        and `change_wow` is computed like-for-like over the intersection of the
        two periods' conclusive domains, which spec 6.4 makes the entire point
        of the change figure. It also churned change_wow vintages whenever the
        current period's conclusive count moved, even with the change unmoved.
        """
        return dict(context, value=value, denominator=denominator)

    n_conclusive = len(conclusive)
    headline = row(targeted_rate(tables["verdicts"], conclusive), n_conclusive)

    series = {
        # The per-agent, effective and blanket rates are all shares of the
        # conclusively-observed domains, so the headline denominator is theirs.
        "effective": row(
            effective_rate(tables["verdicts"], tables["blanket"], conclusive),
            n_conclusive,
        ),
        "blanket": row(blanket_rate(tables["blanket"], conclusive), n_conclusive),
        "coverage": row(cov, panel_size),
        # The blind spot, published rather than footnoted: sites whose server
        # answered but would not let us read the policy.
        "unreadable": row(unreadable_rate(tables["observations"], panel_size), panel_size),
    }
    for agent, rate in per_agent_rates(tables["verdicts"], conclusive).items():
        series[f"agent:{agent}"] = row(rate, n_conclusive)

    if prev_tables is not None:
        prev_conclusive = conclusive_domains(prev_tables["observations"])
        change = like_for_like_change(
            prev_tables["verdicts"],
            prev_conclusive,
            tables["verdicts"],
            conclusive,
        )
        if change is not None:
            series[change_series] = row(change, len(prev_conclusive & conclusive))

    return {
        "headline": headline,
        "series": series,
        "provisional": (
            False if provisional_threshold is None else cov < provisional_threshold
        ),
    }


def record_print(
    root: Path,
    period: str,
    built: dict,
    *,
    reason: str | None = None,
    index_id: str = INDEX_ID,
) -> None:
    """Record print to both prints.csv and series.csv with atomicity and idempotency.

    Args:
        root: Directory containing the ledger CSV files
        period: Period identifier (e.g., "2026-09-14")
        index_id: Which index these rows belong to. The two indices share one
                 ledger; index_id is what keeps their series apart.
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
    headline_key = {"index_id": index_id, "period": period}
    headline_with_provisional = dict(built["headline"], provisional="true" if built["provisional"] else "false")
    if would_conflict(root / "prints.csv", headline_key, headline_with_provisional, reason=reason):
        conflicts.append(("prints", headline_key))

    # Check all series
    for series_id, row in sorted(built["series"].items()):
        series_key = {"index_id": index_id, "period": period, "series_id": series_id}
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
            {"index_id": index_id, "period": period, "series_id": series_id},
            series_with_provisional,
            reason=reason,
        )
