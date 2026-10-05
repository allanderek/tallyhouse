"""Assembles the data the site generator renders from.

The generator is a pure function of committed data, so everything it needs is
gathered here and handed over as one JSON document. Nothing is computed during
rendering: the numbers on the site are the numbers in the ledger, read back
rather than recalculated, so a page can never disagree with the published record.
"""

import collections
import json
import re
from pathlib import Path

from tallyhouse.config import load_agents
from tallyhouse.constants import (
    CONCLUSIVE_OUTCOMES,
    MAX_BODY_BYTES,
    PROBE_PATHS,
    UNREADABLE_OUTCOMES,
    USER_AGENT,
)
from tallyhouse.derive import derive_period
from tallyhouse.downloads import catalogue, manifest
from tallyhouse.ledger import read_rows
from tallyhouse.periods import COLLECTION_WINDOW_HOURS
from tallyhouse.publish import PROVISIONAL_COVERAGE_THRESHOLD
from tallyhouse.storage import manifest_path

INDEX_ID = "agent-accessibility"
HISTORY_INDEX_ID = "agent-accessibility-history"


def _latest_by(rows: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
    """Keep only the highest vintage of each key — what the site should show."""
    best: dict[tuple, dict] = {}
    for row in rows:
        key = tuple(row[f] for f in key_fields)
        current = best.get(key)
        if current is None or int(row["vintage"]) > int(current["vintage"]):
            best[key] = row
    return list(best.values())


class UnreadableMethodology(Exception):
    """A print's methodology_version does not name an agent-set version."""


def _agents_version(methodology_version: str) -> int:
    """The agent-set version a print was computed with, read off the print.

    Taken from the print rather than passed in, so the stance counts on the
    crawler pages are always counted over the same agent set that produced the
    published number. Passing it in separately would let a site be rendered
    with 45 tokens under a headline computed from 16, and nothing would say so.
    """
    match = re.search(r"\bagents=(\d+)\b", methodology_version or "")
    if match is None:
        raise UnreadableMethodology(
            f"cannot tell which agent set produced this print from "
            f"methodology_version {methodology_version!r}. Refusing to count "
            f"stances over a guess."
        )
    return int(match.group(1))


def _describe_period(root: Path, period: str, methodology_version: str) -> tuple[list[dict], list[dict]]:
    """Verdicts and observations for one period, derived from committed evidence.

    Read from raw/ rather than from derived/, which is gitignored and holds
    whichever period happened to be derived last. Two things follow. A fresh
    clone renders the same site as this one, which is the claim the whole
    project rests on and was not previously true of `generate`. And the counts
    on the crawler pages describe the period whose headline they sit under,
    rather than whatever week someone last ran `derive` for.
    """
    agents = load_agents(root, _agents_version(methodology_version))
    tables = derive_period(root, period, agents)
    return (
        [dict(row) for row in tables["verdicts"]],
        [dict(observation, period=period) for observation in tables["observations"]],
        dict(tables["blanket"]),
        list(agents),
    )


def _slug(token: str) -> str:
    """URL slug for an agent token. Lowercased; tokens are otherwise URL-safe."""
    return token.lower()


def load_agent_data(root: Path, verdicts: list[dict]) -> dict:
    """Per-crawler facts for the agent pages.

    Stance counts are computed here rather than read from the ledger because
    they are descriptive, not published figures — the ledger carries the rates,
    and those are never recomputed for display. Shipping all 44,865 verdict
    rows into the generator would be wasteful, so they are aggregated first.
    """
    path = root / "agents" / "descriptions.json"
    if not path.exists():
        # Consistent with the rest of this module: absent data yields empty
        # sections rather than failing the build. The site can render without
        # crawler descriptions; it cannot render without prints.
        return {"agents": {}, "operators": {}, "purposes": {}}
    described = json.loads(path.read_text())
    by_agent: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    per_domain: dict[str, dict[str, str]] = collections.defaultdict(dict)
    for row in verdicts:
        by_agent[row["agent"]][row["stance"]] += 1
        per_domain[row["domain"]][row["agent"]] = row["stance"]

    agents = {}
    for token, meta in described["agents"].items():
        counts = by_agent.get(token, collections.Counter())
        agents[token] = {
            "token": token,
            "slug": _slug(token),
            "operator": meta["operator"],
            "purpose": meta["purpose"],
            "description": meta["description"],
            "series_id": f"agent:{token}",
            "stances": {k: counts.get(k, 0) for k in
                        ("FullBlock", "PartialBlock", "Allowed", "Unmentioned")},
        }

    tokens_by_operator = collections.defaultdict(list)
    for token, meta in agents.items():
        tokens_by_operator[meta["operator"]].append(token)

    operators = {}
    for name, description in described["operators"].items():
        tokens = sorted(tokens_by_operator.get(name, []))
        # Domains that do not treat one operator's tokens alike. This is the
        # whole point of grouping by operator: a site blocking training but
        # allowing retrieval has made a deliberate choice the headline hides.
        divergent = []
        if len(tokens) > 1:
            for domain, stances in per_domain.items():
                seen = {stances.get(t) for t in tokens}
                if len(seen) > 1:
                    divergent.append({"domain": domain,
                                      "stances": {t: stances.get(t) for t in tokens}})
            divergent.sort(key=lambda d: d["domain"])
        operators[name] = {
            "name": name,
            "description": description,
            "tokens": tokens,
            "divergent_count": len(divergent),
            "divergent_examples": divergent[:25],
        }

    return {"agents": agents, "operators": operators, "purposes": described["purposes"]}


def _index_rows(root: Path, index_id: str) -> tuple[list[dict], list[dict], list[dict]]:
    """One index's latest prints, its superseded prints, and its latest series.

    Shared by both indices rather than written twice: the vintage rule -- show
    the highest vintage, but keep the superseded rows so a restatement stays
    visible -- is the ledger's central promise, and two copies of it could drift.
    """
    prints = [r for r in read_rows(root / "prints.csv") if r["index_id"] == index_id]
    series = [r for r in read_rows(root / "series.csv") if r["index_id"] == index_id]

    latest_prints = sorted(
        _latest_by(prints, ("index_id", "period")), key=lambda r: r["period"]
    )
    latest_series = _latest_by(series, ("index_id", "period", "series_id"))
    superseded = [
        r for r in prints
        if not any(l["period"] == r["period"] and l["vintage"] == r["vintage"]
                   for l in latest_prints)
    ]
    return (
        latest_prints,
        sorted(superseded, key=lambda r: (r["period"], r["vintage"])),
        sorted(latest_series, key=lambda r: (r["period"], r["series_id"])),
    )


def load_history_data(root: Path) -> dict:
    """The historical index: the three-year series and how it was built.

    Its levels are NOT comparable with the live index -- a different panel,
    read by a different crawler, with different blind spots -- so it travels as
    its own object rather than as more periods of the same series. Keeping them
    separate in the data is what stops a page accidentally charting them
    together.
    """
    prints, superseded, series = _index_rows(root, HISTORY_INDEX_ID)
    panel_path = root / "panel" / "historical.json"
    panel = json.loads(panel_path.read_text()) if panel_path.exists() else {}
    crawls_path = root / "crawls" / "historical.json"
    crawls = json.loads(crawls_path.read_text()) if crawls_path.exists() else {}
    return {
        "id": HISTORY_INDEX_ID,
        "title": "Three years of AI-crawler blocking",
        "question": "When did the top websites start telling AI crawlers to stay out?",
        "prints": prints,
        "superseded": superseded,
        "series": series,
        "panel": {
            "size": len(panel.get("domains", [])),
            "endpoints": panel.get("endpoints", []),
            "construction": panel.get("construction", {}),
        },
        "crawls": crawls.get("crawls", []),
        "selection": crawls.get("selection", ""),
    }


def load_crawler_data(root: Path) -> dict:
    """The crawler's published identity, for bot-verification programmes.

    The user-agent is taken from constants.py rather than from the JSON,
    because constants.py is what the collector actually sends. A second copy in
    data/ could drift from it, and an identity document that disagrees with the
    requests it describes is worse than none: it is exactly what a verification
    reviewer would reject us for.
    """
    path = root / "crawler.json"
    document = json.loads(path.read_text()) if path.exists() else {}
    return {
        "userAgent": USER_AGENT,
        "token": document.get("token", ""),
        "category": document.get("category", ""),
        "purpose": document.get("purpose", ""),
        "contact": document.get("contact", ""),
        "prefixes": [
            p["ipv4Prefix"] for p in document.get("egress", {}).get("prefixes", [])
        ],
    }


_BLOCKING_STANCES = frozenset({"FullBlock", "PartialBlock"})


def load_panel_rows(
    panel: dict, observations: list[dict], verdicts: list[dict],
    blanket: dict[str, str], tracked: list[str],
) -> list[dict]:
    """One row per panel domain: what it is, and what it currently says.

    Aggregated here rather than in the generator because the verdicts are ~45
    rows per domain, and asking the generator to group forty-five thousand rows
    to render a thousand is work done in the wrong place.

    Every domain in the panel appears, including those we could not read. The
    panel is the denominator of every published figure, so a list that quietly
    omitted the domains we learned nothing about would misrepresent what the
    figure is a share of.
    """
    ranks = panel.get("ranks", {})
    outcomes = {o["domain"]: o.get("outcome", "") for o in observations}

    blocked: dict[str, int] = collections.defaultdict(int)
    for verdict in verdicts:
        if verdict["stance"] in _BLOCKING_STANCES:
            blocked[verdict["domain"]] += 1

    rows = [
        {
            "domain": domain,
            "rank": ranks.get(domain, 0),
            "outcome": outcomes.get(domain, "NotCollected"),
            "blocked": blocked.get(domain, 0),
            "tracked": len(tracked),
            # "" where we could not read the file, which is different from
            # Allowed: one is an absence of evidence, the other is evidence of
            # permission.
            "blanket": blanket.get(domain, ""),
        }
        for domain in panel.get("domains", [])
    ]
    return sorted(rows, key=lambda r: (r["rank"] == 0, r["rank"], r["domain"]))


def load_methodology_data(root: Path) -> dict:
    """The method as the code actually implements it, plus its changelog.

    Every parameter here is read from the module that the pipeline itself uses,
    not restated. A methodology page that drifts from the code is worse than no
    page: it documents a method nobody ran. This is the same reasoning that
    keeps the crawler's user-agent out of data/crawler.json.

    Which versions were actually used is derived from the ledger rather than
    declared, so a version that appears in a published print without an
    explanation shows up as a gap instead of passing unnoticed.
    """
    path = root / "methodology.json"
    document = json.loads(path.read_text()) if path.exists() else {}

    # Read across both indices and every vintage: a methodology version is not
    # specific to an index, and a version used only by rows that have since
    # been restated is a different fact from one never used at all. Showing
    # "no periods" for a superseded version would read as the latter.
    rows = read_rows(root / "prints.csv")
    current = {
        (r["index_id"], r["period"], r["vintage"])
        for r in _latest_by(rows, ("index_id", "period"))
    }

    in_force: dict[str, set[str]] = collections.defaultdict(set)
    retired: dict[str, set[str]] = collections.defaultdict(set)
    for row in rows:
        key = (row["index_id"], row["period"], row["vintage"])
        bucket = in_force if key in current else retired
        bucket[row["methodology_version"]].add(row["period"])

    versions = [
        {
            "version": entry["version"],
            "adopted": entry.get("adopted", ""),
            "summary": entry.get("summary", ""),
            "changed": entry.get("changed", ""),
            "why": entry.get("why", ""),
            "periods": sorted(in_force.get(entry["version"], ())),
            # Periods this version produced that have since been restated under
            # a later one. The restatement is the ledger's record of the change
            # actually taking effect.
            "supersededPeriods": sorted(
                retired.get(entry["version"], set()) - in_force.get(entry["version"], set())
            ),
        }
        for entry in document.get("versions", [])
    ]
    declared = {entry["version"] for entry in versions}

    return {
        "composition": document.get("composition", ""),
        "versions": versions,
        # Named rather than counted, so the page can say which version lacks an
        # explanation instead of merely that one does.
        "undocumented": sorted({r["methodology_version"] for r in rows} - declared),
        "parameters": {
            "probePaths": list(PROBE_PATHS),
            "conclusiveOutcomes": sorted(CONCLUSIVE_OUTCOMES),
            "unreadableOutcomes": sorted(UNREADABLE_OUTCOMES),
            "maxBodyBytes": MAX_BODY_BYTES,
            "collectionWindowHours": COLLECTION_WINDOW_HOURS,
            "provisionalCoverageThreshold": PROVISIONAL_COVERAGE_THRESHOLD,
            "userAgent": USER_AGENT,
        },
    }


def load_site_data(root: Path, *, index_id: str = INDEX_ID) -> dict:
    """Everything the generator needs, as plain JSON-serialisable data."""
    latest_prints, superseded, latest_series = _index_rows(root, index_id)

    # The period the site's descriptive sections are about: the one whose
    # headline the pages sit under.
    described = latest_prints[-1] if latest_prints else None
    if described is not None and manifest_path(root, described["period"]).exists():
        verdicts, fetches, blanket, tracked = _describe_period(
            root, described["period"], described["methodology_version"]
        )
    else:
        # Nothing published, or its evidence is not in this checkout. Empty
        # sections rather than a failed build, as elsewhere in this module.
        verdicts, fetches, blanket, tracked = [], [], {}, []

    panel_path = root / "panel" / "2026.json"
    panel = json.loads(panel_path.read_text()) if panel_path.exists() else {}

    data = {
        "index": {
            "id": index_id,
            "title": "Agent Accessibility Index",
            "question": "How many of the top 1000 websites tell AI crawlers to stay out?",
        },
        "prints": latest_prints,
        "superseded": superseded,
        "series": latest_series,
        "history": load_history_data(root),
        "crawler": load_crawler_data(root),
        "methodology": load_methodology_data(root),
        "panelRows": load_panel_rows(panel, fetches, verdicts, blanket, tracked),
        "panel": {
            "tranco_list_id": panel.get("tranco_list_id"),
            "captured": panel.get("captured"),
            "size": len(panel.get("domains", [])),
            "qualification": panel.get("qualification", {}),
        },
        "verdicts": verdicts,
        "fetches": fetches,
        **load_agent_data(root, verdicts),
    }
    # Built last, because the catalogue is a function of everything above it.
    # Only the manifest travels to the generator: the content is written by
    # Python, so there is no reason to push tens of thousands of CSV rows
    # through the generator to be handed straight back.
    data["downloads"] = manifest(catalogue(root, data))
    return data


def write_site(files: dict[str, str], out: Path) -> list[Path]:
    """Write the rendered site. Python does all file writing; Elm never does."""
    written = []
    for path, content in sorted(files.items()):
        target = out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        # newline="" writes exactly the characters given, with no translation.
        # Without it the CRLF line endings of a verbatim ledger download would be
        # rewritten on some platforms, so the published file would not be the
        # committed one.
        with target.open("w", newline="") as handle:
            handle.write(content)
        written.append(target)
    return written
