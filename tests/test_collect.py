import socket

import httpx
import pytest

from tallyhouse.collect import classify_response, fetch_domain


def client_returning(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _no_op_sleep(delay):
    """No-op sleep for testing retries without real delays."""
    pass


def test_200_plain_text_is_fetched():
    assert classify_response(200, "text/plain", 100) == "Fetched"


def test_404_is_no_robots_txt():
    assert classify_response(404, "text/html", 0) == "NoRobotsTxt"


def test_5xx_is_server_error():
    assert classify_response(503, "text/html", 0) == "ServerError"


def test_html_served_at_robots_txt_is_not_plain_text():
    # Many sites return a styled 404 page with a 200 status.
    assert classify_response(200, "text/html", 100) == "NotPlainText"


def test_oversized_body_is_too_large():
    assert classify_response(200, "text/plain", 10 * 1024 * 1024) == "TooLarge"


@pytest.mark.asyncio
async def test_successful_fetch_records_body_and_metadata():
    def handler(request):
        return httpx.Response(200, text="User-agent: *\nDisallow:\n",
                              headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "example.com")

    assert record["domain"] == "example.com"
    assert record["outcome"] == "Fetched"
    assert record["http_status"] == 200
    assert record["body"] == b"User-agent: *\nDisallow:\n"
    assert record["fetched_at"].endswith("Z")


@pytest.mark.asyncio
async def test_sends_the_identifying_user_agent():
    seen = {}

    def handler(request):
        seen["ua"] = request.headers["user-agent"]
        return httpx.Response(200, text="", headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        await fetch_domain(client, "example.com")

    assert seen["ua"].startswith("TallyhouseIndexBot/1.0")


@pytest.mark.asyncio
async def test_timeout_is_retried_then_recorded_as_timeout():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        raise httpx.ConnectTimeout("too slow")

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "slow.example", attempts=3, sleep=_no_op_sleep)

    assert record["outcome"] == "Timeout"
    assert record["attempts"] == 3
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_transient_failure_then_success_is_recorded_as_fetched():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectTimeout("first attempt fails")
        return httpx.Response(200, text="ok", headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "flaky.example", attempts=3, sleep=_no_op_sleep)

    assert record["outcome"] == "Fetched"
    assert record["attempts"] == 2


@pytest.mark.asyncio
async def test_dns_failure_is_recorded_as_dns_failure():
    def handler(request):
        exc = httpx.ConnectError("Name or service not known")
        exc.__cause__ = socket.gaierror("Name or service not known")
        raise exc

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "nope.invalid", attempts=1)

    assert record["outcome"] == "DnsFailure"


@pytest.mark.asyncio
async def test_too_many_redirects_is_recorded_as_transport_error():
    def handler(request):
        raise httpx.TooManyRedirects("Too many redirects", request=request)

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "redirect-loop.example", attempts=1)

    assert record["outcome"] == "TransportError"
    assert record["attempts"] == 1


@pytest.mark.asyncio
async def test_remote_protocol_error_is_recorded_as_transport_error():
    def handler(request):
        raise httpx.RemoteProtocolError("Bad response")

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "bad-proto.example", attempts=1)

    assert record["outcome"] == "TransportError"


@pytest.mark.asyncio
async def test_connect_error_with_gaierror_cause_is_dns_failure():
    def handler(request):
        exc = httpx.ConnectError("Connection failed")
        exc.__cause__ = socket.gaierror("Name or service not known")
        raise exc

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "dns.example", attempts=1)

    assert record["outcome"] == "DnsFailure"


@pytest.mark.asyncio
async def test_connect_error_without_gaierror_cause_is_connect_failure():
    def handler(request):
        exc = httpx.ConnectError("Connection refused")
        exc.__cause__ = OSError("Connection refused")
        raise exc

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "refused.example", attempts=1)

    assert record["outcome"] == "ConnectFailure"


@pytest.mark.asyncio
async def test_read_error_is_connect_failure_not_timeout():
    def handler(request):
        raise httpx.ReadError("Connection reset by peer")

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "reset.example", attempts=1)

    assert record["outcome"] == "ConnectFailure"
