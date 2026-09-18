# Historical AI-Blocking Index — Design

**Date:** 2026-09-17
**Status:** Approved for implementation
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

1. Query the CDX index for `<domain>/robots.txt`.
2. Follow redirect records **within the index** (the index stores the 301, not
   the target's content; `wikipedia.org/robots.txt` is a 301 in every crawl
   checked). Bounded hop limit; exceeding it is an inconclusive outcome.
3. Range-fetch the record and extract the body from the WARC.
4. Classify with the existing `parse.py` and the same versioned agent set, so
   the two indices' classification is identical even though their collection is
   not.

Outcomes reuse the live vocabulary. `NoRobotsTxt` for a 404/410 record, `Fetched`
for a 200, and a distinct `NotInCrawl` for a domain with no record in that crawl
— which is an absence of evidence about the *crawl*, not about the site.

Raw evidence is retained exactly as the live index retains it: bodies
content-addressed by sha256, a manifest per period. The index is re-derivable
from committed evidence without re-querying Common Crawl.

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

The first measured value, for reference and not yet as a published print:

    CC-MAIN-2026-30, 611-domain balanced panel, 377 conclusive
    targeted 27.59%  effective 29.44%  blanket 5.84%

Against the live index's 23.47% for September 2026. The levels are not
comparable — different panels, different populations — but the direction is
consistent with the live index's documented exclusion bias: this panel *includes*
the bot-protected sites the live panel must drop, and it reads higher. That is
independent evidence for a claim that was previously only an argument.

## 6. Operational notes

- **The CDX HTTP API is unusable for a backfill.** It is rate limited; a few
  hundred queries during development were enough to be cut off entirely, after
  which even sequential requests failed. Access is via the columnar Parquet index
  instead, which has no such gate.
- Measured cost per crawl: **248s** to locate all 611 panel domains across the
  300 Parquet parts, plus **17s** to range-fetch the bodies. About 4.5 minutes,
  so a 36-crawl backfill is roughly 2.7 hours — a one-off, after which the index
  is re-derivable from committed evidence without touching Common Crawl again.
- Per-crawl coverage varies and will be lower and noisier than the live index's
  99.7%. The existing coverage and provisional machinery handles this, but the
  threshold must be calibrated separately from the live index's.

## 7. Out of scope

Splicing with the live index; a live CC-tracking series (CC lags 4-6 weeks, and
the live index already covers the present); any crawl before 2023 in the first
implementation, though the data exists back to 2008 and extending is cheap once
the collector works.
