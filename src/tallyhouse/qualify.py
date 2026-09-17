"""Panel construction.

The panel is the denominator of every published number, so how it is built is
methodology rather than configuration.

Tranco ranks domains by DNS traffic, not by whether they are websites. Its top
ranks include CDN endpoints and name servers — akamai.net, domaincontrol.com —
that never serve a robots.txt at all. Including them would put a permanent floor
under coverage, and a coverage floor makes the provisional-print threshold
useless: set the threshold above the floor and every print is provisional
forever, set it below and it can no longer detect a real outage.

So the panel is qualified at construction: the first N domains of a named Tranco
list that returned a conclusive observation during a one-off sweep. Structural
non-responders never enter, so later coverage loss is transient by construction
and the threshold measures the thing it exists to measure.

The qualification is reproducible: the Tranco list id, the sweep date, and how
many candidates were examined are all recorded in the panel file.
"""

import asyncio
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from tallyhouse.collect import fetch_domain
from tallyhouse.constants import CONCLUSIVE_OUTCOMES

# Swept in rank order, in chunks, so a run stops shortly after reaching `size`
# rather than fetching every candidate it was given.
CHUNK = 200


def read_tranco(path: Path) -> list[tuple[int, str]]:
    """Read a Tranco CSV (rank,domain) in rank order."""
    with path.open(newline="") as handle:
        return [(int(rank), domain) for rank, domain in csv.reader(handle) if domain]


async def qualify(
    candidates: list[tuple[int, str]],
    *,
    client: httpx.AsyncClient,
    size: int,
    concurrency: int = 8,
    attempts: int = 2,
) -> tuple[list[dict], int, list[dict]]:
    """Sweep candidates in rank order until `size` of them are conclusive.

    Returns the qualified entries, how many candidates were examined, and every
    excluded candidate with the outcome that excluded it. A domain qualifies on
    a conclusive outcome — including NoRobotsTxt, which is a site that exists
    and permits everything, not a site that is missing.

    The exclusions are retained and published because they are not neutral.
    Sites behind anti-automation challenges are excluded, and such sites are
    plausibly more likely than average to be hostile to AI crawlers — yelp.com,
    which names seven AI crawlers and disallows them all, is excluded on exactly
    these grounds. The panel therefore probably under-represents AI-hostile
    sites, and the excluded list is how a reader sizes that for themselves.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def one(entry: tuple[int, str]) -> tuple[int, str, str]:
        rank, domain = entry
        async with semaphore:
            try:
                record = await fetch_domain(client, domain, attempts=attempts)
                return rank, domain, record["outcome"]
            except Exception:
                return rank, domain, "TransportError"

    qualified: list[dict] = []
    excluded: list[dict] = []
    examined = 0
    for start in range(0, len(candidates), CHUNK):
        chunk = candidates[start : start + CHUNK]
        results = await asyncio.gather(*(one(c) for c in chunk))
        examined += len(chunk)
        for rank, domain, outcome in sorted(results):
            if outcome not in CONCLUSIVE_OUTCOMES:
                excluded.append({"rank": rank, "domain": domain, "outcome": outcome})
            elif len(qualified) < size:
                qualified.append({"rank": rank, "domain": domain})
            # A conclusive domain arriving after the panel is full is surplus,
            # not excluded. Recording it as an exclusion would overstate how
            # much of the list is unobservable, in an artifact published
            # precisely so readers can size that.
        if len(qualified) >= size:
            break

    return qualified, examined, excluded


def _count_outcomes(entries: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["outcome"]] = counts.get(entry["outcome"], 0) + 1
    return dict(sorted(counts.items()))


def write_panel(
    root: Path,
    year: int,
    *,
    tranco_list_id: str,
    qualified: list[dict],
    examined: int,
    excluded: list[dict] | None = None,
    captured: str | None = None,
) -> Path:
    path = root / "panel" / f"{year}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "year": year,
        "tranco_list_id": tranco_list_id,
        "captured": captured or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "qualification": {
            "rule": "first N domains of the Tranco list returning a conclusive "
                    "robots.txt observation during the sweep",
            "candidates_examined": examined,
            "qualified": len(qualified),
            "excluded": len(excluded or []),
            "excluded_by_outcome": _count_outcomes(excluded or []),
            "known_bias": "sites behind anti-automation challenges are excluded "
                          "and are plausibly more AI-hostile than average, so "
                          "the panel likely under-represents AI-hostile sites",
        },
        "excluded": sorted(
            (excluded or []), key=lambda entry: entry["rank"]
        ),
        "ranks": {entry["domain"]: entry["rank"] for entry in qualified},
        "domains": [entry["domain"] for entry in qualified],
    }
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return path
