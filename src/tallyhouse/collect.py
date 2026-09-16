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

from tallyhouse.constants import MAX_BODY_BYTES, USER_AGENT

_PLAIN_TEXT_PREFIXES = ("text/plain",)


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


async def fetch_domain(
    client: httpx.AsyncClient,
    domain: str,
    *,
    attempts: int = 3,
    sleep=asyncio.sleep,
) -> dict:
    """Fetch one domain's robots.txt, retrying transient failures."""
    last_outcome = "Timeout"
    for attempt in range(1, attempts + 1):
        try:
            response = await client.get(
                f"https://{domain}/robots.txt",
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
            return {
                "domain": domain,
                "outcome": outcome,
                "http_status": response.status_code,
                "final_url": str(response.url),
                "content_type": response.headers.get("content-type"),
                "bytes": len(body),
                "body": body,
                "fetched_at": _now(),
                "attempts": attempt,
            }
        if attempt < attempts:
            await sleep(min(2 ** attempt, 30))

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
