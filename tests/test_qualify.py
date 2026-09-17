import json

import httpx
import pytest

from tallyhouse.config import load_panel
from tallyhouse.qualify import qualify, read_tranco, write_panel


def client_returning(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def candidates(n, start=1):
    return [(i, f"d{i}.com") for i in range(start, start + n)]


def test_read_tranco_preserves_rank_order(tmp_path):
    path = tmp_path / "top.csv"
    path.write_text("1,google.com\n2,cloudflare.com\n3,facebook.com\n")
    assert read_tranco(path) == [(1, "google.com"), (2, "cloudflare.com"), (3, "facebook.com")]


async def test_only_conclusive_domains_qualify():
    # Odd-numbered domains are unreachable, as CDN endpoints and name servers
    # are in the real list.
    def handler(request):
        n = int(request.url.host.removeprefix("d").removesuffix(".com"))
        if n % 2:
            raise httpx.ConnectError("not a website")
        return httpx.Response(200, text="User-agent: *\nAllow: /\n",
                              headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        qualified, examined = await qualify(candidates(10), client=client, size=3, attempts=1)

    assert [q["domain"] for q in qualified] == ["d2.com", "d4.com", "d6.com"]
    assert examined == 10


async def test_a_404_qualifies_because_the_site_exists():
    # NoRobotsTxt is a site that permits everything, not a site that is missing.
    def handler(request):
        return httpx.Response(404, text="nope", headers={"content-type": "text/html"})

    async with client_returning(handler) as client:
        qualified, _ = await qualify(candidates(3), client=client, size=3, attempts=1)

    assert len(qualified) == 3


async def test_qualification_preserves_tranco_rank_order():
    def handler(request):
        return httpx.Response(200, text="", headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        qualified, _ = await qualify(candidates(5), client=client, size=5, attempts=1)

    assert [q["rank"] for q in qualified] == [1, 2, 3, 4, 5]


async def test_sweep_stops_once_the_panel_is_full():
    seen = []

    def handler(request):
        seen.append(request.url.host)
        return httpx.Response(200, text="", headers={"content-type": "text/plain"})

    # 500 candidates, panel of 10: the sweep must not fetch all 500.
    async with client_returning(handler) as client:
        qualified, examined = await qualify(candidates(500), client=client, size=10, attempts=1)

    assert len(qualified) == 10
    assert examined < 500


async def test_running_out_of_candidates_yields_a_short_panel():
    def handler(request):
        raise httpx.ConnectError("nothing answers")

    async with client_returning(handler) as client:
        qualified, examined = await qualify(candidates(5), client=client, size=10, attempts=1)

    # Short rather than silently padded: the caller must notice and widen.
    assert qualified == []
    assert examined == 5


def test_written_panel_loads_and_records_its_provenance(tmp_path):
    qualified = [{"rank": 1, "domain": "a.com"}, {"rank": 4, "domain": "b.com"}]
    write_panel(tmp_path, 2026, tranco_list_id="N2P2W", qualified=qualified, examined=7)

    panel = load_panel(tmp_path, 2026)
    assert panel.tranco_list_id == "N2P2W"
    assert panel.domains == ["a.com", "b.com"]

    document = json.loads((tmp_path / "panel" / "2026.json").read_text())
    assert document["qualification"]["candidates_examined"] == 7
    assert document["qualification"]["qualified"] == 2
    # Ranks are retained so a reader can see which Tranco entries were skipped.
    assert document["ranks"] == {"a.com": 1, "b.com": 4}


def test_written_panel_has_no_duplicate_domains(tmp_path):
    qualified = [{"rank": 1, "domain": "a.com"}, {"rank": 2, "domain": "b.com"}]
    write_panel(tmp_path, 2026, tranco_list_id="N2P2W", qualified=qualified, examined=2)
    # load_panel rejects duplicates; this pins that the writer cannot emit them.
    assert len(load_panel(tmp_path, 2026).domains) == 2
