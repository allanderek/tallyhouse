# Tallyhouse Data Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect robots.txt weekly from a frozen panel of 1000 domains, classify AI-crawler blocking, and publish immutable index prints to an append-only ledger.

**Architecture:** Four stages with strict one-way data flow. `collect` is the only stage that touches the network and only ever appends raw evidence. `derive` is a pure function from raw evidence to classified tables. `compute` turns tables into candidate index values. `ledger` enforces the immutability and vintage rules. Nothing downstream of `collect` may make a network request.

**Tech Stack:** Python 3.10, httpx (async fetching), protego (RFC 9309 robots.txt parsing), pytest.

**Spec:** `docs/superpowers/specs/2026-09-15-tallyhouse-design.md`

## Global Constraints

- Period identifier is the **ISO date of the Monday** collection began, `YYYY-MM-DD`. Never ISO week notation.
- Stance values are exactly: `FullBlock`, `PartialBlock`, `Allowed`, `Unmentioned`.
- Outcome values are exactly: `Fetched`, `NoRobotsTxt`, `ServerError`, `Timeout`, `DnsFailure`, `ConnectFailure`, `TransportError`, `NotPlainText`, `TooLarge`.
- Conclusive outcomes are exactly `Fetched` and `NoRobotsTxt`. All others are excluded from both numerator and denominator.
- Published ledger rows are immutable. A changed value appends a new vintage with a mandatory reason; it never overwrites.
- `derive` and `compute` must never open a socket.
- All timestamps are ISO 8601 UTC with a `Z` suffix.
- Crawler user-agent string is exactly `TallyhouseIndexBot/1.0 (+https://allanderek.github.io/tallyhouse/about/crawler/)`.
- Dependency pins: `protego==0.6.2`, `httpx==0.28.1`, `pytest==9.1.1`.

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `src/tallyhouse/__init__.py`, `src/tallyhouse/constants.py`
- Test: `tests/test_constants.py`

**Interfaces:**
- Consumes: nothing
- Produces: `tallyhouse.constants` with `USER_AGENT: str`, `PROBE_PATHS: list[str]`, `PROBE_BASE: str`, `CONCLUSIVE_OUTCOMES: frozenset[str]`, `MAX_BODY_BYTES: int`

- [ ] **Step 1: Create the dependency and pytest config files**

`requirements.txt`:
```
protego==0.6.2
httpx==0.28.1
pytest==9.1.1
```

`pytest.ini`:
```ini
[pytest]
pythonpath = src
testpaths = tests
```

Note: `python3 -m venv` fails on this machine because `python3.10-venv` is not installed. Either run `sudo apt install python3.10-venv` first, or install with `python3 -m pip install --user -r requirements.txt`.

- [ ] **Step 2: Write the failing test**

`tests/test_constants.py`:
```python
from tallyhouse import constants


def test_user_agent_identifies_and_links_to_crawler_page():
    assert constants.USER_AGENT.startswith("TallyhouseIndexBot/1.0")
    assert "/about/crawler/" in constants.USER_AGENT


def test_probe_paths_include_root_and_varied_subpaths():
    assert "/" in constants.PROBE_PATHS
    assert len(constants.PROBE_PATHS) >= 5


def test_only_fetched_and_no_robots_are_conclusive():
    assert constants.CONCLUSIVE_OUTCOMES == frozenset({"Fetched", "NoRobotsTxt"})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_constants.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tallyhouse'`

- [ ] **Step 4: Write minimal implementation**

`src/tallyhouse/__init__.py`: empty file.

`src/tallyhouse/constants.py`:
```python
"""Project-wide constants. Values here are methodology, not configuration —
changing PROBE_PATHS changes published numbers and requires a methodology
version bump."""

USER_AGENT = (
    "TallyhouseIndexBot/1.0 "
    "(+https://allanderek.github.io/tallyhouse/about/crawler/)"
)

PROBE_BASE = "https://probe.invalid"

PROBE_PATHS = [
    "/",
    "/index.html",
    "/about",
    "/news/article-1",
    "/api/v1/data",
    "/images/photo.jpg",
]

CONCLUSIVE_OUTCOMES = frozenset({"Fetched", "NoRobotsTxt"})

MAX_BODY_BYTES = 512 * 1024
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_constants.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add requirements.txt pytest.ini src/tallyhouse/__init__.py src/tallyhouse/constants.py tests/test_constants.py
git commit -m "feat: project scaffolding and methodology constants"
```

---

### Task 2: Period arithmetic

**Files:**
- Create: `src/tallyhouse/periods.py`
- Test: `tests/test_periods.py`

**Interfaces:**
- Consumes: nothing
- Produces: `period_for(dt: datetime) -> str`, `previous_period(period: str) -> str`, `next_period(period: str) -> str`, `parse_period(period: str) -> date`, `window_end(period: str) -> datetime`, exception `InvalidPeriod`

- [ ] **Step 1: Write the failing test**

`tests/test_periods.py`:
```python
from datetime import datetime, date, timezone

import pytest

from tallyhouse.periods import (
    InvalidPeriod,
    next_period,
    parse_period,
    period_for,
    previous_period,
    window_end,
)


def test_period_for_returns_monday_of_that_week():
    # 2026-09-16 is a Wednesday; its Monday is 2026-09-14.
    assert period_for(datetime(2026, 9, 16, 13, 0, tzinfo=timezone.utc)) == "2026-09-14"


def test_period_for_on_a_monday_returns_that_monday():
    assert period_for(datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)) == "2026-09-14"


def test_period_for_on_a_sunday_returns_the_preceding_monday():
    assert period_for(datetime(2026, 9, 20, 23, 59, tzinfo=timezone.utc)) == "2026-09-14"


def test_periods_step_by_seven_days():
    assert previous_period("2026-09-14") == "2026-09-07"
    assert next_period("2026-09-14") == "2026-09-21"


def test_periods_cross_year_boundaries_without_iso_week_confusion():
    # The trap ISO week notation would create: this Monday sits in calendar 2026
    # but ISO week-year 2027. A Monday date has no such ambiguity.
    assert next_period("2026-12-28") == "2027-01-04"
    assert previous_period("2027-01-04") == "2026-12-28"


def test_parse_period_returns_a_date():
    assert parse_period("2026-09-14") == date(2026, 9, 14)


def test_non_monday_period_is_rejected():
    with pytest.raises(InvalidPeriod):
        parse_period("2026-09-16")


def test_malformed_period_is_rejected():
    with pytest.raises(InvalidPeriod):
        parse_period("2026-W38")


def test_window_closes_72_hours_after_monday_midnight_utc():
    assert window_end("2026-09-14") == datetime(2026, 9, 17, 0, 0, tzinfo=timezone.utc)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_periods.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tallyhouse.periods'`

- [ ] **Step 3: Write minimal implementation**

`src/tallyhouse/periods.py`:
```python
"""Period arithmetic.

A period is the ISO date of the Monday on which collection began, e.g.
"2026-09-14". ISO week notation is deliberately avoided: the ISO week-year
diverges from the calendar year at year boundaries and some years have 53
weeks, which is a reliable source of off-by-one bugs.
"""

from datetime import date, datetime, timedelta, timezone

COLLECTION_WINDOW_HOURS = 72


class InvalidPeriod(ValueError):
    """Raised when a period string is malformed or is not a Monday."""


def period_for(dt: datetime) -> str:
    """The period containing the given instant."""
    monday = dt.date() - timedelta(days=dt.weekday())
    return monday.isoformat()


def parse_period(period: str) -> date:
    try:
        parsed = date.fromisoformat(period)
    except ValueError as exc:
        raise InvalidPeriod(f"{period!r} is not an ISO date") from exc
    if parsed.weekday() != 0:
        raise InvalidPeriod(f"{period!r} is not a Monday")
    return parsed


def previous_period(period: str) -> str:
    return (parse_period(period) - timedelta(days=7)).isoformat()


def next_period(period: str) -> str:
    return (parse_period(period) + timedelta(days=7)).isoformat()


def window_end(period: str) -> datetime:
    """The instant the collection window closes, including all retries."""
    start = datetime.combine(
        parse_period(period), datetime.min.time(), tzinfo=timezone.utc
    )
    return start + timedelta(hours=COLLECTION_WINDOW_HOURS)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_periods.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/tallyhouse/periods.py tests/test_periods.py
git commit -m "feat: period arithmetic on Monday dates"
```

---

### Task 3: Content-addressed raw storage

**Files:**
- Create: `src/tallyhouse/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: nothing
- Produces: `store_body(root: Path, data: bytes) -> str`, `load_body(root: Path, sha: str) -> bytes`, `body_path(root: Path, sha: str) -> Path`, `write_manifest(root: Path, period: str, records: list[dict]) -> Path`, `read_manifest(root: Path, period: str) -> list[dict]`

- [ ] **Step 1: Write the failing test**

`tests/test_storage.py`:
```python
import gzip

from tallyhouse.storage import (
    body_path,
    load_body,
    read_manifest,
    store_body,
    write_manifest,
)


def test_store_body_returns_sha256_and_roundtrips(tmp_path):
    sha = store_body(tmp_path, b"User-agent: *\nDisallow:\n")
    assert len(sha) == 64
    assert load_body(tmp_path, sha) == b"User-agent: *\nDisallow:\n"


def test_identical_bodies_deduplicate_to_one_file(tmp_path):
    a = store_body(tmp_path, b"same")
    b = store_body(tmp_path, b"same")
    assert a == b
    assert len(list(tmp_path.rglob("*.txt.gz"))) == 1


def test_bodies_are_stored_gzipped(tmp_path):
    sha = store_body(tmp_path, b"hello robots")
    with gzip.open(body_path(tmp_path, sha), "rb") as handle:
        assert handle.read() == b"hello robots"


def test_bodies_are_sharded_by_sha_prefix(tmp_path):
    sha = store_body(tmp_path, b"shard me")
    assert body_path(tmp_path, sha).parent.name == sha[:2]


def test_manifest_roundtrips(tmp_path):
    records = [{"domain": "example.com", "outcome": "Fetched", "sha256": "abc"}]
    write_manifest(tmp_path, "2026-09-14", records)
    assert read_manifest(tmp_path, "2026-09-14") == records


def test_manifest_is_sorted_by_domain_for_stable_diffs(tmp_path):
    write_manifest(
        tmp_path,
        "2026-09-14",
        [{"domain": "zzz.com"}, {"domain": "aaa.com"}],
    )
    assert [r["domain"] for r in read_manifest(tmp_path, "2026-09-14")] == [
        "aaa.com",
        "zzz.com",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_storage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tallyhouse.storage'`

- [ ] **Step 3: Write minimal implementation**

`src/tallyhouse/storage.py`:
```python
"""Content-addressed storage for raw robots.txt evidence.

Bodies are keyed by sha256 and shared across all periods, so the large
majority of files that do not change between weeks cost nothing to retain.
"""

import gzip
import hashlib
import json
from pathlib import Path


def body_path(root: Path, sha: str) -> Path:
    return root / "raw" / "bodies" / sha[:2] / f"{sha}.txt.gz"


def store_body(root: Path, data: bytes) -> str:
    """Store a body and return its sha256. Idempotent."""
    sha = hashlib.sha256(data).hexdigest()
    path = body_path(root, sha)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        # mtime=0 keeps the gzip output byte-identical across runs.
        with gzip.GzipFile(filename="", mode="wb", fileobj=path.open("wb"), mtime=0) as handle:
            handle.write(data)
    return sha


def load_body(root: Path, sha: str) -> bytes:
    with gzip.open(body_path(root, sha), "rb") as handle:
        return handle.read()


def manifest_path(root: Path, period: str) -> Path:
    return root / "raw" / period / "manifest.json"


def write_manifest(root: Path, period: str, records: list[dict]) -> Path:
    path = manifest_path(root, period)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda r: r["domain"])
    path.write_text(json.dumps(ordered, indent=2, sort_keys=True) + "\n")
    return path


def read_manifest(root: Path, period: str) -> list[dict]:
    return json.loads(manifest_path(root, period).read_text())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_storage.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/tallyhouse/storage.py tests/test_storage.py
git commit -m "feat: content-addressed storage for raw robots.txt evidence"
```

---

### Task 4: Panel and agent set loading

**Files:**
- Create: `src/tallyhouse/config.py`, `data/agents/v1.json`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing
- Produces: `load_agents(root: Path, version: int) -> list[str]`, `load_panel(root: Path, year: int) -> Panel`, dataclass `Panel(year: int, tranco_list_id: str, captured: str, domains: list[str])`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
import json

import pytest

from tallyhouse.config import load_agents, load_panel


def write_panel(root, year, domains, list_id="NX3JG"):
    path = root / "panel" / f"{year}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "year": year,
                "tranco_list_id": list_id,
                "captured": "2026-01-05T00:00:00Z",
                "domains": domains,
            }
        )
    )


def test_load_panel_exposes_provenance_and_domains(tmp_path):
    write_panel(tmp_path, 2026, ["example.com", "bbc.co.uk"])
    panel = load_panel(tmp_path, 2026)
    assert panel.year == 2026
    assert panel.tranco_list_id == "NX3JG"
    assert panel.domains == ["example.com", "bbc.co.uk"]


def test_panel_without_a_tranco_list_id_is_rejected(tmp_path):
    path = tmp_path / "panel" / "2026.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"year": 2026, "domains": ["a.com"]}))
    # The list id is what makes the panel falsifiable rather than asserted.
    with pytest.raises(KeyError):
        load_panel(tmp_path, 2026)


def test_duplicate_domains_in_a_panel_are_rejected(tmp_path):
    write_panel(tmp_path, 2026, ["a.com", "a.com"])
    with pytest.raises(ValueError):
        load_panel(tmp_path, 2026)


def test_load_agents_returns_the_tracked_set(tmp_path):
    path = tmp_path / "agents" / "v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "agents": ["GPTBot", "ClaudeBot"]}))
    assert load_agents(tmp_path, 1) == ["GPTBot", "ClaudeBot"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tallyhouse.config'`

- [ ] **Step 3: Write minimal implementation**

`src/tallyhouse/config.py`:
```python
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
```

- [ ] **Step 4: Create the real agent set**

`data/agents/v1.json`:
```json
{
  "version": 1,
  "note": "Adding or removing an agent changes the series and requires a methodology version bump plus recomputation of all history as new vintages.",
  "agents": [
    "GPTBot",
    "ChatGPT-User",
    "OAI-SearchBot",
    "ClaudeBot",
    "anthropic-ai",
    "CCBot",
    "Google-Extended",
    "PerplexityBot",
    "Perplexity-User",
    "Bytespider",
    "Amazonbot",
    "Applebot-Extended",
    "meta-externalagent",
    "Diffbot",
    "ImagesiftBot",
    "cohere-ai"
  ]
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add src/tallyhouse/config.py data/agents/v1.json tests/test_config.py
git commit -m "feat: load frozen panel and versioned agent set"
```

---

### Task 5: Stance classification

**Files:**
- Create: `src/tallyhouse/parse.py`
- Test: `tests/test_parse.py`

**Interfaces:**
- Consumes: `tallyhouse.constants.PROBE_PATHS`, `PROBE_BASE`
- Produces: `is_mentioned(body: str, agent: str) -> bool`, `classify(body: str, agent: str) -> str`, `blanket_stance(body: str) -> str`. All stance returns are the literal strings `FullBlock`, `PartialBlock`, `Allowed`, `Unmentioned`.

- [ ] **Step 1: Write the failing test**

`tests/test_parse.py`:
```python
from tallyhouse.parse import blanket_stance, classify, is_mentioned

FULL = "User-agent: GPTBot\nDisallow: /\n"
PARTIAL = "User-agent: CCBot\nDisallow: /private\n"
ALLOW_ALL = "User-agent: *\nAllow: /\n"
BLANKET = "User-agent: *\nDisallow: /\n"


def test_agent_named_and_fully_disallowed_is_full_block():
    assert classify(FULL, "GPTBot") == "FullBlock"


def test_agent_named_and_partly_disallowed_is_partial_block():
    assert classify(PARTIAL, "CCBot") == "PartialBlock"


def test_agent_not_named_anywhere_is_unmentioned():
    assert classify(FULL, "ClaudeBot") == "Unmentioned"


def test_unmentioned_takes_precedence_over_blanket_rules():
    # The site blocks everyone via *, but says nothing about ClaudeBot.
    # The targeted headline must not count this as targeting ClaudeBot.
    assert classify(BLANKET, "ClaudeBot") == "Unmentioned"


def test_agent_named_and_explicitly_allowed_is_allowed():
    body = BLANKET + "\nUser-agent: GPTBot\nAllow: /\nDisallow:\n"
    assert classify(body, "GPTBot") == "Allowed"


def test_agent_matching_is_case_insensitive():
    assert is_mentioned("user-agent: gptbot\nDisallow: /\n", "GPTBot")
    assert classify("user-agent: gptbot\nDisallow: /\n", "GPTBot") == "FullBlock"


def test_substring_of_another_agent_name_does_not_count_as_mentioned():
    # "Applebot-Extended" being present must not imply "Applebot" is named.
    assert not is_mentioned("User-agent: Applebot-Extended\nDisallow: /\n", "Applebot")


def test_blanket_stance_detects_a_site_closed_to_everyone():
    assert blanket_stance(BLANKET) == "FullBlock"


def test_blanket_stance_of_an_open_site_is_allowed():
    assert blanket_stance(ALLOW_ALL) == "Allowed"


def test_empty_body_is_unmentioned_and_open():
    assert classify("", "GPTBot") == "Unmentioned"
    assert blanket_stance("") == "Allowed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_parse.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tallyhouse.parse'`

- [ ] **Step 3: Write minimal implementation**

`src/tallyhouse/parse.py`:
```python
"""Classification of a robots.txt body into a stance per agent.

Stance is defined operationally by a fixed probe set rather than by reading
directives directly. This is robust to the many ways a real file can express
the same policy, and it is reproducible — but it means PROBE_PATHS is part of
the published methodology, not an implementation detail.
"""

import re

from protego import Protego

from tallyhouse.constants import PROBE_BASE, PROBE_PATHS

# An agent token no real site will name, used to observe the "*" group.
_BLANKET_PROBE_AGENT = "TallyhouseBlanketProbe"

_USER_AGENT_LINE = re.compile(r"^\s*user-agent\s*:\s*(.+?)\s*$", re.IGNORECASE)


def is_mentioned(body: str, agent: str) -> bool:
    """True if the agent is named in a User-agent line.

    Matching is exact and case-insensitive on the whole token, so that
    "Applebot-Extended" does not imply "Applebot".
    """
    wanted = agent.lower()
    for line in body.splitlines():
        match = _USER_AGENT_LINE.match(line)
        if match and match.group(1).lower() == wanted:
            return True
    return False


def _stance_from_probes(body: str, agent: str) -> str:
    parser = Protego.parse(body)
    results = [parser.can_fetch(PROBE_BASE + path, agent) for path in PROBE_PATHS]
    if not any(results):
        return "FullBlock"
    if all(results):
        return "Allowed"
    return "PartialBlock"


def classify(body: str, agent: str) -> str:
    """The stance a site takes toward a specific named agent.

    An agent the file never names is Unmentioned even when a blanket "*" rule
    blocks it, because the targeted headline measures deliberate stance toward
    that agent. Blanket blocking is reported separately by blanket_stance.
    """
    if not is_mentioned(body, agent):
        return "Unmentioned"
    return _stance_from_probes(body, agent)


def blanket_stance(body: str) -> str:
    """The stance the "*" group takes, observed via an unnamed agent."""
    return _stance_from_probes(body, _BLANKET_PROBE_AGENT)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_parse.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add src/tallyhouse/parse.py tests/test_parse.py
git commit -m "feat: classify robots.txt stance per agent via a fixed probe set"
```

---

### Task 6: The collector

**Files:**
- Create: `src/tallyhouse/collect.py`
- Test: `tests/test_collect.py`

**Interfaces:**
- Consumes: `tallyhouse.constants`, `tallyhouse.storage.store_body`
- Produces: `classify_response(status: int, content_type: str | None, size: int) -> str`, `async fetch_domain(client, domain: str, *, attempts: int = 3) -> dict`. The returned dict has keys `domain`, `outcome`, `http_status`, `final_url`, `content_type`, `bytes`, `body` (`bytes | None`), `fetched_at`, `attempts`. Note it returns the raw `body`, not a `sha256` — hashing and storage happen in Task 11, so that this function stays free of filesystem concerns.

- [ ] **Step 1: Write the failing test**

`tests/test_collect.py`:
```python
import httpx
import pytest

from tallyhouse.collect import classify_response, fetch_domain


def client_returning(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_200_plain_text_is_fetched():
    assert classify_response(200, "text/plain", 100) == "Fetched"


def test_404_is_no_robots_txt():
    assert classify_response(404, "text/html", 0) == "NoRobotsTxt"


def test_5xx_is_server_error():
    assert classify_response(503, "text/html", 0) == "ServerError"


def test_html_served_at_robots_txt_is_not_plain_text():
    # Many sites return a styled 404 page with a 200 status.
    assert classify_response(200, "text/html", 100) == "NotPlainText"


def test_oversized_body_is_too_large():
    assert classify_response(200, "text/plain", 10 * 1024 * 1024) == "TooLarge"


@pytest.mark.asyncio
async def test_successful_fetch_records_body_and_metadata():
    def handler(request):
        return httpx.Response(200, text="User-agent: *\nDisallow:\n",
                              headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "example.com")

    assert record["domain"] == "example.com"
    assert record["outcome"] == "Fetched"
    assert record["http_status"] == 200
    assert record["body"] == b"User-agent: *\nDisallow:\n"
    assert record["fetched_at"].endswith("Z")


@pytest.mark.asyncio
async def test_sends_the_identifying_user_agent():
    seen = {}

    def handler(request):
        seen["ua"] = request.headers["user-agent"]
        return httpx.Response(200, text="", headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        await fetch_domain(client, "example.com")

    assert seen["ua"].startswith("TallyhouseIndexBot/1.0")


@pytest.mark.asyncio
async def test_timeout_is_retried_then_recorded_as_timeout():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        raise httpx.ConnectTimeout("too slow")

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "slow.example", attempts=3)

    assert record["outcome"] == "Timeout"
    assert record["attempts"] == 3
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_transient_failure_then_success_is_recorded_as_fetched():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectTimeout("first attempt fails")
        return httpx.Response(200, text="ok", headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "flaky.example", attempts=3)

    assert record["outcome"] == "Fetched"
    assert record["attempts"] == 2


@pytest.mark.asyncio
async def test_dns_failure_is_recorded_as_dns_failure():
    def handler(request):
        raise httpx.ConnectError("Name or service not known")

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "nope.invalid", attempts=1)

    assert record["outcome"] == "DnsFailure"
```

Add `pytest-asyncio==1.3.0` to `requirements.txt` and this to `pytest.ini`:
```ini
asyncio_mode = auto
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pip install --user pytest-asyncio==1.3.0 && python3 -m pytest tests/test_collect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tallyhouse.collect'`

- [ ] **Step 3: Write minimal implementation**

`src/tallyhouse/collect.py`:
```python
"""The only stage that touches the network.

It appends raw evidence and nothing else: no classification, no index
values. Every outcome the crawler can observe is recorded as data, including
the failures, because the denominator rule depends on telling a conclusive
absence (404) from an inconclusive one (timeout).
"""

import asyncio
from datetime import datetime, timezone

import httpx

from tallyhouse.constants import MAX_BODY_BYTES, USER_AGENT

_PLAIN_TEXT_PREFIXES = ("text/plain",)


def classify_response(status: int, content_type: str | None, size: int) -> str:
    if status == 404 or status == 410:
        return "NoRobotsTxt"
    if status >= 500:
        return "ServerError"
    if status != 200:
        # 401/403 and friends: the file exists but we were refused, which is
        # not evidence about crawler policy.
        return "ServerError"
    if size > MAX_BODY_BYTES:
        return "TooLarge"
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype and not ctype.startswith(_PLAIN_TEXT_PREFIXES):
        return "NotPlainText"
    return "Fetched"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def fetch_domain(client: httpx.AsyncClient, domain: str, *, attempts: int = 3) -> dict:
    """Fetch one domain's robots.txt, retrying transient failures."""
    last_outcome = "Timeout"
    for attempt in range(1, attempts + 1):
        try:
            response = await client.get(
                f"https://{domain}/robots.txt",
                headers={"user-agent": USER_AGENT},
                follow_redirects=True,
            )
        except httpx.ConnectError:
            last_outcome = "DnsFailure"
        except (httpx.TimeoutException, httpx.NetworkError):
            last_outcome = "Timeout"
        else:
            body = response.content
            outcome = classify_response(
                response.status_code,
                response.headers.get("content-type"),
                len(body),
            )
            return {
                "domain": domain,
                "outcome": outcome,
                "http_status": response.status_code,
                "final_url": str(response.url),
                "content_type": response.headers.get("content-type"),
                "bytes": len(body),
                "body": body,
                "fetched_at": _now(),
                "attempts": attempt,
            }
        if attempt < attempts:
            await asyncio.sleep(min(2 ** attempt, 30))

    return {
        "domain": domain,
        "outcome": last_outcome,
        "http_status": None,
        "final_url": None,
        "content_type": None,
        "bytes": None,
        "body": None,
        "fetched_at": _now(),
        "attempts": attempts,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_collect.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add src/tallyhouse/collect.py tests/test_collect.py requirements.txt pytest.ini
git commit -m "feat: robots.txt collector with retries and outcome classification"
```

---

### Task 7: Index computation

**Files:**
- Create: `src/tallyhouse/compute.py`
- Test: `tests/test_compute.py`

**Interfaces:**
- Consumes: `tallyhouse.constants.CONCLUSIVE_OUTCOMES`
- Produces: `conclusive_domains(observations: list[dict]) -> set[str]`, `coverage(observations: list[dict], panel_size: int) -> float`, `targeted_rate(verdicts, conclusive) -> float`, `effective_rate(verdicts, blanket, conclusive) -> float`, `per_agent_rates(verdicts, conclusive) -> dict[str, float]`, `blanket_rate(blanket, conclusive) -> float`, `like_for_like_change(prev_verdicts, prev_conclusive, cur_verdicts, cur_conclusive) -> float | None`

A `verdicts` argument is a `list[dict]` with keys `domain`, `agent`, `stance`. A `blanket` argument is a `dict[str, str]` mapping domain to blanket stance.

- [ ] **Step 1: Write the failing test**

`tests/test_compute.py`:
```python
import pytest

from tallyhouse.compute import (
    blanket_rate,
    conclusive_domains,
    coverage,
    effective_rate,
    like_for_like_change,
    per_agent_rates,
    targeted_rate,
)

BLOCKING = [{"domain": "a.com", "agent": "GPTBot", "stance": "FullBlock"}]
PARTIAL = [{"domain": "b.com", "agent": "CCBot", "stance": "PartialBlock"}]
QUIET = [{"domain": "c.com", "agent": "GPTBot", "stance": "Unmentioned"}]


def test_only_fetched_and_no_robots_count_as_conclusive():
    observations = [
        {"domain": "a.com", "outcome": "Fetched"},
        {"domain": "b.com", "outcome": "NoRobotsTxt"},
        {"domain": "c.com", "outcome": "Timeout"},
        {"domain": "d.com", "outcome": "ServerError"},
    ]
    assert conclusive_domains(observations) == {"a.com", "b.com"}


def test_coverage_is_conclusive_over_panel_size():
    observations = [
        {"domain": "a.com", "outcome": "Fetched"},
        {"domain": "b.com", "outcome": "Timeout"},
    ]
    assert coverage(observations, panel_size=4) == 25.0


def test_targeted_rate_counts_domains_not_verdict_rows():
    # One domain blocking three agents is still one blocking domain.
    verdicts = [
        {"domain": "a.com", "agent": "GPTBot", "stance": "FullBlock"},
        {"domain": "a.com", "agent": "CCBot", "stance": "FullBlock"},
        {"domain": "a.com", "agent": "ClaudeBot", "stance": "PartialBlock"},
    ]
    assert targeted_rate(verdicts, {"a.com", "b.com"}) == 50.0


def test_partial_block_counts_toward_targeted_rate():
    assert targeted_rate(PARTIAL, {"b.com"}) == 100.0


def test_unmentioned_does_not_count_toward_targeted_rate():
    assert targeted_rate(QUIET, {"c.com"}) == 0.0


def test_targeted_rate_ignores_domains_outside_the_conclusive_set():
    assert targeted_rate(BLOCKING, {"z.com"}) == 0.0


def test_effective_rate_includes_blanket_blocked_domains():
    blanket = {"c.com": "FullBlock"}
    assert effective_rate(QUIET, blanket, {"c.com"}) == 100.0
    # ...whereas the targeted headline must not count it.
    assert targeted_rate(QUIET, {"c.com"}) == 0.0


def test_effective_rate_does_not_double_count():
    blanket = {"a.com": "FullBlock"}
    assert effective_rate(BLOCKING, blanket, {"a.com"}) == 100.0


def test_per_agent_rates_are_reported_separately():
    verdicts = [
        {"domain": "a.com", "agent": "GPTBot", "stance": "FullBlock"},
        {"domain": "b.com", "agent": "GPTBot", "stance": "Unmentioned"},
        {"domain": "a.com", "agent": "CCBot", "stance": "Unmentioned"},
        {"domain": "b.com", "agent": "CCBot", "stance": "Unmentioned"},
    ]
    rates = per_agent_rates(verdicts, {"a.com", "b.com"})
    assert rates == {"GPTBot": 50.0, "CCBot": 0.0}


def test_blanket_rate_counts_fully_closed_sites():
    assert blanket_rate({"a.com": "FullBlock", "b.com": "Allowed"}, {"a.com", "b.com"}) == 50.0


def test_like_for_like_change_uses_only_domains_seen_in_both_weeks():
    # b.com times out this week. Counting it last week but not this week
    # would invent a fall that never happened.
    prev = [
        {"domain": "a.com", "agent": "GPTBot", "stance": "FullBlock"},
        {"domain": "b.com", "agent": "GPTBot", "stance": "FullBlock"},
    ]
    cur = [{"domain": "a.com", "agent": "GPTBot", "stance": "FullBlock"}]
    change = like_for_like_change(prev, {"a.com", "b.com"}, cur, {"a.com"})
    assert change == 0.0


def test_like_for_like_change_detects_a_real_change():
    prev = [{"domain": "a.com", "agent": "GPTBot", "stance": "Unmentioned"},
            {"domain": "b.com", "agent": "GPTBot", "stance": "Unmentioned"}]
    cur = [{"domain": "a.com", "agent": "GPTBot", "stance": "FullBlock"},
           {"domain": "b.com", "agent": "GPTBot", "stance": "Unmentioned"}]
    change = like_for_like_change(prev, {"a.com", "b.com"}, cur, {"a.com", "b.com"})
    assert change == 50.0


def test_like_for_like_change_is_none_without_a_previous_period():
    assert like_for_like_change([], set(), [], set()) is None


def test_rates_with_no_conclusive_domains_raise_rather_than_divide_by_zero():
    with pytest.raises(ValueError):
        targeted_rate([], set())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_compute.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tallyhouse.compute'`

- [ ] **Step 3: Write minimal implementation**

`src/tallyhouse/compute.py`:
```python
"""Index computation. A pure function of classified tables — no I/O, no
network, no clock."""

from tallyhouse.constants import CONCLUSIVE_OUTCOMES

_BLOCKING_STANCES = frozenset({"FullBlock", "PartialBlock"})


def conclusive_domains(observations: list[dict]) -> set[str]:
    return {
        o["domain"] for o in observations if o["outcome"] in CONCLUSIVE_OUTCOMES
    }


def coverage(observations: list[dict], panel_size: int) -> float:
    if panel_size == 0:
        raise ValueError("panel_size must be positive")
    return _pct(len(conclusive_domains(observations)), panel_size)


def _pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        raise ValueError("no conclusive observations to compute a rate over")
    return round(100.0 * numerator / denominator, 4)


def _targeted_domains(verdicts: list[dict], conclusive: set[str]) -> set[str]:
    return {
        v["domain"]
        for v in verdicts
        if v["domain"] in conclusive and v["stance"] in _BLOCKING_STANCES
    }


def targeted_rate(verdicts: list[dict], conclusive: set[str]) -> float:
    return _pct(len(_targeted_domains(verdicts, conclusive)), len(conclusive))


def blanket_blocked(blanket: dict[str, str], conclusive: set[str]) -> set[str]:
    return {d for d, stance in blanket.items() if d in conclusive and stance == "FullBlock"}


def blanket_rate(blanket: dict[str, str], conclusive: set[str]) -> float:
    return _pct(len(blanket_blocked(blanket, conclusive)), len(conclusive))


def effective_rate(
    verdicts: list[dict], blanket: dict[str, str], conclusive: set[str]
) -> float:
    blocked = _targeted_domains(verdicts, conclusive) | blanket_blocked(blanket, conclusive)
    return _pct(len(blocked), len(conclusive))


def per_agent_rates(verdicts: list[dict], conclusive: set[str]) -> dict[str, float]:
    agents = sorted({v["agent"] for v in verdicts})
    rates = {}
    for agent in agents:
        blocking = {
            v["domain"]
            for v in verdicts
            if v["agent"] == agent
            and v["domain"] in conclusive
            and v["stance"] in _BLOCKING_STANCES
        }
        rates[agent] = _pct(len(blocking), len(conclusive))
    return rates


def like_for_like_change(
    prev_verdicts: list[dict],
    prev_conclusive: set[str],
    cur_verdicts: list[dict],
    cur_conclusive: set[str],
) -> float | None:
    """Week-on-week change over domains conclusively observed in both weeks.

    At weekly cadence the true movements are small, so a denominator that
    wobbles between periods could otherwise manufacture a change that never
    happened. Returns None when there is no comparable previous period.
    """
    both = prev_conclusive & cur_conclusive
    if not both:
        return None
    return round(targeted_rate(cur_verdicts, both) - targeted_rate(prev_verdicts, both), 4)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_compute.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add src/tallyhouse/compute.py tests/test_compute.py
git commit -m "feat: index computation with like-for-like week-on-week change"
```

---

### Task 8: The append-only ledger

**Files:**
- Create: `src/tallyhouse/ledger.py`
- Test: `tests/test_ledger.py`

**Interfaces:**
- Consumes: nothing
- Produces: `PRINT_FIELDS: list[str]`, `read_rows(path: Path) -> list[dict]`, `append_row(path: Path, key: dict, row: dict, *, reason: str | None = None) -> dict | None`, `latest(path: Path, key: dict) -> dict | None`, exception `LedgerConflict`

`key` identifies the series point, e.g. `{"index_id": "agent-accessibility", "period": "2026-09-14"}`. `row` carries the value fields. Returns the appended row, or `None` when the value was unchanged.

- [ ] **Step 1: Write the failing test**

`tests/test_ledger.py`:
```python
import pytest

from tallyhouse.ledger import LedgerConflict, append_row, latest, read_rows

KEY = {"index_id": "agent-accessibility", "period": "2026-09-14"}


def row(value, **extra):
    base = {
        "value": value,
        "denominator": "980",
        "coverage": "98.0",
        "methodology_version": "1",
        "collector_version": "abc123",
        "computed_at": "2026-09-17T00:00:00Z",
    }
    base.update(extra)
    return base


def test_first_print_is_vintage_one(tmp_path):
    path = tmp_path / "prints.csv"
    appended = append_row(path, KEY, row("21.4"))
    assert appended["vintage"] == "1"
    assert appended["reason"] == ""


def test_identical_recomputation_is_a_no_op(tmp_path):
    path = tmp_path / "prints.csv"
    append_row(path, KEY, row("21.4"))
    assert append_row(path, KEY, row("21.4")) is None
    assert len(read_rows(path)) == 1


def test_changed_value_without_a_reason_is_refused(tmp_path):
    path = tmp_path / "prints.csv"
    append_row(path, KEY, row("21.4"))
    with pytest.raises(LedgerConflict):
        append_row(path, KEY, row("22.9"))
    # The published number must survive the refused write.
    assert read_rows(path)[0]["value"] == "21.4"


def test_changed_value_with_a_reason_appends_a_new_vintage(tmp_path):
    path = tmp_path / "prints.csv"
    append_row(path, KEY, row("21.4"))
    appended = append_row(path, KEY, row("22.9"), reason="parser fix: Allow precedence")
    assert appended["vintage"] == "2"
    assert appended["reason"] == "parser fix: Allow precedence"
    rows = read_rows(path)
    assert len(rows) == 2
    assert rows[0]["value"] == "21.4"  # vintage 1 is untouched


def test_latest_returns_the_highest_vintage(tmp_path):
    path = tmp_path / "prints.csv"
    append_row(path, KEY, row("21.4"))
    append_row(path, KEY, row("22.9"), reason="restated")
    assert latest(path, KEY)["value"] == "22.9"


def test_periods_are_independent(tmp_path):
    path = tmp_path / "prints.csv"
    append_row(path, KEY, row("21.4"))
    other = dict(KEY, period="2026-09-21")
    assert append_row(path, other, row("21.9"))["vintage"] == "1"


def test_latest_of_an_unknown_key_is_none(tmp_path):
    assert latest(tmp_path / "prints.csv", KEY) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ledger.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tallyhouse.ledger'`

- [ ] **Step 3: Write minimal implementation**

`src/tallyhouse/ledger.py`:
```python
"""The append-only ledger.

This module is the only place allowed to decide that a published number may
change, and it never lets one change silently. Values are stored as strings
so that a round-trip through the file cannot alter them.
"""

import csv
from pathlib import Path

PRINT_FIELDS = [
    "index_id",
    "period",
    "vintage",
    "value",
    "denominator",
    "coverage",
    "methodology_version",
    "collector_version",
    "computed_at",
    "reason",
]

_COMPARED_FIELDS = ("value", "denominator", "coverage")


class LedgerConflict(Exception):
    """Raised when a published value would change without a stated reason."""


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _matching(rows: list[dict], key: dict) -> list[dict]:
    return [r for r in rows if all(r[k] == v for k, v in key.items())]


def latest(path: Path, key: dict) -> dict | None:
    matches = _matching(read_rows(path), key)
    if not matches:
        return None
    return max(matches, key=lambda r: int(r["vintage"]))


def append_row(path: Path, key: dict, row: dict, *, reason: str | None = None) -> dict | None:
    """Append a row, enforcing the vintage rules.

    Returns the appended row, or None when the value is unchanged.
    """
    existing = latest(path, key)
    if existing is not None:
        if all(existing[f] == str(row[f]) for f in _COMPARED_FIELDS):
            return None
        if not reason:
            raise LedgerConflict(
                f"{key} is published as {existing['value']} and would become "
                f"{row['value']}. Supply a reason to append a new vintage."
            )
        vintage = int(existing["vintage"]) + 1
    else:
        vintage = 1

    # Key fields not already in PRINT_FIELDS (e.g. series_id) are appended, so
    # the same ledger code serves both prints.csv and series.csv.
    fields = list(dict.fromkeys([*PRINT_FIELDS, *key]))
    record = {f: "" for f in fields}
    record.update({k: str(v) for k, v in key.items()})
    record.update({k: str(v) for k, v in row.items()})
    record["vintage"] = str(vintage)
    record["reason"] = reason or ""

    is_new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if is_new:
            writer.writeheader()
        writer.writerow(record)
    return record
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ledger.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/tallyhouse/ledger.py tests/test_ledger.py
git commit -m "feat: append-only ledger enforcing immutable prints and vintages"
```

---

### Task 9: Derive stage

**Files:**
- Create: `src/tallyhouse/derive.py`
- Test: `tests/test_derive.py`

**Interfaces:**
- Consumes: `tallyhouse.storage.load_body`, `tallyhouse.parse.classify`, `tallyhouse.parse.blanket_stance`
- Produces: `derive_period(root: Path, period: str, agents: list[str]) -> dict` returning `{"observations": [...], "verdicts": [...], "blanket": {...}}`, and `write_tables(out_dir: Path, period: str, tables: dict) -> None`

- [ ] **Step 1: Write the failing test**

`tests/test_derive.py`:
```python
from tallyhouse.derive import derive_period, write_tables
from tallyhouse.storage import store_body, write_manifest

AGENTS = ["GPTBot", "CCBot"]


def seed(root, period, entries):
    """entries: list of (domain, outcome, body_or_None)"""
    records = []
    for domain, outcome, body in entries:
        sha = store_body(root, body.encode()) if body is not None else None
        records.append({"domain": domain, "outcome": outcome, "sha256": sha,
                        "http_status": 200 if body is not None else None,
                        "fetched_at": "2026-09-14T00:00:00Z", "attempts": 1,
                        "final_url": None, "content_type": None,
                        "bytes": len(body) if body is not None else None})
    write_manifest(root, period, records)


def test_verdicts_are_produced_for_every_agent_on_conclusive_domains(tmp_path):
    seed(tmp_path, "2026-09-14", [("a.com", "Fetched", "User-agent: GPTBot\nDisallow: /\n")])
    tables = derive_period(tmp_path, "2026-09-14", AGENTS)
    stances = {v["agent"]: v["stance"] for v in tables["verdicts"]}
    assert stances == {"GPTBot": "FullBlock", "CCBot": "Unmentioned"}


def test_domains_without_robots_txt_are_conclusive_and_unmentioned(tmp_path):
    seed(tmp_path, "2026-09-14", [("a.com", "NoRobotsTxt", None)])
    tables = derive_period(tmp_path, "2026-09-14", AGENTS)
    stances = {v["stance"] for v in tables["verdicts"]}
    assert stances == {"Unmentioned"}
    assert tables["blanket"]["a.com"] == "Allowed"


def test_inconclusive_domains_produce_no_verdicts(tmp_path):
    seed(tmp_path, "2026-09-14", [("a.com", "Timeout", None)])
    tables = derive_period(tmp_path, "2026-09-14", AGENTS)
    assert tables["verdicts"] == []
    assert "a.com" not in tables["blanket"]


def test_blanket_stance_is_recorded_per_domain(tmp_path):
    seed(tmp_path, "2026-09-14", [("a.com", "Fetched", "User-agent: *\nDisallow: /\n")])
    tables = derive_period(tmp_path, "2026-09-14", AGENTS)
    assert tables["blanket"]["a.com"] == "FullBlock"


def test_derive_is_deterministic(tmp_path):
    seed(tmp_path, "2026-09-14", [
        ("b.com", "Fetched", "User-agent: CCBot\nDisallow: /x\n"),
        ("a.com", "Fetched", "User-agent: GPTBot\nDisallow: /\n"),
    ])
    first = derive_period(tmp_path, "2026-09-14", AGENTS)
    second = derive_period(tmp_path, "2026-09-14", AGENTS)
    assert first == second


def test_write_tables_produces_sorted_csv(tmp_path):
    seed(tmp_path, "2026-09-14", [
        ("b.com", "Fetched", "User-agent: GPTBot\nDisallow: /\n"),
        ("a.com", "Fetched", "User-agent: GPTBot\nDisallow: /\n"),
    ])
    tables = derive_period(tmp_path, "2026-09-14", AGENTS)
    write_tables(tmp_path / "derived", "2026-09-14", tables)
    text = (tmp_path / "derived" / "verdicts.csv").read_text()
    assert text.index("a.com") < text.index("b.com")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_derive.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tallyhouse.derive'`

- [ ] **Step 3: Write minimal implementation**

`src/tallyhouse/derive.py`:
```python
"""Derive classified tables from retained raw evidence.

Pure with respect to the network and the clock: given the same raw/ tree and
the same agent set, it produces identical output forever.
"""

import csv
from pathlib import Path

from tallyhouse.constants import CONCLUSIVE_OUTCOMES
from tallyhouse.parse import blanket_stance, classify
from tallyhouse.storage import load_body, read_manifest

VERDICT_FIELDS = ["domain", "period", "agent", "stance"]
FETCH_FIELDS = [
    "domain", "period", "outcome", "http_status", "final_url",
    "content_type", "bytes", "sha256", "fetched_at", "attempts",
]


def derive_period(root: Path, period: str, agents: list[str]) -> dict:
    observations = sorted(read_manifest(root, period), key=lambda r: r["domain"])
    verdicts: list[dict] = []
    blanket: dict[str, str] = {}

    for record in observations:
        if record["outcome"] not in CONCLUSIVE_OUTCOMES:
            continue
        sha = record.get("sha256")
        body = load_body(root, sha).decode("utf-8", errors="replace") if sha else ""
        blanket[record["domain"]] = blanket_stance(body)
        for agent in agents:
            verdicts.append(
                {
                    "domain": record["domain"],
                    "period": period,
                    "agent": agent,
                    "stance": classify(body, agent),
                }
            )

    return {"observations": observations, "verdicts": verdicts, "blanket": blanket}


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_tables(out_dir: Path, period: str, tables: dict) -> None:
    verdicts = sorted(tables["verdicts"], key=lambda r: (r["domain"], r["agent"]))
    _write_csv(out_dir / "verdicts.csv", VERDICT_FIELDS, verdicts)

    fetches = [dict(o, period=period) for o in tables["observations"]]
    _write_csv(out_dir / "fetches.csv", FETCH_FIELDS, fetches)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_derive.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/tallyhouse/derive.py tests/test_derive.py
git commit -m "feat: derive classified tables from raw evidence"
```

---

### Task 10: End-to-end pipeline test

**Files:**
- Create: `tests/test_pipeline.py`
- Modify: none

**Interfaces:**
- Consumes: everything above
- Produces: confidence that the stages compose

- [ ] **Step 1: Write the failing test**

`tests/test_pipeline.py`:
```python
"""Walks a tiny panel from raw evidence through to a published print."""

import pytest

from tallyhouse.compute import conclusive_domains, coverage, targeted_rate
from tallyhouse.derive import derive_period
from tallyhouse.ledger import append_row, read_rows
from tallyhouse.storage import store_body, write_manifest

AGENTS = ["GPTBot", "CCBot"]
PERIOD = "2026-09-14"
KEY = {"index_id": "agent-accessibility", "period": PERIOD}


def seed(root):
    bodies = {
        "blocks.com": "User-agent: GPTBot\nDisallow: /\n",
        "open.com": "User-agent: *\nAllow: /\n",
        "closed.com": "User-agent: *\nDisallow: /\n",
    }
    records = [
        {"domain": d, "outcome": "Fetched", "sha256": store_body(root, b.encode()),
         "http_status": 200, "final_url": f"https://{d}/robots.txt",
         "content_type": "text/plain", "bytes": len(b),
         "fetched_at": "2026-09-14T00:00:00Z", "attempts": 1}
        for d, b in bodies.items()
    ]
    records.append({"domain": "down.com", "outcome": "Timeout", "sha256": None,
                    "http_status": None, "final_url": None, "content_type": None,
                    "bytes": None, "fetched_at": "2026-09-14T00:00:00Z", "attempts": 3})
    write_manifest(root, PERIOD, records)


def test_pipeline_produces_a_print_matching_hand_computation(tmp_path):
    seed(tmp_path)
    tables = derive_period(tmp_path, PERIOD, AGENTS)

    conclusive = conclusive_domains(tables["observations"])
    assert conclusive == {"blocks.com", "open.com", "closed.com"}

    # Of 4 panel domains, 3 were conclusively observed.
    assert coverage(tables["observations"], panel_size=4) == 75.0

    # Only blocks.com names an AI agent and disallows it. closed.com is shut to
    # everyone but targets nobody, so it must not count here.
    assert targeted_rate(tables["verdicts"], conclusive) == pytest.approx(33.3333, abs=1e-3)

    path = tmp_path / "prints.csv"
    append_row(path, KEY, {
        "value": "33.3333", "denominator": "3", "coverage": "75.0",
        "methodology_version": "1", "collector_version": "test",
        "computed_at": "2026-09-17T00:00:00Z",
    })
    assert read_rows(path)[0]["vintage"] == "1"


def test_rerunning_the_pipeline_changes_nothing(tmp_path):
    seed(tmp_path)
    path = tmp_path / "prints.csv"
    row = {"value": "33.3333", "denominator": "3", "coverage": "75.0",
           "methodology_version": "1", "collector_version": "test",
           "computed_at": "2026-09-17T00:00:00Z"}
    append_row(path, KEY, row)
    assert append_row(path, KEY, row) is None
    assert len(read_rows(path)) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_pipeline.py -v`
Expected: FAIL (the assertions exercise real behaviour; fix any genuine defects they expose rather than weakening the test)

- [ ] **Step 3: Make it pass**

No new production code should be required. If a test fails, the defect is in an earlier task's module — fix it there and re-run that task's tests too.

- [ ] **Step 4: Run the whole suite**

Run: `python3 -m pytest -v`
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add tests/test_pipeline.py
git commit -m "test: end-to-end pipeline from raw evidence to published print"
```

---

---

### Task 11: Collection run

**Files:**
- Create: `src/tallyhouse/run_collect.py`
- Test: `tests/test_run_collect.py`

**Interfaces:**
- Consumes: `tallyhouse.collect.fetch_domain`, `tallyhouse.storage.store_body`, `tallyhouse.storage.write_manifest`, `tallyhouse.config.load_panel`
- Produces: `async collect_panel(root: Path, period: str, domains: list[str], *, client, concurrency: int = 8) -> list[dict]` — fetches every domain, stores bodies, writes the manifest, and returns the manifest records (with `sha256`, without `body`).

- [ ] **Step 1: Write the failing test**

`tests/test_run_collect.py`:
```python
import httpx
import pytest

from tallyhouse.run_collect import collect_panel
from tallyhouse.storage import load_body, read_manifest


def client_returning(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_collect_panel_stores_bodies_and_writes_manifest(tmp_path):
    def handler(request):
        return httpx.Response(200, text=f"# {request.url.host}\nUser-agent: *\nDisallow:\n",
                              headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        records = await collect_panel(tmp_path, "2026-09-14", ["a.com", "b.com"], client=client)

    assert len(records) == 2
    manifest = read_manifest(tmp_path, "2026-09-14")
    assert [r["domain"] for r in manifest] == ["a.com", "b.com"]
    sha = manifest[0]["sha256"]
    assert load_body(tmp_path, sha).startswith(b"# a.com")


async def test_manifest_records_never_contain_raw_bodies(tmp_path):
    def handler(request):
        return httpx.Response(200, text="body", headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        await collect_panel(tmp_path, "2026-09-14", ["a.com"], client=client)

    # Bodies belong in content-addressed storage, never inlined in the manifest.
    assert "body" not in read_manifest(tmp_path, "2026-09-14")[0]


async def test_failed_domains_appear_in_the_manifest_with_no_sha(tmp_path):
    def handler(request):
        raise httpx.ConnectTimeout("down")

    async with client_returning(handler) as client:
        await collect_panel(tmp_path, "2026-09-14", ["down.com"], client=client, attempts=1)

    record = read_manifest(tmp_path, "2026-09-14")[0]
    assert record["outcome"] == "Timeout"
    assert record["sha256"] is None


async def test_identical_bodies_across_domains_share_one_stored_file(tmp_path):
    def handler(request):
        return httpx.Response(200, text="same for everyone",
                              headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        await collect_panel(tmp_path, "2026-09-14", ["a.com", "b.com", "c.com"], client=client)

    assert len(list(tmp_path.rglob("*.txt.gz"))) == 1


async def test_concurrency_is_capped(tmp_path):
    state = {"now": 0, "peak": 0}

    def handler(request):
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        state["now"] -= 1
        return httpx.Response(200, text="x", headers={"content-type": "text/plain"})

    domains = [f"d{i}.com" for i in range(20)]
    async with client_returning(handler) as client:
        await collect_panel(tmp_path, "2026-09-14", domains, client=client, concurrency=4)

    assert state["peak"] <= 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_run_collect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tallyhouse.run_collect'`

- [ ] **Step 3: Write minimal implementation**

`src/tallyhouse/run_collect.py`:
```python
"""Orchestrates a collection run across the whole panel.

Concurrency is capped deliberately: the index is about crawler etiquette, so
the crawler that produces it must be beyond reproach. One request per domain
per week is negligible load, but a burst of a thousand simultaneous
connections is not a good look.
"""

import asyncio
from pathlib import Path

import httpx

from tallyhouse.collect import fetch_domain
from tallyhouse.storage import store_body, write_manifest


async def collect_panel(
    root: Path,
    period: str,
    domains: list[str],
    *,
    client: httpx.AsyncClient,
    concurrency: int = 8,
    attempts: int = 3,
) -> list[dict]:
    semaphore = asyncio.Semaphore(concurrency)

    async def one(domain: str) -> dict:
        async with semaphore:
            return await fetch_domain(client, domain, attempts=attempts)

    results = await asyncio.gather(*(one(d) for d in domains))

    records = []
    for result in results:
        record = dict(result)
        body = record.pop("body")
        record["sha256"] = store_body(root, body) if body is not None else None
        records.append(record)

    write_manifest(root, period, records)
    return sorted(records, key=lambda r: r["domain"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_run_collect.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/tallyhouse/run_collect.py tests/test_run_collect.py
git commit -m "feat: panel-wide collection run with capped concurrency"
```

---

### Task 12: Print assembly

**Files:**
- Create: `src/tallyhouse/publish.py`
- Test: `tests/test_publish.py`

**Interfaces:**
- Consumes: `tallyhouse.compute.*`, `tallyhouse.ledger.append_row`
- Produces: `PROVISIONAL_COVERAGE_THRESHOLD: float`, `build_print(tables, prev_tables, panel_size, *, methodology_version, collector_version, computed_at) -> dict`, `record_print(root, period, built, *, reason=None) -> None`

`build_print` returns `{"headline": {...}, "series": {series_id: {...}}, "provisional": bool}`.

- [ ] **Step 1: Write the failing test**

`tests/test_publish.py`:
```python
from tallyhouse.ledger import read_rows
from tallyhouse.publish import (
    PROVISIONAL_COVERAGE_THRESHOLD,
    build_print,
    record_print,
)

META = {
    "methodology_version": "1",
    "collector_version": "test",
    "computed_at": "2026-09-17T00:00:00Z",
}


def tables(observations, verdicts, blanket):
    return {"observations": observations, "verdicts": verdicts, "blanket": blanket}


def simple(n_blocking=1, n_total=2, outcome="Fetched"):
    obs = [{"domain": f"d{i}.com", "outcome": outcome} for i in range(n_total)]
    verdicts = [
        {"domain": f"d{i}.com", "agent": "GPTBot",
         "stance": "FullBlock" if i < n_blocking else "Unmentioned"}
        for i in range(n_total)
    ]
    blanket = {f"d{i}.com": "Allowed" for i in range(n_total)}
    return tables(obs, verdicts, blanket)


def test_headline_is_the_targeted_rate():
    built = build_print(simple(1, 2), None, panel_size=2, **META)
    assert built["headline"]["value"] == 50.0


def test_series_include_effective_blanket_coverage_and_per_agent():
    built = build_print(simple(1, 2), None, panel_size=2, **META)
    assert "effective" in built["series"]
    assert "blanket" in built["series"]
    assert "coverage" in built["series"]
    assert "agent:GPTBot" in built["series"]


def test_print_is_provisional_below_the_coverage_threshold():
    # 2 of 100 panel domains observed.
    built = build_print(simple(1, 2), None, panel_size=100, **META)
    assert built["provisional"] is True


def test_print_is_not_provisional_at_full_coverage():
    built = build_print(simple(1, 2), None, panel_size=2, **META)
    assert built["provisional"] is False
    assert PROVISIONAL_COVERAGE_THRESHOLD <= 100.0


def test_week_on_week_series_is_absent_without_a_previous_period():
    built = build_print(simple(1, 2), None, panel_size=2, **META)
    assert "change_wow" not in built["series"]


def test_week_on_week_series_appears_with_a_previous_period():
    built = build_print(simple(2, 2), simple(1, 2), panel_size=2, **META)
    assert built["series"]["change_wow"]["value"] == 50.0


def test_record_print_writes_both_ledgers(tmp_path):
    built = build_print(simple(1, 2), None, panel_size=2, **META)
    record_print(tmp_path, "2026-09-14", built)
    prints = read_rows(tmp_path / "prints.csv")
    series = read_rows(tmp_path / "series.csv")
    assert prints[0]["value"] == "50.0"
    assert prints[0]["vintage"] == "1"
    assert {r["series_id"] for r in series} >= {"effective", "blanket", "coverage"}


def test_recording_the_same_print_twice_is_a_no_op(tmp_path):
    built = build_print(simple(1, 2), None, panel_size=2, **META)
    record_print(tmp_path, "2026-09-14", built)
    record_print(tmp_path, "2026-09-14", built)
    assert len(read_rows(tmp_path / "prints.csv")) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_publish.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tallyhouse.publish'`

- [ ] **Step 3: Write minimal implementation**

`src/tallyhouse/publish.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_publish.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/tallyhouse/publish.py tests/test_publish.py
git commit -m "feat: assemble prints and series with provisional coverage flag"
```

---

### Task 13: Command line interface

**Files:**
- Create: `src/tallyhouse/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above
- Produces: `main(argv: list[str]) -> int` with subcommands `collect`, `derive`, `print`

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
import json

import pytest

from tallyhouse.cli import main
from tallyhouse.ledger import read_rows
from tallyhouse.storage import store_body, write_manifest


def seed_config(root):
    (root / "agents").mkdir(parents=True, exist_ok=True)
    (root / "agents" / "v1.json").write_text(
        json.dumps({"version": 1, "agents": ["GPTBot"]})
    )
    (root / "panel").mkdir(parents=True, exist_ok=True)
    (root / "panel" / "2026.json").write_text(
        json.dumps({"year": 2026, "tranco_list_id": "TEST1",
                    "captured": "2026-01-05T00:00:00Z",
                    "domains": ["a.com", "b.com"]})
    )


def seed_raw(root):
    records = []
    for domain, body in [("a.com", "User-agent: GPTBot\nDisallow: /\n"),
                         ("b.com", "User-agent: *\nAllow: /\n")]:
        records.append({"domain": domain, "outcome": "Fetched",
                        "sha256": store_body(root, body.encode()),
                        "http_status": 200, "final_url": None,
                        "content_type": "text/plain", "bytes": len(body),
                        "fetched_at": "2026-09-14T00:00:00Z", "attempts": 1})
    write_manifest(root, "2026-09-14", records)


def test_derive_writes_tables(tmp_path):
    seed_config(tmp_path)
    seed_raw(tmp_path)
    assert main(["derive", "--root", str(tmp_path), "--period", "2026-09-14"]) == 0
    assert (tmp_path / "derived" / "verdicts.csv").exists()


def test_print_writes_a_ledger_row(tmp_path):
    seed_config(tmp_path)
    seed_raw(tmp_path)
    assert main(["print", "--root", str(tmp_path), "--period", "2026-09-14"]) == 0
    rows = read_rows(tmp_path / "prints.csv")
    assert rows[0]["value"] == "50.0"


def test_reprinting_an_unchanged_period_succeeds_without_duplicating(tmp_path):
    seed_config(tmp_path)
    seed_raw(tmp_path)
    main(["print", "--root", str(tmp_path), "--period", "2026-09-14"])
    assert main(["print", "--root", str(tmp_path), "--period", "2026-09-14"]) == 0
    assert len(read_rows(tmp_path / "prints.csv")) == 1


def test_changed_result_without_a_reason_exits_nonzero(tmp_path):
    seed_config(tmp_path)
    seed_raw(tmp_path)
    main(["print", "--root", str(tmp_path), "--period", "2026-09-14"])

    # Change the evidence so the computed value differs.
    write_manifest(tmp_path, "2026-09-14", [
        {"domain": "a.com", "outcome": "Fetched",
         "sha256": store_body(tmp_path, b"User-agent: *\nAllow: /\n"),
         "http_status": 200, "final_url": None, "content_type": "text/plain",
         "bytes": 24, "fetched_at": "2026-09-14T00:00:00Z", "attempts": 1},
    ])
    assert main(["print", "--root", str(tmp_path), "--period", "2026-09-14"]) != 0
    assert len(read_rows(tmp_path / "prints.csv")) == 1


def test_invalid_period_is_rejected(tmp_path):
    seed_config(tmp_path)
    with pytest.raises(SystemExit):
        main(["derive", "--root", str(tmp_path), "--period", "2026-09-16"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tallyhouse.cli'`

- [ ] **Step 3: Write minimal implementation**

`src/tallyhouse/cli.py`:
```python
"""Command line entry points for the pipeline stages.

Each stage is separately runnable so that a failed collect never corrupts
published data, and derive/print can be re-run freely at any time.
"""

import argparse
import asyncio
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

from tallyhouse.config import load_agents, load_panel
from tallyhouse.derive import derive_period, write_tables
from tallyhouse.ledger import LedgerConflict
from tallyhouse.periods import InvalidPeriod, parse_period, period_for, previous_period
from tallyhouse.publish import build_print, record_print
from tallyhouse.run_collect import collect_panel

METHODOLOGY_VERSION = "1"


def _collector_version() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def _load(root: Path, period: str):
    year = parse_period(period).year
    panel = load_panel(root, year)
    agents = load_agents(root, 1)
    return panel, agents


def _cmd_collect(args) -> int:
    root = Path(args.root)
    panel, _ = _load(root, args.period)

    async def run():
        async with httpx.AsyncClient(timeout=20.0) as client:
            await collect_panel(root, args.period, panel.domains, client=client)

    asyncio.run(run())
    return 0


def _cmd_derive(args) -> int:
    root = Path(args.root)
    _, agents = _load(root, args.period)
    tables = derive_period(root, args.period, agents)
    write_tables(root / "derived", args.period, tables)
    return 0


def _cmd_print(args) -> int:
    root = Path(args.root)
    panel, agents = _load(root, args.period)
    tables = derive_period(root, args.period, agents)

    previous = previous_period(args.period)
    try:
        prev_tables = derive_period(root, previous, agents)
    except FileNotFoundError:
        prev_tables = None

    built = build_print(
        tables,
        prev_tables,
        panel_size=len(panel.domains),
        methodology_version=METHODOLOGY_VERSION,
        collector_version=_collector_version(),
        computed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    try:
        record_print(root, args.period, built, reason=args.reason)
    except LedgerConflict as exc:
        print(f"refusing to change a published number: {exc}", file=sys.stderr)
        return 1
    if built["provisional"]:
        print("warning: coverage below threshold, print marked provisional", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tallyhouse")
    parser.add_argument("--root", default="data")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("collect", "derive", "print"):
        child = sub.add_parser(name)
        child.add_argument("--root", default="data")
        child.add_argument("--period", default=period_for(datetime.now(timezone.utc)))
        if name == "print":
            child.add_argument("--reason", default=None)

    args = parser.parse_args(argv)
    try:
        parse_period(args.period)
    except InvalidPeriod as exc:
        parser.error(str(exc))

    return {
        "collect": _cmd_collect,
        "derive": _cmd_derive,
        "print": _cmd_print,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
```

Note: `_cmd_print` computes values from `derive_period` rather than reading
`derived/`, so a print can never be produced from stale tables.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cli.py -v`
Expected: 5 passed

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest -v`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add src/tallyhouse/cli.py tests/test_cli.py
git commit -m "feat: command line interface for collect, derive and print"
```

---

## Not in this plan

Deliberately deferred to the site-generation plan: the Elm HTML AST and escaping,
the embedded QuickJS runtime, page templates, the SVG chart, panel search, and
publishing to GitHub Pages.

Deferred to first real operation: acquiring and freezing the Tranco panel file
(`data/panel/2026.json`), and calibrating the provisional-print coverage threshold
from a real collection run, per the spec.
