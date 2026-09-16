"""Orchestrates a collection run across the whole panel.

Concurrency is capped deliberately: the index is about crawler etiquette, so
the crawler that produces it must be beyond reproach. One request per domain
per week is negligible load, but a burst of a thousand simultaneous
connections is not a good look.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import httpx

from tallyhouse.collect import fetch_domain
from tallyhouse.storage import store_body, write_manifest


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def collect_panel(
    root: Path,
    period: str,
    domains: list[str],
    *,
    client: httpx.AsyncClient,
    concurrency: int = 8,
    attempts: int = 3,
) -> list[dict]:
    semaphore = asyncio.Semaphore(concurrency)

    async def one(domain: str) -> dict:
        async with semaphore:
            try:
                return await fetch_domain(client, domain, attempts=attempts)
            except Exception:
                # Catch unexpected exceptions and return a TransportError outcome
                # rather than aborting the entire run. This ensures one bad domain
                # doesn't destroy the whole weekly collection.
                return {
                    "domain": domain,
                    "outcome": "TransportError",
                    "http_status": None,
                    "final_url": None,
                    "content_type": None,
                    "bytes": None,
                    "body": None,
                    "fetched_at": _now(),
                    "attempts": attempts,
                }

    results = await asyncio.gather(*(one(d) for d in domains))

    records = []
    for result in results:
        record = dict(result)
        body = record.pop("body")
        record["sha256"] = store_body(root, body) if body is not None else None
        records.append(record)

    write_manifest(root, period, records)
    return sorted(records, key=lambda r: r["domain"])
