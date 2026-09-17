"""Common Crawl collector for the historical index.

Reads robots.txt as Common Crawl saw it, rather than as we can see it now. The
CDX index carries robots.txt records and points into each crawl's `/robotstxt/`
WARCs, so a single record costs one range request of roughly a kilobyte. Scanning
instead would mean ~150GB per crawl (100,000 WARCs at ~1.5MB), which is why the
index is load-bearing rather than a convenience.

This module only fetches and extracts. Classification is the existing parse.py,
unchanged, so the two indices differ in how evidence is gathered and not at all
in how it is read.
"""

import gzip
import json
import time
import urllib.error
import urllib.parse
import urllib.request

CDX = "https://index.commoncrawl.org/{crawl}-index"
DATA = "https://data.commoncrawl.org/"

# The index returns 502s and 504s often enough that a backfill without retries
# will lose records silently; observed during the feasibility spike.
RETRIES = 4
BACKOFF = 4.0

# One query returns every capture under a urlkey, 200s and redirects alike, so
# the useful record is selected rather than chased. Chasing the `redirect` field
# does not work: CDX urlkeys ignore the scheme, so an http->https redirect points
# back at the same key and looks like a loop. Selecting also costs one query per
# domain-crawl rather than several, which matters across ~36,000 lookups.
CAPTURES = 20


class IndexUnavailable(Exception):
    """The CDX index could not be reached, as distinct from having no record."""


def cdx_lookup(crawl: str, url: str, *, opener=urllib.request.urlopen,
               sleep=time.sleep) -> list[dict]:
    """Every index record for a URL in a crawl. Empty list if not captured."""
    query = urllib.parse.urlencode(
        {"url": url, "output": "json", "limit": CAPTURES}
    )
    for attempt in range(RETRIES):
        try:
            with opener(f"{CDX.format(crawl=crawl)}?{query}", timeout=60) as response:
                text = response.read().decode("utf-8", "replace")
        except Exception:
            text = ""
        lines = [l for l in text.splitlines() if l.strip()]
        if lines and lines[0].startswith('{"urlkey'):
            return [json.loads(l) for l in lines if l.startswith("{")]
        if lines and lines[0].startswith('{"message"'):
            return []  # genuinely not captured, not a transport failure
        if attempt < RETRIES - 1:
            sleep(BACKOFF * (attempt + 1))
    raise IndexUnavailable(f"CDX index did not answer for {url} in {crawl}")


def best_capture(records: list[dict]) -> dict | None:
    """The most informative capture: a 200 if any, else a conclusive absence.

    Newest first within each class, so a site that fixed its robots.txt during
    the crawl window is reported as it ended up.
    """
    def newest(candidates):
        return max(candidates, key=lambda r: r.get("timestamp", "")) if candidates else None

    return (
        newest([r for r in records if str(r.get("status")) == "200"])
        or newest([r for r in records if str(r.get("status")) in {"404", "410"}])
        or newest(records)
    )


def fetch_record(record: dict, *, opener=urllib.request.urlopen) -> bytes:
    """Range-fetch one WARC record and return the HTTP response body."""
    start = int(record["offset"])
    end = start + int(record["length"]) - 1
    request = urllib.request.Request(
        DATA + record["filename"], headers={"Range": f"bytes={start}-{end}"}
    )
    with opener(request, timeout=90) as response:
        raw = gzip.decompress(response.read())
    # WARC headers, then HTTP headers, then the body.
    parts = raw.split(b"\r\n\r\n", 2)
    return parts[2] if len(parts) > 2 else b""


def observe(crawl: str, domain: str, *, opener=urllib.request.urlopen,
            sleep=time.sleep) -> dict:
    """What Common Crawl recorded for one domain's robots.txt in one crawl.

    Returns the same record shape the live collector produces, so derive and
    compute need no knowledge of where the evidence came from.
    """
    # Apex first, then the www. variant — the same fallback the live collector
    # uses, and for the same reason: plenty of sites serve robots.txt only on
    # one of them. Bounded at two queries; no chasing.
    records: list[dict] = []
    for host in (domain, f"www.{domain}"):
        found = cdx_lookup(crawl, f"{host}/robots.txt", opener=opener, sleep=sleep)
        records.extend(found)
        if any(str(r.get("status")) == "200" for r in found):
            break

    if not records:
        return _record(domain, "NotInCrawl", crawl)

    record = best_capture(records)
    status = str(record.get("status", ""))
    if status in {"301", "302", "303", "307", "308"}:
        # Captured only as a redirect, with no readable target in this crawl.
        return _record(domain, "TransportError", crawl, status=status,
                       url=record.get("url"), timestamp=record.get("timestamp"))
    if status in {"404", "410"}:
        return _record(domain, "NoRobotsTxt", crawl, status=status,
                       url=record.get("url"), timestamp=record.get("timestamp"))
    if status != "200":
        return _record(domain, "ServerError", crawl, status=status,
                       url=record.get("url"), timestamp=record.get("timestamp"))

    body = fetch_record(record, opener=opener)
    return _record(domain, "Fetched", crawl, status=status, url=record.get("url"),
                   timestamp=record.get("timestamp"), body=body)


def _record(domain: str, outcome: str, crawl: str, *, status=None, url=None,
            timestamp=None, body=None) -> dict:
    return {
        "domain": domain,
        "outcome": outcome,
        "http_status": int(status) if status and status.isdigit() else None,
        "final_url": url,
        "content_type": None,
        "bytes": len(body) if body is not None else None,
        "body": body,
        # The crawl's own timestamp for this capture: when CC saw it, which is
        # the only honest "fetched_at" for evidence we did not gather.
        "fetched_at": _iso(timestamp),
        "attempts": 1,
        "crawl": crawl,
    }


def _iso(timestamp: str | None) -> str | None:
    if not timestamp or len(timestamp) < 14:
        return None
    t = timestamp
    return f"{t[0:4]}-{t[4:6]}-{t[6:8]}T{t[8:10]}:{t[10:12]}:{t[12:14]}Z"
