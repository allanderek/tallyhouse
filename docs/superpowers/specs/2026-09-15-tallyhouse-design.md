# Tallyhouse — Design

**Date:** 2026-09-15
**Status:** Approved for planning
**Scope:** v1 — the index platform plus its first index, the Agent Accessibility Index.

---

## 1. Purpose

Tallyhouse hosts a small number of hand-built indices. An *index*, as opposed to a
scrape or a comparison table, commits to four things:

1. A **fixed panel**, chosen in advance and frozen.
2. A **published methodology**, versioned.
3. A **reproducible print** — anyone can re-derive the number from retained evidence.
4. **Continuity** — published numbers never silently change.

The project is a portfolio/play project. Ceremony is kept low, but the four
commitments above are kept, because they cost almost nothing when designed in on
day one and cannot be retrofitted. They are also the gap in the incumbents.

v1 ships the shared platform and one index. Indices two and three (open-weight
inference pricing; SaaS list-price inflation) are out of scope but shape the
architecture: the platform must make index #2 cheap.

## 2. Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Revisions | Frozen prints, corrections as new **vintages** | A published number is immutable; a restatement is a new row with a reason. Standard statistical-agency practice and the thing that makes an index citable. |
| System of record | Files in git, not a database | Raw evidence and the print ledger are the ground truth; any database is a derived cache. Makes the serving layer swappable and the methodology verifiable by a stranger. |
| Site | Fully static | Once arbitrary-domain lookup is dropped, nothing needs a server. |
| Collector | Python | Crawling 1000 flaky domains is exactly the wrong place to be adventurous. |
| Generator | Elm, own HTML AST | A pure function of committed inputs — the cheapest-to-fail component, and therefore the right place for the one piece of novelty. |
| Hosting | Public repo + Pages | No uptime burden, and it makes "reproducible" literally true. |
| Database | **None** | See Appendix A. |

### 2.1 Rejected: Acadia

Acadia was the original motivation. It was investigated and rejected — findings in
Appendix A. The short version: unregistered installations cannot use persistent
SQLite files, so persistence requires a paid Server installation, and the project
is nothing but persistent accumulating data. The architecture below is
deliberately arranged so that a database can be reintroduced later as a pure
cache, without re-collecting anything.

## 3. Repository layout

```
collect/              python — fetch robots.txt for the panel
derive/               python — parse, classify, compute prints
generate/             elm   — derived/ -> site manifest (pure, offline)
                      driven in-process by Python via embedded QuickJS
data/
  panel/<year>.json         frozen annual panel + Tranco list id
  agents/v<n>.json          tracked AI-agent set, versioned
  raw/
    bodies/<sha256>.txt.gz  content-addressed, shared across all periods
    <period>/manifest.json  domain -> observation metadata
  derived/
    panel.csv               period, rank, domain
    fetches.csv             one row per domain per period
    verdicts.csv            one row per domain per period per agent
  prints.csv                append-only headline ledger
  series.csv                append-only sub-series ledger
site/                 built output
docs/                 methodology sources, this spec
```

Bodies are content-addressed globally rather than per period, so the ~90% of
`robots.txt` files unchanged month to month cost nothing to retain. Expected
growth is a few MB per year — comfortable in git for decades.

## 4. Data model

### 4.1 Print ledger — `data/prints.csv`

Append-only. Rows are never edited or deleted.

```
index_id, period, vintage, value, denominator, coverage,
methodology_version, collector_version, computed_at, reason
```

- `vintage` starts at 1 and increments per `(index_id, period)`.
- `reason` is empty for vintage 1, and mandatory thereafter.
- The site shows the highest vintage by default and links to earlier ones.
- `methodology_version` is the agent-set version combined with the pinned
  `protego` version — anything that can change a verdict from identical raw input.
- `collector_version` is the git commit of `collect/` that produced the evidence.
- Git history is the audit trail: every restatement is a commit with a diff.

### 4.2 Series ledger — `data/series.csv`

Same key plus `series_id`, for sub-series (per-agent rates, the blanket-block
control series, coverage). **Append-only under the same vintage discipline as
`prints.csv`** — published sub-series are as immutable as the headline, and a
changed value appends a new vintage rather than overwriting.

`data/derived/` by contrast is wholly regenerable scratch: delete it and re-run
`derive` to reproduce it exactly.

### 4.3 Observations — `data/derived/fetches.csv`

```
domain, period, outcome, http_status, final_url, content_type,
bytes, sha256, fetched_at, attempts
```

`outcome` is one of `Fetched | NoRobotsTxt | ServerError | Timeout | DnsFailure |
NotPlainText | TooLarge`.

### 4.4 Verdicts — `data/derived/verdicts.csv`

```
domain, period, agent, stance
```

`stance` is one of `FullBlock | PartialBlock | Allowed | Unmentioned`.

## 5. Pipeline

Four stages, each independently runnable, each a pure function of its inputs
except `collect`.

### 5.1 collect (python, networked)

For each domain in the frozen panel, one request per period to
`https://<domain>/robots.txt`, falling back to `http://` and to the `www.` host.

- Identifies itself honestly and links to `/about/crawler/`.
- Concurrency-capped, spread over hours, exponential backoff.
- Retries across several days before declaring a non-conclusive outcome.
- Writes `raw/bodies/<sha256>.txt.gz` and `raw/<period>/manifest.json`.
- Never writes to `derived/` or `prints.csv`.

Bodies over a size cap are recorded as `TooLarge` with the body truncated but
retained, so the cap can be revisited later without re-collecting.

### 5.2 derive (python, offline, deterministic)

Parses every retained body with **`protego`** (RFC 9309-compliant; explicitly not
`urllib.robotparser`, which mishandles group merging and precedence), producing
`verdicts.csv` and `fetches.csv` in `derived/`, plus candidate values for the
headline print and every sub-series.

Each candidate is compared against the corresponding ledger (`prints.csv` for the
headline, `series.csv` for sub-series); the rules below apply identically to both:

- No existing row for the period → append as vintage 1.
- Existing row with an identical value → no-op.
- Existing row with a different value → append a new vintage; `reason` must be
  supplied explicitly by the operator. The run fails rather than guessing.

### 5.3 generate (elm, offline, pure)

Python assembles one JSON document from `derived/` and passes it as flags. Elm
renders and emits a manifest of `[{path, content}]` through a port. Python writes
the files.

**There is no Node.** The compiled Elm runs inside an embedded QuickJS
interpreter (the `quickjs` PyPI package) in the Python process — no subprocess, no
stdout parsing, no JS runtime installed system-wide. The JS engine is a pinned
Python dependency like any other, which is a far better bet for a project whose
central claim is that a stranger can clone the repo in ten years and re-derive
every number. Verified byte-identical to Node and Duktape at 1000-row scale, and
faster than both (see Appendix B).

Two things the embedding requires, both non-obvious:

- **A four-line `setTimeout` shim.** Elm's scheduler genuinely calls `setTimeout`
  during `Platform.worker` startup. A minimal job queue (`push` on `setTimeout`,
  drain after `init`) is sufficient and makes effect ordering deterministic. It
  also explains why subscribing to a port *after* `init` works: the send is
  deferred into that queue.
- **An explicitly raised stack limit.** QuickJS's default stack overflows on
  Elm's list recursion at around 1000 elements — which is exactly the panel page.
  `set_max_stack_size(64MB)` clears it. If a future index needs pages with many
  more rows than the panel, chunk the page rather than raising the limit further.

- The generator **never opens a socket**. Determinism is the product.
- HTML is built from a hand-rolled AST (`Node tag attrs kids | Text s`) with an
  owned `escape` function. This is load-bearing: the site renders attacker-
  controlled text from 1000 strangers' servers. Verified during the spike — a
  body containing `</pre><script>alert('xss')</script>` was correctly neutralised.
- Charts are inline SVG generated by Elm. No charting library, no runtime JS.
- Elm's output ends `}(this))`. Evaluated as a script in QuickJS, `this` is the
  global object, so `Elm` lands on `globalThis` and it simply works. (Under Node
  this would need CommonJS, since `this` is `undefined` in an ES module.)

### 5.4 publish

Commit `data/`, push, and publish `site/` to a `gh-pages` branch. (`docs/` holds
this spec and the methodology sources, so the Pages "docs folder" option is not
used.)

## 6. The Agent Accessibility Index

### 6.1 Cadence and period identifiers

The index prints **monthly**. A `period` is written `YYYY-MM` and refers to the
month in which collection began. Collection starts on the first of the month.

### 6.2 Panel

Tranco top 1000, **frozen annually**. `data/panel/<year>.json` pins the Tranco
list ID and capture date, so the panel is falsifiable rather than asserted. The
basket is fixed for the year, so the index measures behaviour change rather than
composition change. Rebasing happens each January, with both panels published
across the overlap period so the chain is visible.

### 6.3 Agent set

`data/agents/v1.json`, versioned data rather than source code, because new
crawlers appear constantly. Initial set includes GPTBot, ChatGPT-User,
OAI-SearchBot, ClaudeBot, anthropic-ai, CCBot, Google-Extended, PerplexityBot,
Bytespider, Amazonbot, Applebot-Extended, meta-externalagent, Diffbot, ImagesiftBot.

Changing the agent set makes the series non-comparable, so it is a methodology
version bump that triggers recomputation of **all** history as new vintages, with
`reason` recording the change. Retained raw evidence makes this mechanical.

### 6.4 Headline

**Targeted AI blocking:** the percentage of conclusively-observed panel domains
that name at least one agent from the tracked set and disallow it (`FullBlock` or
`PartialBlock`).

A blanket `User-agent: * / Disallow: /` blocks AI crawlers but expresses nothing
about AI specifically, so it is excluded from the headline and published as a
separate control series.

**Both the targeted series and the effective-block series (targeted or blanket)
are computed and published from the first print.** They derive from the same
parse, so publishing both costs nothing, and it keeps the choice of headline a
presentation decision rather than a data decision. If the gap between them turns
out to be large, the effective series can be promoted to co-equal later with
complete history behind it and no gap in the record.

Sub-series published from day one: per-agent block rate; blanket-block rate;
coverage.

### 6.5 Integrity rules

Fixed in advance and published, because deciding them after seeing a bad month is
how indices lose credibility.

- **Denominator** is conclusive observations only. `NoRobotsTxt` is conclusive —
  no `robots.txt` means not blocking. `Timeout`, `DnsFailure` and `ServerError`
  are not, and are excluded from both numerator and denominator.
- **Coverage** — conclusive observations as a share of the panel — is published
  alongside every print.
- A print with coverage below **97%** is marked **provisional** and the site
  labels it as such.

## 7. Site structure

```
/                          all indices, current prints
/agent-accessibility/      headline, chart, series table, downloads
  /methodology/            versioned, with a changelog
  /panel/                  the 1000 domains, searchable
  /domain/<domain>/        per-domain history and observed robots.txt
  /releases/<period>/      the frozen print for that period
/about/
/about/crawler/            who the crawler is, and how to contact
```

Downloads per index: `series.csv`, `panel-<period>.csv`, `verdicts-<period>.csv`.

The only JavaScript shipped to the browser is panel search over a ~50KB JSON
file. Everything else is documents. Per-domain pages have permanent URLs and
work without JS.

## 8. Testing

- **Parser:** RFC 9309 examples, plus a fixture corpus of awkward real-world
  `robots.txt` harvested from `raw/`.
- **Derive:** golden tests pinning fixed raw input to expected prints, verdicts
  and coverage.
- **Ledger:** tests that a changed value without a `reason` fails the run, and
  that vintages append rather than overwrite.
- **Generator:** snapshot tests of rendered pages; escaping tests covering markup,
  quotes and ampersands in body content.
- **Determinism:** run `derive` + `generate` twice over identical inputs and
  assert byte-identical output.

## 9. Operations

Monthly cron: `collect` → `derive` → `generate` → commit → push. Stages are
separately runnable so a failed `collect` never corrupts published data, and
`derive`/`generate` can be re-run freely at any time.

## 10. Out of scope for v1

Indices two and three; arbitrary-domain lookup (needs a server, rate limiting and
abuse controls); per-print written commentary and RSS; any public API beyond the
CSV downloads; a database of any kind.

---

## Appendix A — Acadia investigation

Acadia 0.3.1 was evaluated as the storage and serving layer and rejected.

**Verified working.** A Tallyhouse-shaped schema compiles: composite natural keys,
foreign keys, `btree Unique/NotUnique` indexes, custom types. Error messages are
excellent. Endpoint calls are `POST /_endpoints`, body
`uint32BE moduleId, uint32BE endpointId, args`; strings are `uint32BE length +
UTF-8`; variants are `uint32BE payloadSize + uint8 tag + payload`. An `Accept`
header is required or the server returns 406. A hand-written Python client
successfully inserted and read back rows.

**Blocking issue.** `acadia register` reports that unregistered installations have
`make/serve/plan/sign/publish` but not `+SQLite`; persistent SQLite files require
a paid Personal or Server installation. A VPS deployment needs a Server
installation specifically.

**Other findings.**

- Duplicate primary key insert fails with HTTP 418; writes are not idempotent, so
  re-running a period's collection would error.
- Multi-variant custom types are not comparable and cannot be primary or index
  keys. Only primitives, single-variant "boxed" wrappers, and tuples. This forced
  `Agent` from a sum type into `Agent String` plus a versioned agent table — which
  is the better design and is retained above.
- Endpoint IDs are compiler-assigned and shifted when an endpoint was added.
  Published-history workflows are documented to keep them stable, so this is less
  severe than it first appeared.
- `hints/sqlite-to-acadia.md` sanctions bulk loading via raw SQL into a published
  `acadia.sqlite`.

**Reintroduction path.** Because raw evidence and the print ledger are files, a
database can later be added as a pure derived cache — rebuilt from scratch on each
run, which also sidesteps the 418 idempotency problem entirely — without
re-collecting anything or migrating any data.

## Appendix B — JS runtime for the generator

Elm's compiled output is close to plain ES5. By inspection it references no
`XMLHttpRequest`, no `window` and no `require`; `console` appears only inside
`_Debug_log_UNUSED` and `document` only inside error-message strings.

`setTimeout` is the exception, and inspection was misleading here: it appears
textually only inside `_Process_sleep`, but the scheduler calls it during
`Platform.worker` startup. A bare QuickJS context fails with
`ReferenceError: 'setTimeout' is not defined`. The four-line job-queue shim in 5.3
resolves it.

A minimal `Platform.worker` generator was compiled and run under five runtimes.
At 1000 rows (~321KB of HTML), all produced **byte-identical** output:

| Runtime | Time | Notes |
|---|---|---|
| QuickJS (embedded in Python) | 0.15s | Fastest; needs the shim and a raised stack limit |
| Duktape via `dukpy` (embedded) | 0.17s | Works with the same shim |
| Node 24 | 0.20s | Subprocess; needs CommonJS loading |
| Bun 1.3 / Deno 2 | ~0.05s at small scale | Verified identical output; not benchmarked at 1000 rows |

QuickJS embedded in Python is chosen. It removes Node from the build entirely,
turns the JS engine into a pinned Python dependency, and collapses the pipeline
into a single process with no subprocess boundary and no stdout parsing.

The one sharp edge is the stack limit: QuickJS's default overflows on Elm's
`List.map`/`String.concat` recursion at around 1000 elements. This is a property
of list length, not page size, so it scales with the panel.
