"""Loading of versioned methodology inputs: the frozen panel and the
tracked agent set. Both are data rather than code because both change on a
different cadence from the pipeline, and changing either changes published
numbers."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Panel:
    year: int
    tranco_list_id: str
    captured: str
    domains: list[str]


def load_panel(root: Path, year: int) -> Panel:
    raw = json.loads((root / "panel" / f"{year}.json").read_text())
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
