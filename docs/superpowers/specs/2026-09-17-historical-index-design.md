# Historical AI-Blocking Index — Design

**Date:** 2026-09-17
**Status:** Implemented and published 2026-09-23. Section 5.1 records where
implementation departed from this design, and why.
**Relationship to the live index:** a separate index on the same spine, not backfill.

---

## 1. Why a second index rather than backfill

The live Agent Accessibility Index has one print. A series with no history is a
number, not an index, and nobody cites it. Common Crawl publishes a `robots.txt`
subset per monthly crawl going back to 2008, so a historical reconstruction can
start the story where it actually starts — before GPTBot existed.

It is a **separate index** because it is a different instrument. Common Crawl
fetches with its own user-agent, its own IP ranges and its own scheduling; it
reaches a host whenever its frontier does, not at a fixed weekly instant. Its
population comes from CC's seed selection, not Tranco rank. Splicing the two
series would manufacture a discontinuity at the join that looks like a real
change and is not — the same confound the live index's like-for-like change
series exists to prevent. Backfilled rows would also be vintage-1 prints with a
`computed_at` three years after their `period`, which would hollow out what
"published and frozen" means in the ledger.

The two indices' **shapes** are comparable. Their **levels** are not, because
they measure different populations. This must be stated wherever both appear.

## 2. What Common Crawl gives us

Verified during a feasibility spike on 2026-09-17:

- A `robotstxt` subset exists per crawl, back to at least 2023 (127 crawls exist
  in total, to 2008).
- Those records **are** in the CDX index — confirmed for 2023, 2024, 2025 and
  2026 crawls — and the index entry points into the `/robotstxt/` WARC.
- A single record is retrievable by HTTP range request: ~1KB, rather than
  scanning the ~150GB (100,000 × 1.5MB WARCs) that one crawl's subset occupies.
  Across 3 years that is ~36MB of fetches instead of ~5TB of scanning.
- The existing `parse.py` classifies the extracted bodies **unchanged**: January
  2023 Reddit and GitHub were pulled and classified during the spike.

CC also reaches sites the live collector cannot. It is a verified crawler, so it
obtains `robots.txt` from the bot-protected hosts (Yelp, nih.gov, ScienceDirect)
that the live panel excludes at qualification. The historical index therefore has
**better** coverage of the AI-hostile population, and offers an independent
estimate of the live index's documented exclusion bias.

## 3. Panel: balanced

The panel is the **intersection of the Tranco top 1000 on 2023-02-01 (list
K2K4W) and on 2026-09-16 (list N2P2W)** — 611 domains.

Measured churn made this necessary: only 611 of the 2023 top-1000 remain in the
2026 top-1000, so **39% of constituents turned over in three years**. With
contemporaneous panels a move in the headline could be composition rather than
behaviour, and the two would be inseparable. Tranco's own method also changed
underneath (4 providers in 2023, 5 from 2024), so even a contemporaneous panel is
not a stable instrument across the span.

A balanced panel holds membership fixed, so **a change in the number can only
mean a change in behaviour** — which is the only thing this index is for.

Two consequences, both stated rather than hidden:

- **Survivorship.** Members were prominent at both endpoints, so the panel is
  biased toward durably significant sites. Sites that rose or fell within the
  span are absent.
- **Different population.** ~611 domains, against the live index's 1000, and
  selected differently. Levels are not comparable between the two indices.

The panel is **not** filtered by the live index's qualification sweep. That sweep
excludes hosts our collector cannot read; Common Crawl can read them, so
importing that exclusion would inherit a bias this index does not suffer.

## 4. Period and cadence

A period is the **crawl's nominal month, `YYYY-MM`** — not the Monday-date
convention of the live index, which exists to bound a 72-hour collection window
that has no analogue here. The crawl id (e.g. `CC-MAIN-2023-06`) is recorded
alongside each print as provenance, so a reader can retrieve the exact source.

Crawls are roughly monthly but irregular, and a crawl fetches a given host
whenever its frontier reaches it during the crawl window. A period is therefore
"the state of the panel as Common Crawl observed it during that crawl", which is
weaker than the live index's bounded window and must be described as such.

## 5. Method

For each crawl and each panel domain:

1. Read the crawl's columnar index and select the **best capture per domain in
   SQL** — a readable file first, then a conclusive absence, then whatever was
   seen; newest within each class, so a site that changed mid-crawl is reported
   as it ended up. One query per crawl, not one per domain.
2. Range-fetch that record and extract the body from the WARC.
3. Classify with the existing `parse.py` and the same versioned agent set, so
   the two indices' classification is identical even though their collection is
   not.

Outcomes reuse the live vocabulary. `NoRobotsTxt` for a 404/410 record, `Fetched`
for a 200 **whose body we actually hold**, `TransportError` for a capture that is
only a redirect, `BodyUnavailable` for a capture the WARC would not give us, and a
distinct `NotInCrawl` for a domain with no record in that crawl — which is an
absence of evidence about the *crawl*, not about the site. Of these only
`Fetched` and `NoRobotsTxt` are conclusive.

Raw evidence is retained exactly as the live index retains it: bodies
content-addressed by sha256, a manifest per period. Each observation also
records the WARC filename, offset and length it came from, so a single body can
be re-fetched — or verified by a stranger — without re-running the query that
located it. The index is re-derivable from committed evidence without
re-querying Common Crawl.

## 5a. Coverage, and a second balancing problem

Measured on CC-MAIN-2026-30 over the 611-domain balanced panel:

| outcome | count |
|---|---|
| Fetched | 355 |
| NoRobotsTxt | 22 |
| TransportError (captured only as a redirect) | 53 |
| ServerError | 29 |
| **NotInCrawl** | **152** |

Coverage is **61.7%**, against the live index's 99.7%. Common Crawl does not
fetch every host's robots.txt in every crawl, and which hosts it reaches varies
between crawls. That is not transient loss of the kind the provisional threshold
is designed for — it means **the observable set changes between periods**, so a
move in the series could be composition rather than behaviour.

That is the same confound the balanced panel was chosen to remove, reappearing
one level down. The intended remedy is the same idea applied again: a **doubly
balanced panel**, restricted to domains conclusively observed in *every* crawl in
the span, so each period compares a genuinely fixed set. The cost is a smaller
panel, and the size is an empirical question settled by probing several crawls
before committing to a full backfill.

The first measured value, from the feasibility spike and superseded by the
published series in §6.1:

    CC-MAIN-2026-30, 611-domain balanced panel, 377 conclusive
    targeted 27.59%  effective 29.44%  blanket 5.84%

Against the live index's 23.47% for September 2026 — that index's vintage 1, as
it stood on the date of this spike; it was later restated to 23.97% under the
45-token agent set. The levels are not
comparable — different panels, different populations — but the direction is
consistent with the live index's documented exclusion bias: this panel *includes*
the bot-protected sites the live panel must drop, and it reads higher. That is
independent evidence for a claim that was previously only an argument.

## 5.1 Where implementation departed from this design

**Redirect chasing was abandoned.** Step 2 as designed does not work: the index
keys captures by a scheme-insensitive urlkey, so following a 301 from
`http://x/robots.txt` lands on the same urlkey as the record you started from
and looks like a redirect loop. Selecting the best capture in SQL answers the
same question in one query and cannot loop.

**The doubly balanced panel (§5a) was not built.** Restricting the panel to
domains conclusively observed in *every* crawl would have removed the
changing-observable-set confound, but at a cost the spike numbers made
unattractive: conclusive counts per crawl run 377-421 out of 611, and the
intersection across all sixteen would have been far smaller than any of them.

The confound is instead handled where it actually bites, in the change figure.
`change_since_previous` is computed like-for-like over the domains that two
**adjacent** readings share, so a move in it cannot be composition even though
the levels' denominators differ between periods. Coverage is published per
period so a reader can see the denominator move.

This turned out to be more than a modelling nicety. The first published run
showed a −6.3 point fall at 2024-05 followed by a +10.0 point rise, which looks
like real volatility in the levels. The like-for-like change said −6.91 points
across 405 *shared* domains, which composition cannot explain — so the data had
to be wrong, and it was: 124 of that crawl's captures had lost their body to a
transient range-request failure, been recorded as `Fetched` anyway because the
archive's status was 200, and then been read by `derive` as an *empty*
robots.txt blocking nobody. The `BodyUnavailable` outcome and retried range
requests exist because of this. A levels-only series would have shipped.

**Historical prints are never provisional**, contradicting §6's plan to
calibrate a separate threshold. The flag means "more evidence may arrive inside
the collection window"; Common Crawl's archive is closed, so a historical
reading can never be restated on coverage grounds and is final the moment it is
computed, at whatever coverage it achieved. Coverage is published as its own
series instead, which is the honest place for it.

**The change series is `change_since_previous`, not a cadence-named row.** The
published series is roughly quarterly but unevenly spaced — the gaps run two to
four months — so a field named for a cadence would be stating something false. A
gap in the series breaks the chain rather than spanning it: a missing crawl
yields no change row, rather than a two-step move in a field claiming one step.

## 6. Operational notes

- **The CDX HTTP API is unusable for a backfill.** It is rate limited; a few
  hundred queries during development were enough to be cut off entirely, after
  which even sequential requests failed. Access is via the columnar Parquet index
  instead, which has no such gate.
- Measured cost per crawl was **248s** to locate all 611 panel domains across
  the 300 Parquet parts, plus **17s** to range-fetch the bodies. The locate
  query was filtering ~97M index rows with 611 OR'd two-element `IN`
  expressions, up to 1222 string comparisons per row; one flat `IN` list is the
  same predicate but hashable, and cut it roughly threefold.
- **The archive refuses us in bursts, and a burst can cost a whole crawl.** Both
  the index reads and the range requests need patience: DuckDB's httpfs defaults
  give up after 0.1s, 0.4s and 1.6s, which treats a busy archive as a broken
  one. One 503 four minutes into a query cost a whole crawl on the first run,
  and later a burst cost 2023-03 237 of its 367 bodies while every other crawl
  was clean.
- The collector is therefore **serialised, delayed between crawls, and
  resumable**: a crawl's manifest is written only on completion, and a crawl
  whose manifest exists is skipped, so being refused costs one crawl rather than
  the run. `tallyhouse repair` re-fetches unread bodies from the coordinates on
  record, without re-running the index query. It touches only failed captures,
  so a repair cannot change a number that was already right.
- Per-crawl coverage varies and is lower than the live index's 99.7%. See §5.1:
  it is published per period rather than managed with a threshold.

## 6.1 Published result

Sixteen roughly quarterly crawls, 2023-01 to 2026-08, published 2026-09-23.
Which crawls constitute the series is `data/crawls/historical.json`, because
adding or removing one changes the published series.

The rise in AI-crawler blocking is a **step, not a climb**. Through the first
half of 2023 the figure sits between 1.28% and 2.26% — and what there is is
CCBot, since most tracked crawlers did not yet exist. GPTBot launched in August
2023, and the very next crawl reads 15.93%, a like-for-like jump of **13.65
points** over the 381 domains shared with the reading before. From there it
climbs about two points a quarter to the mid-twenties, plateaus through 2025
(three consecutive negative changes), and reaches **27.85%** at 2026-08.

Coverage runs 61.7%-68.9% across the series. The live index read 23.97% for
September 2026 on its own panel (vintage 2; vintage 1's 23.47% predates the
agent-set expansion to 45 tokens); the levels are not comparable, but the
historical panel *includes* the bot-protected sites the live panel must exclude
at qualification and reads higher, which is independent evidence for the live
index's documented exclusion bias.

## 7. Out of scope

Splicing with the live index; a live CC-tracking series (CC lags 4-6 weeks, and
the live index already covers the present); any crawl before 2023 in the first
implementation, though the data exists back to 2008 and extending is cheap once
the collector works.
