"""Loading of versioned methodology inputs: the frozen panel and the
tracked agent set. Both are data rather than code because both change on a
different cadence from the pipeline, and changing either changes published
numbers."""

import json
from dataclasses import dataclass
from importlib.metadata import version as _package_version
from pathlib import Path


@dataclass(frozen=True)
class Removal:
    """One domain removed from the live panel at its owner's request."""

    domain: str
    effective_from: str
    reason: str
    requested: str = ""
    source: str = ""


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


def load_removals(root: Path, name: str = "removals") -> list[Removal]:
    """Panel removals requested by site owners, as committed data.

    The crawler page promises that a site can ask to be left out and that the
    removal is recorded with its reason. That makes this a mechanism rather
    than an intention, and committed data rather than an operator's memory.
    """
    path = root / "panel" / f"{name}.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    removals = []
    for entry in raw.get("removals", []):
        missing = [f for f in ("domain", "effective_from", "reason") if not entry.get(f)]
        if missing:
            # A removal without a reason is indistinguishable from a quiet
            # edit to the denominator, and one without an effective period
            # cannot be applied without restating published prints.
            raise ValueError(
                f"removal {entry.get('domain', '?')!r} is missing "
                f"{', '.join(missing)}; every removal must say which domain, "
                f"from when, and why"
            )
        removals.append(
            Removal(
                domain=entry["domain"],
                effective_from=entry["effective_from"],
                reason=entry["reason"],
                requested=entry.get("requested", ""),
                source=entry.get("source", ""),
            )
        )
    domains = [r.domain for r in removals]
    if len(set(domains)) != len(domains):
        raise ValueError("a domain is listed for removal more than once")
    return removals


def removals_in_effect(removals: list[Removal], period: str) -> set[str]:
    """Domains removed as of `period`.

    Comparison is on the period string, which sorts correctly because periods
    are ISO dates. A removal dated after the period does not apply to it: that
    is what makes honouring a request unable to restate an already-published
    number.
    """
    return {r.domain for r in removals if r.effective_from <= period}
