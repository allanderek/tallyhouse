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
