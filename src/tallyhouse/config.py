"""Loading of versioned methodology inputs: the frozen panel and the
tracked agent set. Both are data rather than code because both change on a
different cadence from the pipeline, and changing either changes published
numbers."""

import json
from dataclasses import dataclass
from importlib.metadata import version as _package_version
from pathlib import Path


@dataclass(frozen=True)
class Panel:
    year: int
    tranco_list_id: str
    captured: str
    domains: list[str]


def methodology_version(agents_version: int) -> str:
    """The methodology version: the agent set combined with the pinned parser.

    Spec 4.1 defines it as "the agent-set version combined with the pinned
    protego version — anything that can change a verdict from identical raw
    input". It is composed here rather than hardcoded so that neither half can
    be bumped without the ledger noticing.
    """
    return f"agents={agents_version};protego={_package_version('protego')}"


def load_panel(root: Path, year: int) -> Panel:
    raw = json.loads((root / "panel" / f"{year}.json").read_text())
    if raw["year"] != year:
        # A panel filed under the wrong year would be silently used for periods
        # it does not describe, and a panel of the wrong size lets coverage
        # exceed 100%.
        raise ValueError(
            f"panel file {year}.json declares year {raw['year']!r}"
        )
    domains = raw["domains"]
    if len(set(domains)) != len(domains):
        raise ValueError(f"panel {year} contains duplicate domains")
    return Panel(
        year=raw["year"],
        tranco_list_id=raw["tranco_list_id"],
        captured=raw["captured"],
        domains=domains,
    )


def load_agents(root: Path, version: int) -> list[str]:
    raw = json.loads((root / "agents" / f"v{version}.json").read_text())
    return raw["agents"]
