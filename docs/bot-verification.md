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

**Category:** Academic Research.

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

**Content use:** none. This is worth stating precisely rather than picking the
nearest box. We request exactly one file, `/robots.txt`, which is a directives
file a site publishes *in order to be read by crawlers* — RFC 9309 §2.3.1 means
a crawler is always permitted to fetch it. We request no page content at all, so
we need no search, reference or training permission over any site's content.

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
- **Removable on request** — promised on the crawler page, but **not yet
  mechanised**. The panel file's `excluded` list records domains dropped at
  qualification with a technical outcome (`ConnectFailure` and so on); there is
  no opt-out list and no free-text reason field, so an actual request would
  today be honoured by hand. This is the one claim on this page not enforced in
  code, and it should be closed: a published promise that rests on someone
  remembering is not a control.
- **Everything is public**: the code, the method, the ledger, and every
  `robots.txt` body we classified.
