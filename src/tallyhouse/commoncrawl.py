"""Common Crawl collector for the historical index.

Reads robots.txt as Common Crawl saw it, rather than as we can see it now.

Access is via the **columnar index**: per-crawl Parquet describing every capture,
including the `robotstxt` subset, queryable with predicate pushdown over HTTP
range requests. The obvious alternative, the CDX HTTP API, is not usable here —
it is rate limited, and a few hundred queries were enough to have us cut off
entirely. A backfill needs ~36,000 lookups, so the API was never an option.

The Parquet query also lets the best capture per domain be chosen in SQL, which
collapses ~1.3M candidate rows per crawl to one row per panel domain. Only then
is a WARC body range-fetched, one per domain. Bulk data fetches from
data.commoncrawl.org are not rate limited; only the index API is.

This module fetches and extracts. Classification is the existing parse.py,
unchanged, so the two indices differ in how evidence is gathered and not at all
in how it is read.
"""

import gzip
import io
import urllib.request
from pathlib import Path

DATA = "https://data.commoncrawl.org/"
PATHS = DATA + "crawl-data/{crawl}/cc-index-table.paths.gz"

# Captures whose host is the apex or the www. variant — the same two hosts the
# live collector tries. Deliberately NOT every subdomain sharing a registered
# domain: en.wikipedia.org's robots.txt is a different site's policy, and the
# two indices must agree on what "a domain's robots.txt" means.
_HOSTS = "url_host_name IN ('{domain}', 'www.{domain}')"

# Prefer a readable file, then a conclusive absence, then whatever was seen;
# newest within each class, so a site that changed mid-crawl is reported as it
# ended up.
_SELECT = """
SELECT url_host_registered_domain AS domain, url, fetch_status,
       warc_filename, warc_record_offset, warc_record_length, fetch_time
FROM read_parquet({parts})
WHERE url_path = '/robots.txt' AND ({hosts})
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY {group}
    ORDER BY CASE WHEN CAST(fetch_status AS INTEGER) = 200 THEN 0
                  WHEN CAST(fetch_status AS INTEGER) IN (404, 410) THEN 1
                  ELSE 2 END,
             fetch_time DESC
) = 1
"""


class IndexUnavailable(Exception):
    """The columnar index could not be reached or read."""


def robotstxt_parts(crawl: str, *, cache: Path | None = None,
                    opener=urllib.request.urlopen) -> list[str]:
    """URLs of the Parquet parts describing a crawl's robots.txt captures."""
    raw = None
    marker = cache / f"{crawl}.paths.gz" if cache else None
    if marker and marker.exists():
        raw = marker.read_bytes()
    if raw is None:
        try:
            with opener(PATHS.format(crawl=crawl), timeout=120) as response:
                raw = response.read()
        except Exception as exc:
            raise IndexUnavailable(f"could not read index paths for {crawl}") from exc
        if marker:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_bytes(raw)
    lines = gzip.decompress(raw).decode().splitlines()
    return [DATA + line for line in lines if "subset=robotstxt" in line]


def locate(connection, parts: list[str], domains: list[str]) -> dict[str, dict]:
    """One best capture per domain, chosen in SQL. Domains absent are omitted."""
    if not domains or not parts:
        return {}
    hosts = " OR ".join(_HOSTS.format(domain=d.replace("'", "")) for d in domains)
    query = _SELECT.format(
        parts="[" + ",".join(f"'{p}'" for p in parts) + "]",
        hosts=hosts,
        group="url_host_registered_domain",
    )
    rows = connection.execute(query).fetchall()
    located = {}
    for domain, url, status, filename, offset, length, fetch_time in rows:
        located[domain] = {
            "url": url, "status": str(status), "filename": filename,
            "offset": offset, "length": length,
            "fetch_time": fetch_time.strftime("%Y-%m-%dT%H:%M:%SZ") if fetch_time else None,
        }
    return located


def fetch_body(record: dict, *, opener=urllib.request.urlopen) -> bytes:
    """Range-fetch one WARC record and return the HTTP response body."""
    start = int(record["offset"])
    end = start + int(record["length"]) - 1
    request = urllib.request.Request(
        DATA + record["filename"], headers={"Range": f"bytes={start}-{end}"}
    )
    with opener(request, timeout=120) as response:
        raw = gzip.decompress(response.read())
    parts = raw.split(b"\r\n\r\n", 2)
    return parts[2] if len(parts) > 2 else b""


def to_observation(domain: str, crawl: str, record: dict | None, body: bytes | None) -> dict:
    """Shape a capture like a live-collector record, so derive needs no changes."""
    if record is None:
        outcome, status = "NotInCrawl", None
    else:
        status = record["status"]
        if status == "200":
            outcome = "Fetched"
        elif status in {"404", "410"}:
            outcome = "NoRobotsTxt"
        elif status in {"301", "302", "303", "307", "308"}:
            # Captured only as a redirect: no readable policy in this crawl.
            outcome = "TransportError"
        else:
            outcome = "ServerError"
    return {
        "domain": domain,
        "outcome": outcome,
        "http_status": int(status) if status and status.isdigit() else None,
        "final_url": record["url"] if record else None,
        "content_type": None,
        "bytes": len(body) if body is not None else None,
        "body": body,
        # When Common Crawl saw it — the only honest timestamp for evidence we
        # did not gather ourselves.
        "fetched_at": record["fetch_time"] if record else None,
        "attempts": 1,
        "crawl": crawl,
    }
