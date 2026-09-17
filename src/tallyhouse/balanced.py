"""Balanced panel construction for the historical index.

The panel is the intersection of a Tranco top-N at two endpoints. Membership is
therefore fixed across the whole span, so a change in the published number can
only mean a change in behaviour — never a change in who is being measured.

That matters more than it might sound: 39% of the Tranco top 1000 turned over
between February 2023 and September 2026. With contemporaneous panels, a move in
the headline would be composition and behaviour inseparably mixed.

The panel is deliberately NOT filtered by the live index's qualification sweep.
That sweep excludes hosts the live collector cannot read; Common Crawl, a
verified crawler, can read them, so importing the exclusion would inherit a bias
this index does not suffer.
"""

import json
from pathlib import Path


def balanced_panel(
    early: list[tuple[int, str]], late: list[tuple[int, str]]
) -> list[dict]:
    """Domains present in both endpoints, ordered by their later rank.

    Ordering by the later rank is arbitrary but must be deterministic, so that
    rebuilding the panel from the same two lists reproduces the same file.
    """
    early_ranks = {domain: rank for rank, domain in early}
    entries = [
        {"domain": domain, "rank_early": early_ranks[domain], "rank_late": rank}
        for rank, domain in late
        if domain in early_ranks
    ]
    return sorted(entries, key=lambda e: e["rank_late"])


def write_balanced_panel(
    root: Path,
    name: str,
    *,
    early_list_id: str,
    early_date: str,
    late_list_id: str,
    late_date: str,
    entries: list[dict],
    early_size: int,
    late_size: int,
) -> Path:
    path = root / "panel" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "name": name,
        "kind": "balanced",
        "endpoints": [
            {"tranco_list_id": early_list_id, "date": early_date, "size": early_size},
            {"tranco_list_id": late_list_id, "date": late_date, "size": late_size},
        ],
        "construction": {
            "rule": "domains present in the Tranco top-N at BOTH endpoints",
            "retained": len(entries),
            "churn": f"{early_size - len(entries)} of {early_size} early entries "
                     f"absent at the later endpoint",
            "known_bias": "members were prominent at both endpoints, so the panel "
                          "is biased toward durably significant sites; sites that "
                          "rose or fell within the span are absent",
            "not_comparable": "a different population from the live index panel, "
                              "so levels are not comparable between the two indices",
        },
        "ranks": {e["domain"]: {"early": e["rank_early"], "late": e["rank_late"]}
                  for e in entries},
        "domains": [e["domain"] for e in entries],
    }
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return path


def load_balanced_panel(root: Path, name: str) -> list[str]:
    document = json.loads((root / "panel" / f"{name}.json").read_text())
    domains = document["domains"]
    if len(set(domains)) != len(domains):
        raise ValueError(f"balanced panel {name} contains duplicate domains")
    return domains
