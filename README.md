# Tallyhouse

Hand-built indices, published from an append-only ledger, where every figure can
be re-derived from committed evidence.

The first index measures how many of the most popular websites tell AI crawlers
to stay out in `robots.txt`.

## The two indices

**Agent Accessibility Index** — weekly. A frozen annual panel of 1,000 domains
drawn from [Tranco](https://tranco-list.eu/), fetched by our own crawler, and
classified against a versioned set of 45 AI-crawler tokens.

**Three-year history** — roughly quarterly, 2023-01 to 2026-08. The same
classification applied to `robots.txt` as [Common
Crawl](https://commoncrawl.org/) captured it at the time, over a balanced panel
of 611 domains present in the Tranco top 1,000 at both ends of the span.

The two measure different populations with different instruments, so **their
levels are not comparable** and the site says so wherever both appear. What the
history shows is the shape: blocking was near zero through the first half of
2023, and the largest single move in the series is the first quarter after
GPTBot launched.

## Why the ledger is append-only

A published number is never edited. If a figure has to change, the new value is
appended as a further vintage alongside a stated reason, and the old row stays
where it was. `data/prints.csv` and `data/series.csv` are the record; the site
reads them back rather than recomputing, so a page cannot disagree with what was
published.

The evidence behind every figure is committed too — every `robots.txt` body we
classified, content-addressed by sha256 under `data/raw/`. Cloning this
repository and re-running `derive` reproduces every published number exactly.
The CI build proves it continuously: it renders the site from a fresh clone, and
the result is byte-identical to what is served.

## Running it

Requires Python 3.10+ and Elm 0.19.1. No Node is needed to build the site — the
generator is Elm compiled to JavaScript and run inside an embedded QuickJS
interpreter. Node is used only to run the Elm test suite.

```sh
pip install -r requirements.txt
./check                       # both test suites: Python pipeline, Elm generator
./debug.sh                    # build and serve on localhost:8080
```

The pipeline stages are separately runnable, so a failed collection can never
corrupt published data:

```sh
export PYTHONPATH=src
python3 -m tallyhouse.cli collect                        # networked
python3 -m tallyhouse.cli derive   --period <YYYY-MM-DD>
python3 -m tallyhouse.cli print    --period <YYYY-MM-DD>
python3 -m tallyhouse.cli generate                       # from committed data
```

`weekly.sh collect` and `weekly.sh publish` are the scheduled entry points and
set `PYTHONPATH` themselves. The `backfill` and `repair` subcommands read the
Common Crawl archive for the historical index; `historical-print` publishes it.

## The crawler

`TallyhouseIndexBot` requests exactly one file from each panel domain,
`/robots.txt`, once a week. It never requests anything else, does not follow
links, does not run JavaScript, and makes no attempt to look like a browser or
to get past an anti-automation challenge. Sites that answer with a challenge are
published as an `unreadable` figure rather than guessed at.

See [`/about/crawler/`](https://allanderek.github.io/tallyhouse/about/crawler/)
for how to be removed from the panel.

## Licence

The code is [MIT](LICENSE). The published index data — the ledgers, panels,
agent sets and observation manifests — is [CC BY
4.0](LICENSE-DATA), so you may reuse the numbers with attribution.

`data/raw/bodies/` is the exception: those are `robots.txt` files as published by
the sites in the panel. They are third-party content, retained verbatim because
an index that cannot be checked against its evidence is an assertion rather than
a measurement. No licence is granted over them here, and none could be.

## Design documents

`docs/superpowers/specs/` holds the design of both indices, including the places
where the implementation departed from the design and why.

## Related work

[The Agentic Web Index](https://knownagents.com/insights) tracks the same
crawlers from the opposite side: not what a site's `robots.txt` says, but what a
crawler actually does when it requests a page — including whether it honours the
rule it was given, which this project has no way to observe.
