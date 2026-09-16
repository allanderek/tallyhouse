import asyncio

import httpx
import pytest

from tallyhouse.run_collect import collect_panel
from tallyhouse.storage import load_body, read_manifest


def client_returning(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_collect_panel_stores_bodies_and_writes_manifest(tmp_path):
    def handler(request):
        return httpx.Response(200, text=f"# {request.url.host}\nUser-agent: *\nDisallow:\n",
                              headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        records = await collect_panel(tmp_path, "2026-09-14", ["a.com", "b.com"], client=client)

    assert len(records) == 2
    manifest = read_manifest(tmp_path, "2026-09-14")
    assert [r["domain"] for r in manifest] == ["a.com", "b.com"]
    sha = manifest[0]["sha256"]
    assert load_body(tmp_path, sha).startswith(b"# a.com")


async def test_manifest_records_never_contain_raw_bodies(tmp_path):
    def handler(request):
        return httpx.Response(200, text="body", headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        await collect_panel(tmp_path, "2026-09-14", ["a.com"], client=client)

    # Bodies belong in content-addressed storage, never inlined in the manifest.
    assert "body" not in read_manifest(tmp_path, "2026-09-14")[0]


async def test_failed_domains_appear_in_the_manifest_with_no_sha(tmp_path):
    def handler(request):
        raise httpx.ConnectTimeout("down")

    async with client_returning(handler) as client:
        await collect_panel(tmp_path, "2026-09-14", ["down.com"], client=client, attempts=1)

    record = read_manifest(tmp_path, "2026-09-14")[0]
    assert record["outcome"] == "Timeout"
    assert record["sha256"] is None


async def test_identical_bodies_across_domains_share_one_stored_file(tmp_path):
    def handler(request):
        return httpx.Response(200, text="same for everyone",
                              headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        await collect_panel(tmp_path, "2026-09-14", ["a.com", "b.com", "c.com"], client=client)

    assert len(list(tmp_path.rglob("*.txt.gz"))) == 1


async def test_concurrency_is_capped(tmp_path):
    state = {"now": 0, "peak": 0}

    async def handler(request):
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        await asyncio.sleep(0.01)
        state["now"] -= 1
        return httpx.Response(200, text="x", headers={"content-type": "text/plain"})

    domains = [f"d{i}.com" for i in range(20)]
    async with client_returning(handler) as client:
        await collect_panel(tmp_path, "2026-09-14", domains, client=client, concurrency=4)

    assert state["peak"] <= 4
    assert state["peak"] == 4

    # Verify the test is discriminating: a different cap should yield different peak
    state = {"now": 0, "peak": 0}
    async with client_returning(handler) as client:
        await collect_panel(tmp_path, "2026-09-14", domains, client=client, concurrency=8)

    assert state["peak"] <= 8
    assert state["peak"] == 8


async def test_unexpected_exception_becomes_transport_error_outcome(tmp_path):
    """An unexpected exception in fetch_domain should be recorded as TransportError, not abort the run."""
    def handler(request):
        if request.url.host == "bad.com":
            raise ValueError("boom")
        return httpx.Response(200, text=f"ok {request.url.host}",
                              headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        records = await collect_panel(tmp_path, "2026-09-14", ["good.com", "bad.com"], client=client)

    # The run should not raise; both domains should be in the manifest.
    assert len(records) == 2
    manifest = read_manifest(tmp_path, "2026-09-14")
    assert [r["domain"] for r in manifest] == ["bad.com", "good.com"]

    # The domain with the unexpected exception should have TransportError outcome.
    bad_record = next(r for r in manifest if r["domain"] == "bad.com")
    assert bad_record["outcome"] == "TransportError"
    assert bad_record["sha256"] is None
    assert "body" not in bad_record

    # The other domain should have succeeded normally.
    good_record = next(r for r in manifest if r["domain"] == "good.com")
    assert good_record["outcome"] == "Fetched"
    assert good_record["sha256"] is not None


async def test_404_body_is_not_stored_as_a_blob(tmp_path):
    def handler(request):
        return httpx.Response(404, text="User-agent: GPTBot\nDisallow: /\n",
                              headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        await collect_panel(tmp_path, "2026-09-14", ["gone.com"], client=client,
                            attempts=1)

    record = read_manifest(tmp_path, "2026-09-14")[0]
    assert record["outcome"] == "NoRobotsTxt"
    assert record["sha256"] is None
    assert list(tmp_path.rglob("*.txt.gz")) == []


async def test_5xx_body_is_not_stored_as_a_blob(tmp_path):
    def handler(request):
        return httpx.Response(500, text="error page id=deadbeef",
                              headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        await collect_panel(tmp_path, "2026-09-14", ["boom.com"], client=client,
                            attempts=1)

    record = read_manifest(tmp_path, "2026-09-14")[0]
    assert record["outcome"] == "ServerError"
    assert record["sha256"] is None
    assert list(tmp_path.rglob("*.txt.gz")) == []
