"""The only stage that touches the network.

It appends raw evidence and nothing else: no classification, no index
values. Every outcome the crawler can observe is recorded as data, including
the failures, because the denominator rule depends on telling a conclusive
absence (404) from an inconclusive one (timeout).
"""

import asyncio
import socket
from datetime import datetime, timezone

import httpx

from tallyhouse.constants import CONCLUSIVE_OUTCOMES, MAX_BODY_BYTES, USER_AGENT

_PLAIN_TEXT_PREFIXES = ("text/plain",)

# Outcomes whose payload is genuinely this domain's robots.txt and is therefore
# worth retaining. Everything else -- a 404/410 error page, a 5xx error page, an
# HTML page served at /robots.txt -- is a body ABOUT the absence of a policy,
# not a statement of one. Retaining it would publish a sha256 for a domain that
# has no robots.txt and invite a later stage to parse a stranger's error page as
# crawler policy; CDN error pages also carry per-request ids, so they never
# deduplicate and would accumulate forever as blobs referenced by nothing.
#
# TooLarge is retained because spec 5.1 requires it: the body is kept so that
# the size cap can be revisited later without re-collecting.
_BODY_BEARING_OUTCOMES = frozenset({"Fetched", "TooLarge"})


def classify_response(status: int, content_type: str | None, size: int) -> str:
    if status == 404 or status == 410:
        return "NoRobotsTxt"
    if status >= 500:
        return "ServerError"
    if status != 200:
        # 401/403 and friends: the file exists but we were refused, which is
        # not evidence about crawler policy.
        return "ServerError"
    if size > MAX_BODY_BYTES:
        return "TooLarge"
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype and not ctype.startswith(_PLAIN_TEXT_PREFIXES):
        return "NotPlainText"
    return "Fetched"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def url_variants(domain: str) -> list[str]:
    """The robots.txt URLs to try for a domain, in order.

    Spec 5.1: the canonical request is https://<domain>/robots.txt, falling back
    to http:// and to the www. host. Without the fallbacks, coverage is
    suppressed for every panel domain that serves robots.txt only on www. or
    only over http — and coverage is what decides whether a print is
    provisional.

    A domain already spelled with a www. prefix yields no www. variant, so
    nobody is asked for www.www.example.com.
    """
    hosts = [domain]
    if not domain.startswith("www."):
        hosts.append(f"www.{domain}")
    return [
        f"{scheme}://{host}/robots.txt"
        for scheme in ("https", "http")
        for host in hosts
    ]


# A 5xx or a 429 is a transient server condition, not a statement about crawler
# policy, so it is retried exactly like a transport failure. Without this a
# single 503 recorded a non-conclusive ServerError having made one request.
def _is_transient_status(status: int) -> bool:
    return status >= 500 or status == 429


async def _fetch_url(
    client: httpx.AsyncClient,
    domain: str,
    url: str,
    *,
    attempts: int,
    sleep,
) -> dict:
    """Fetch one URL, retrying transient failures."""
    last_outcome = "Timeout"
    last_record: dict | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = await client.get(
                url,
                headers={"user-agent": USER_AGENT},
                follow_redirects=True,
            )
        except httpx.TimeoutException:
            last_outcome = "Timeout"
        except httpx.ConnectError as exc:
            # Distinguish DNS failures from other connection errors.
            if isinstance(exc.__cause__, socket.gaierror):
                last_outcome = "DnsFailure"
            else:
                last_outcome = "ConnectFailure"
        except httpx.NetworkError:
            # ReadError, WriteError, CloseError are terminal network problems.
            last_outcome = "ConnectFailure"
        except httpx.RequestError:
            # TooManyRedirects, ProtocolError, ProxyError, UnsupportedProtocol
            # are terminal: retrying won't help.
            last_outcome = "TransportError"
        else:
            body = response.content
            outcome = classify_response(
                response.status_code,
                response.headers.get("content-type"),
                len(body),
            )
            record = {
                "domain": domain,
                "outcome": outcome,
                "http_status": response.status_code,
                "final_url": str(response.url),
                "content_type": response.headers.get("content-type"),
                "bytes": len(body),
                "body": body if outcome in _BODY_BEARING_OUTCOMES else None,
                "fetched_at": _now(),
                "attempts": attempt,
            }
            if not _is_transient_status(response.status_code):
                return record
            last_record = record
            last_outcome = outcome
        if attempt < attempts:
            # The backoff is deliberately short. The 72-hour collection window of
            # spec 5.1/6.1 is spanned by cron re-running `collect`, which merges
            # into the period's existing manifest and re-attempts only the
            # domains still inconclusive — not by one process sleeping for three
            # days holding a thousand sockets open.
            await sleep(min(2 ** attempt, 30))

    if last_record is not None:
        last_record["attempts"] = attempts
        return last_record

    return {
        "domain": domain,
        "outcome": last_outcome,
        "http_status": None,
        "final_url": None,
        "content_type": None,
        "bytes": None,
        "body": None,
        "fetched_at": _now(),
        "attempts": attempts,
    }


async def fetch_domain(
    client: httpx.AsyncClient,
    domain: str,
    *,
    attempts: int = 3,
    sleep=asyncio.sleep,
) -> dict:
    """Fetch one domain's robots.txt, falling back across URL variants.

    Variants are tried in the order of `url_variants` and the first conclusive
    outcome wins; a 404 on the canonical URL is itself conclusive (spec 6.5:
    no robots.txt means not blocking), so the fallbacks exist for domains that
    do not answer there at all.

    Request ceiling per domain per run: `attempts` for the canonical
    https://<domain> URL plus one for each remaining variant — six requests with
    the default attempts=3, three for a www.-prefixed domain. The fallbacks get a
    single try each rather than the full retry budget, because multiplying the
    budget by the variant count is how a polite crawler stops being one.

    When nothing is conclusive, the canonical URL's outcome is what gets
    recorded: it is the one the index asked about.
    """
    first: dict | None = None
    for index, url in enumerate(url_variants(domain)):
        record = await _fetch_url(
            client, domain, url, attempts=attempts if index == 0 else 1, sleep=sleep
        )
        if record["outcome"] in CONCLUSIVE_OUTCOMES:
            return record
        if first is None:
            first = record
    return first
