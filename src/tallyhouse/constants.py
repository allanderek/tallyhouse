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
CONCLUSIVE_OUTCOMES = frozenset({"Fetched", "NoRobotsTxt"})

MAX_BODY_BYTES = 512 * 1024
