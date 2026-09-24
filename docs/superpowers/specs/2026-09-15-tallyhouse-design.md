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
| Hosting | Public GitHub repo + GitHub Pages | No uptime burden, and it makes "reproducible" literally true. |
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
`robots.txt` files unchanged between periods cost nothing to retain. Weekly
collection barely changes this — files change *less* week to week than month to
month, so the deduplication ratio improves. The growing part is the per-period
manifests and ledgers, which are gzipped CSV/JSON at roughly 200KB per period.
Expected growth is a few MB per year — comfortable in git for decades.

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
`derive` to reproduce it exactly. It is therefore **gitignored**. This matters
more at weekly cadence — `verdicts.csv` alone is roughly 14,000 rows per period,
so committing it would add tens of MB a year to no purpose. Anyone wanting the
tables without running the pipeline downloads them from the site.

### 4.3 Observations — `data/derived/fetches.csv`

```
domain, period, outcome, http_status, final_url, content_type,
bytes, sha256, fetched_at, attempts
```

`outcome` is one of `Fetched | NoRobotsTxt | ServerError | Challenged | Timeout |
DnsFailure | ConnectFailure | TransportError | NotPlainText | TooLarge`.

Only `Fetched` and `NoRobotsTxt` are conclusive; the rest are recorded so that
*why* a domain was unobservable is itself evidence. `ConnectFailure` and
`TransportError` were added during implementation: the original list forced
connection-refused and TLS failures to be recorded as `DnsFailure`, connection
resets as `Timeout`, and left redirect loops and protocol errors with no bucket
at all — which crashed the collector rather than recording an outcome.

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
- Retries with backoff inside the 72-hour collection window before declaring a
  non-conclusive outcome.
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

Commit `data/`, push, and publish `site/` to a `gh-pages` branch, served by
**GitHub Pages**. (`docs/` holds this spec and the methodology sources, so the
Pages "docs folder" option is not used.)

Nothing in the design depends on GitHub specifically — the build output is a
directory of static files, so GitLab/Codeberg/Cloudflare Pages or any static host
is a one-line change to the publish step. GitHub is chosen because the repo lives
there already.

Notes on the deployment path:

- Pushing from an unattended cron job needs a deploy key or scoped token on the
  machine that runs it, scoped to this repo only.
- Pages requires a **public** repo on free accounts. That suits this project,
  whose evidence is meant to be public anyway, but it means the raw evidence and
  print ledger are published by construction rather than by choice.
- Collection must run from a machine with a stable, reputable IP and honest
  identification, so it stays on a machine you control rather than in CI.
  `derive` and `generate`, being pure functions of committed data, could
  optionally also run in GitHub Actions — which would continuously prove the
  "clone and re-derive" claim rather than merely asserting it.

## 6. The Agent Accessibility Index

### 6.1 Cadence and period identifiers

The index prints **weekly**. AI-crawler blocking moves fast enough that monthly
sampling would miss the response to events — a new crawler launching, a large
publisher changing policy — which is where most of the interest lies. A weekly
series can also be aggregated up to a monthly one at any time; the reverse is
impossible, so weekly is the conservative choice.

A `period` is the **ISO date of the Monday on which collection began**, written
`YYYY-MM-DD`. Deliberately not ISO week notation (`2026-W38`): the ISO week-year
diverges from the calendar year at year boundaries and some years have 53 weeks,
which is a reliable source of off-by-one bugs. A Monday date sorts correctly,
never ambiguates, and can be *displayed* as a week number wherever that reads
better.

Collection opens Monday 00:00 UTC. The window — including all retries — closes at
72 hours, well clear of the next period, so runs can never overlap.

**The window is enforced.** `collect` refuses to run outside it, in either
direction: you cannot observe a week that has not begun, and collecting after it
closes labels observations with a week they were not gathered in. That failure is
quiet rather than loud — the data looks fine, it is merely mis-dated — which is
why it is a guard rather than a convention. `--ignore-window` overrides it
deliberately.

An override cannot hide, because `fetched_at` already records when each
observation was gathered: `print` compares those timestamps against the window
and warns when any fall outside it, so a forced late collection cannot produce a
clean-looking print. No extra field is needed; the evidence already says.

### 6.2 Panel

Tranco top 1000, **qualified at construction and frozen annually**.
`data/panel/<year>.json` pins the Tranco list ID and capture date, so the panel
is falsifiable rather than asserted. The basket is fixed for the year, so the
index measures behaviour change rather than composition change. Rebasing happens
each January, with both panels published across the overlap period so the chain
is visible.

**Qualification.** Tranco ranks domains by DNS traffic, not by whether they are
websites: its top ranks include CDN endpoints and name servers — `akamai.net`,
`domaincontrol.com` — that never serve a `robots.txt` at all. A sweep of the real
top 20 found two such domains, capping coverage at 90%.

Admitting them would put a *permanent floor* under coverage, and a floor makes
the provisional rule in §6.5 meaningless: set the threshold above the floor and
every print is provisional forever, set it below and it can no longer detect a
genuine outage. So the panel is the first 1000 domains of the named Tranco list
that returned a **conclusive** observation during a one-off qualification sweep.
A 404 qualifies — that is a site which exists and permits everything, not a site
that is missing.

Structural non-responders therefore never enter the panel, and coverage loss
during a later collection is transient by construction, which is exactly what the
provisional threshold exists to detect. `tallyhouse qualify` performs the sweep
and records the list ID, the sweep date, the number of candidates examined and
each domain's Tranco rank, so a stranger can rebuild the same panel. A sweep that
cannot fill the panel fails rather than publishing a smaller denominator.

**The unreadable web.** A measured ~12% of the top 1000 sit behind
anti-automation protection that returns HTTP 403 to any client that cannot
execute JavaScript. Cloudflare labels these itself with `cf-mitigated:
challenge`, which the collector reads to record `Challenged`; other providers
(Akamai, Varnish, CloudFront) return an unlabelled 403 recorded as
`ServerError`. Both are inconclusive.

RFC 9309 §2.3.1.3 permits a crawler to treat an unavailable `robots.txt` as
licence to crawl. That rule governs **crawler behaviour**; it does not state what
a site's policy *is*, and this index reports policy. The distinction is not
academic: behind these responses `ietf.org` is permissive while `yelp.com` names
seven AI crawlers and disallows them all. Inferring "no restrictions" would
publish a falsehood about Yelp, so an unreadable response is recorded as
evidence of nothing.

**The collector never solves a challenge.** A challenge is a site expressing a
preference against automated access, and an index about crawler etiquette cannot
be the thing that routes around it. A headless browser would pass these
legitimately and raise coverage substantially; it is declined deliberately.

**Known limitation — panel bias.** Unreadable sites are excluded at
qualification, which keeps coverage loss transient and preserves the meaning of
the provisional threshold (§6.5). The exclusion is not neutral: sites deploying
aggressive bot protection are plausibly more hostile to AI crawlers than average,
and Yelp is a concrete example of an AI-hostile site excluded on these grounds.
**The panel therefore probably under-represents AI-hostile sites, and the
headline is likely an underestimate.** The panel file records every excluded
domain with the outcome that excluded it, and the `unreadable` series publishes
the size of the blind spot each period, so a reader can size the effect rather
than take the claim on trust.

**Known limitation — corporate grouping.** Qualification does not collapse
domains owned by one operator: `facebook.com`, `instagram.com` and `fbcdn.net` are three panel members
and one editorial policy, so large groups carry proportionate extra weight.
Grouping is an editorial judgement that cannot be derived reproducibly from
public data, so it is documented rather than applied.

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
coverage; and `unreadable` — the share of the panel whose server answered but
withheld its policy. `unreadable` is distinct from coverage loss: a timeout is an
absence, whereas a challenge or refusal is a site that exists, has a policy, and
would not show it. Publishing it makes the index's blind spot a number on the
chart rather than a footnote, and makes its growth measurable as bot protection
spreads.

**Week-on-week change is published like-for-like**, computed only over domains
conclusively observed in *both* the current and preceding period. At weekly
frequency the true changes are small, so a wobbling denominator could otherwise
manufacture movement that never happened — the headline level and the change
figure would disagree, and the change is what gets quoted. The headline *level*
remains computed over all conclusive observations in the period.

### 6.5 Integrity rules

Fixed in advance and published, because deciding them after seeing a bad week is
how indices lose credibility.

- **Denominator** is conclusive observations only. `NoRobotsTxt` is conclusive —
  no `robots.txt` means not blocking. `Timeout`, `DnsFailure` and `ServerError`
  are not, and are excluded from both numerator and denominator.
- **Coverage** — conclusive observations as a share of the panel — is published
  alongside every print.
- A print with coverage below **97%** is marked **provisional** and the site
  labels it as such. This figure is a placeholder to be calibrated from the first
  real collection run before anything is published — the 72-hour weekly window
  allows less retry time than a monthly one would, so achievable coverage may
  legitimately be lower.

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

Two scheduled jobs rather than one, because collection and publication want
different schedules. `weekly.sh collect` runs several times across the 72-hour
window: it merges into the period's existing manifest, keeping every conclusive
observation and re-attempting only the domains we learned nothing about, so
repeated runs are how coverage climbs. `weekly.sh publish` runs once after the
window closes — deriving, printing and rendering — because a print freezes a
number, and freezing it while evidence is still arriving would guarantee a
restatement.

Both commit. A print that exists only on one machine's disk is not published,
and the ledger's promise is about what is committed. Neither pushes; that stays
a human decision.

Stages remain separately runnable so a failed `collect` never corrupts
published data, and `derive`/`generate` can be re-run freely at any time.

### 9.1 The gap at 2026-09-21

The series does not run continuously from its first print. `2026-09-14` was
collected by hand while the pipeline was being built; `2026-09-21`'s window
opened and closed with no scheduled job in existence to collect it. That week
is unobservable rather than merely uncollected — `robots.txt` reports only the
present, so there is no archive of what the panel said that Monday that our own
instrument could have read.

It is left as a gap rather than filled. `--ignore-window` would collect it now
and label the observations with a week they were not gathered in, which is the
one thing a dated series must not do. The pipeline already handles the
consequence correctly: `change_wow` is omitted entirely for the first print
after a gap, because a row named for a cadence must not report a fortnight's
movement. The reading itself still publishes; only the change figure is
withheld.

Regular collection begins at `2026-09-28`.

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
