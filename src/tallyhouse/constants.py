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

# Outcome types. Conclusive outcomes (below) tell us what the site's policy is;
# all others mean "we learned nothing this week" and are excluded from index.
# - Fetched: successfully retrieved and parsed robots.txt
# - NoRobotsTxt: 404/410 (conclusive absence; site blocks no one)
# - DnsFailure: domain name did not resolve
# - ConnectFailure: connection failed (refused, TLS error, host unreachable, etc.)
# - Timeout: request exceeded time limit
# - TransportError: protocol/redirect/proxy errors (bad robots.txt scenario; retry won't help)
# - NotPlainText: 200 but served HTML or other non-plaintext (mangled 404 page)
# - TooLarge: body exceeds MAX_BODY_BYTES
# - ServerError: 5xx, or a 4xx other than 404/410 (we were refused, not answered)
# - Challenged: an anti-automation challenge stood between us and the file
# - Removed: the site asked to be left out, so we did not request it. Not a
#   failure and not a blind spot: deliberately absent evidence. Excluded from
#   the denominator rather than counted as a miss, because we were asked not to
#   look rather than failing to see.
#
# Challenged and ServerError are deliberately NOT conclusive. RFC 9309 2.3.1.3
# lets a crawler treat an unavailable robots.txt as permission to crawl, but
# that governs crawler behaviour, not what the site's policy says — and this
# index reports policy. Measured against the real top 1000, the files behind
# these responses are heterogeneous: ietf.org is permissive, yelp.com names
# seven AI crawlers and disallows them all. Inferring either way would publish
# a falsehood, so we record that we learned nothing.
CONCLUSIVE_OUTCOMES = frozenset({"Fetched", "NoRobotsTxt"})

# Outcomes meaning "the server answered but would not let us read the policy".
# Published as the `unreadable` series so the size of this blind spot is a
# number on the chart rather than a footnote, and so its growth is tracked.
UNREADABLE_OUTCOMES = frozenset({"Challenged", "ServerError"})

MAX_BODY_BYTES = 512 * 1024
