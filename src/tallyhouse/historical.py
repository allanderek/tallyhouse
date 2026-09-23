"""Publishing the historical index from archived evidence.

The two indices share everything that turns robots.txt into a verdict — the
parser, the classifier, the rate computations, the ledger. They differ only in
where the evidence comes from and what that implies about the resulting number.
Three of those implications are encoded here:

**A different index_id.** The levels are not comparable with the live index:
different panel, different reader, different blind spots. Sharing an index_id
would invite exactly the comparison the spec says not to make.

**Never provisional.** The live flag means "more evidence may arrive inside the
collection window". Common Crawl's archive is closed: what it saw in March 2023
is all it will ever have seen, so these numbers are final the moment they are
computed. Coverage is published as its own row instead, which is the honest
place for "we could read 62% of the panel".

**A cadence-neutral change row.** The series is roughly quarterly but not
evenly spaced — Common Crawl skipped months, and the gaps between published
points run from two months to four. `change_since_previous` says what it
actually is: the like-for-like move from the previous published point.
"""

from pathlib import Path

from tallyhouse.derive import derive_period
from tallyhouse.publish import build_print, record_print
from tallyhouse.storage import manifest_collector_version, manifest_path

INDEX_ID = "agent-accessibility-history"
CHANGE_SERIES = "change_since_previous"


def publish_series(
    root: Path,
    crawls: list[dict],
    agents: list[str],
    *,
    panel_size: int,
    methodology_version: str,
    computed_at: str,
    reason: str | None = None,
    log=print,
) -> list[dict]:
    """Derive and record every collected period, in series order."""
    results = []
    previous = None
    for entry in crawls:
        period = entry["period"]
        if not manifest_path(root, period).exists():
            # A gap breaks the chain rather than spanning it. Comparing across
            # a missing point would publish a two-step move in a field that
            # claims to describe one, so the next point gets no change row.
            previous = None
            results.append({"period": period, "status": "not collected"})
            log(f"{period}: not collected, skipping")
            continue
        tables = derive_period(root, period, agents)
        built = build_print(
            tables,
            previous,
            panel_size=panel_size,
            methodology_version=methodology_version,
            collector_version=manifest_collector_version(root, period),
            computed_at=computed_at,
            change_series=CHANGE_SERIES,
            provisional_threshold=None,
        )
        record_print(root, period, built, reason=reason, index_id=INDEX_ID)
        previous = tables
        results.append({
            "period": period,
            "status": "published",
            "headline": built["headline"]["value"],
            "coverage": built["series"]["coverage"]["value"],
            "conclusive": built["headline"]["denominator"],
        })
        log(
            f"{period}: targeted {built['headline']['value']:.2f}% of "
            f"{built['headline']['denominator']} conclusive "
            f"(coverage {built['series']['coverage']['value']:.1f}%)"
        )
    return results
