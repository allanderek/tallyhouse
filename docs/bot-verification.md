# Bot verification: what we declare about TallyhouseIndexBot

This records what we tell bot-verification programmes about the crawler, and it
exists because those answers are **commitments**, not paperwork. A declaration
that we collect data but never train on it, and never request anything but
`/robots.txt`, has to stay true as the project changes. Writing it down is what
makes a future change that breaks it visible.

If you change the collector's behaviour, change this file in the same commit,
and re-submit.

## Identity

| | |
|---|---|
| Token | `TallyhouseIndexBot` |
| User-agent | from `src/tallyhouse/constants.py` — the single source of truth |
| Exact user agent | one string only, verified on the wire — httpx appends nothing |
| UA match pattern | `TallyhouseIndexBot*` |
| Egress | `149.102.158.121/32`, published at `/about/crawler/ips.json` |
| Public page | `https://allanderek.github.io/tallyhouse/about/crawler/` |
| Contact | `https://github.com/allanderek/tallyhouse/issues` |
| Source | `https://github.com/allanderek/tallyhouse` |

## Cloudflare BotBase

Dashboard path as of 2026-08-28: **Protect & Connect → Application Security →
BotBase**, or `https://dash.cloudflare.com/?to=/:account/application-security/botbase`.
(An earlier docs page said Manage Account → Configurations → Bot Submission
Form. That path no longer exists; the docs lagged the dashboard.)

**Category:** Data Collection.

Not "Academic Research" — that is a *legacy* value, retained only so existing
WAF rules keep working, and the form no longer offers it. Of the current set
(Search, Agent, Training, Transact, Data Collection, Security Testing, SEO, Ads
Verification, Social / Link Preview, Feed Fetching, Monitoring & Operations),
Data Collection is the right behavioural bucket: we fetch data, index nothing
and train nothing. Its gloss mentions price scraping, which is not us, but no
other value is closer.

**Operator classification:** direct operator. We run the crawler on our own
host; we are not a platform acting for third parties.

**Bot behaviour** — of the options offered, *data collection* only:

| behaviour | us | why |
|---|---|---|
| Search indexing | no | nothing is indexed; we never fetch an indexable page |
| User-behalf actions | no | nothing is fetched in response to a user's request |
| **Data collection** | **yes** | we record each panel domain's `robots.txt` |
| Model training | no | no model is trained on anything collected |
| SEO tool support | no | — |

**Content use:** Full. The form offers Immediate (interacts, saves nothing),
Reference (indexes, excerpts, links back) and Full (summarises, replicates).
There is no "none".

Full is the honest answer even though it sounds like the most aggressive one.
We retain every `robots.txt` we fetch and **republish it verbatim** under
`data/raw/bodies/` — that is replication. Immediate would be false, and
Reference would understate it, since we do not excerpt but reproduce whole
files.

The asymmetry settles it. Cloudflare says a verified bot that reproduces
content in full while declaring less may lose its status, and a reviewer sees
our verbatim copies the moment they open the repository. Under-declaring is the
error that costs us; over-declaring costs little, because we never request page
content at all.

What keeps that from being misleading in the other direction is the scope: the
only file we ever request is `/robots.txt`, a directives file published *in
order to be read by crawlers*, which RFC 9309 §2.3.1 always permits a crawler
to fetch. Content Signals governs a site's content, and a signal file cannot be
its own subject. The submission description should say so plainly, so that
nothing a reviewer finds contradicts the declaration.

**Verification method:** published IP list. Web Bot Auth is stronger and is not
available while the site is on GitHub Pages — see §9.2 of
`docs/superpowers/specs/2026-09-15-tallyhouse-design.md` for why, and what it
would take.

## Conduct we are claiming

Each of these is enforced in code, not merely intended:

- **One file, one request a week.** `PROBE_PATHS` are tested offline against the
  fetched file; they are never requested over the network.
- **Never evades anti-automation.** No browser or TLS impersonation, no
  JavaScript execution, no challenge solving. A challenge is recorded as
  `Challenged` and the domain is excluded from the rate as inconclusive — we
  publish the size of that blind spot as the `unreadable` series rather than
  guessing past it.
- **Concurrency capped** (8) and collection confined to a 72-hour window per
  week, refusing to run outside it.
- **Removable on request.** `data/panel/removals.json` records each removal
  with its reason and the period it takes effect from, `tallyhouse remove`
  writes it and refuses to date one into an already-published period, and from
  that period the domain is not requested at all. The panel file itself is
  never edited, so prints computed against the old membership stay
  re-derivable — a removal changes future weeks without restating past ones.
- **Everything is public**: the code, the method, the ledger, and every
  `robots.txt` body we classified.
