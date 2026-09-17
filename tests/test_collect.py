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
    calls = {"n": 0, "canonical": 0}

    def handler(request):
        calls["n"] += 1
        if str(request.url) == "https://slow.example/robots.txt":
            calls["canonical"] += 1
        raise httpx.ConnectTimeout("too slow")

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "slow.example", attempts=3, sleep=_no_op_sleep)

    assert record["outcome"] == "Timeout"
    assert record["attempts"] == 3
    # The canonical URL gets the full retry budget...
    assert calls["canonical"] == 3
    # ...and each of the three fallback variants gets exactly one try, which is
    # the documented per-domain request ceiling.
    assert calls["n"] == 6


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


@pytest.mark.asyncio
async def test_404_error_page_body_is_not_retained():
    # Some 404 pages contain text that would parse as robots directives. The
    # outcome is a conclusive absence of policy, so the payload is evidence of
    # nothing and must not be carried forward as this domain's robots.txt.
    def handler(request):
        return httpx.Response(
            404,
            text="User-agent: GPTBot\nDisallow: /\n",
            headers={"content-type": "text/plain"},
        )

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "gone.example", attempts=1)

    assert record["outcome"] == "NoRobotsTxt"
    assert record["body"] is None
    # The observed size is still recorded: it is evidence about the response.
    assert record["bytes"] == len(b"User-agent: GPTBot\nDisallow: /\n")


@pytest.mark.asyncio
async def test_5xx_error_page_body_is_not_retained():
    def handler(request):
        return httpx.Response(503, text="<html>maintenance id=abc123</html>",
                              headers={"content-type": "text/html"})

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "down.example", attempts=1, sleep=_no_op_sleep)

    assert record["outcome"] == "ServerError"
    assert record["body"] is None


@pytest.mark.asyncio
async def test_html_served_with_200_has_no_body_retained():
    def handler(request):
        return httpx.Response(200, text="<html>not robots</html>",
                              headers={"content-type": "text/html"})

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "html.example", attempts=1)

    assert record["outcome"] == "NotPlainText"
    assert record["body"] is None


# Spec 5.1 fallbacks: https://<domain>, then https://www.<domain>, then http://
# for each, stopping at the first conclusive outcome.
def test_url_variants_are_tried_in_spec_order():
    from tallyhouse.collect import url_variants

    assert url_variants("example.com") == [
        "https://example.com/robots.txt",
        "https://www.example.com/robots.txt",
        "http://example.com/robots.txt",
        "http://www.example.com/robots.txt",
    ]


def test_a_www_domain_is_not_prefixed_again():
    from tallyhouse.collect import url_variants

    assert url_variants("www.example.com") == [
        "https://www.example.com/robots.txt",
        "http://www.example.com/robots.txt",
    ]


@pytest.mark.asyncio
async def test_robots_txt_served_only_on_www_is_fetched():
    def handler(request):
        if request.url.host == "www.example.com":
            return httpx.Response(200, text="User-agent: *\nDisallow: /x\n",
                                  headers={"content-type": "text/plain"})
        exc = httpx.ConnectError("refused")
        exc.__cause__ = OSError("refused")
        raise exc

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "example.com", attempts=1)

    assert record["outcome"] == "Fetched"
    assert record["final_url"] == "https://www.example.com/robots.txt"
    assert record["body"] == b"User-agent: *\nDisallow: /x\n"


@pytest.mark.asyncio
async def test_robots_txt_served_only_over_http_is_fetched():
    def handler(request):
        if request.url.scheme == "http" and request.url.host == "example.com":
            return httpx.Response(200, text="User-agent: *\nDisallow:\n",
                                  headers={"content-type": "text/plain"})
        exc = httpx.ConnectError("no tls")
        exc.__cause__ = OSError("no tls")
        raise exc

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "example.com", attempts=1)

    assert record["outcome"] == "Fetched"
    assert record["final_url"] == "http://example.com/robots.txt"


@pytest.mark.asyncio
async def test_a_domain_answering_on_the_first_variant_issues_no_further_requests():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, text="", headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "example.com")

    assert record["outcome"] == "Fetched"
    assert seen == ["https://example.com/robots.txt"]


@pytest.mark.asyncio
async def test_a_404_on_the_canonical_url_stops_the_fallbacks():
    # NoRobotsTxt is conclusive (spec 6.5), so there is nothing left to learn.
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(404, text="", headers={"content-type": "text/html"})

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "example.com")

    assert record["outcome"] == "NoRobotsTxt"
    assert seen == ["https://example.com/robots.txt"]


@pytest.mark.asyncio
async def test_a_domain_down_everywhere_records_the_canonical_urls_outcome():
    def handler(request):
        raise httpx.ConnectTimeout("down")

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "example.com", attempts=2, sleep=_no_op_sleep)

    assert record["outcome"] == "Timeout"
    assert record["attempts"] == 2


@pytest.mark.asyncio
async def test_a_transient_503_is_retried_up_to_the_attempt_limit():
    calls = {"canonical": 0}

    def handler(request):
        if str(request.url) == "https://flaky.example/robots.txt":
            calls["canonical"] += 1
        return httpx.Response(503, text="", headers={"content-type": "text/html"})

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "flaky.example", attempts=3, sleep=_no_op_sleep)

    assert record["outcome"] == "ServerError"
    assert calls["canonical"] == 3
    assert record["attempts"] == 3


@pytest.mark.asyncio
async def test_a_503_that_recovers_is_recorded_as_fetched():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="", headers={"content-type": "text/html"})
        return httpx.Response(200, text="User-agent: *\nDisallow:\n",
                              headers={"content-type": "text/plain"})

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "flaky.example", attempts=3, sleep=_no_op_sleep)

    assert record["outcome"] == "Fetched"
    assert record["attempts"] == 3


@pytest.mark.asyncio
async def test_a_429_is_retried_like_a_transient_failure():
    calls = {"canonical": 0}

    def handler(request):
        if str(request.url) == "https://busy.example/robots.txt":
            calls["canonical"] += 1
        return httpx.Response(429, text="", headers={"content-type": "text/html"})

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "busy.example", attempts=3, sleep=_no_op_sleep)

    assert record["outcome"] == "ServerError"
    assert calls["canonical"] == 3


@pytest.mark.asyncio
async def test_a_403_is_not_retried():
    # A refusal is a settled answer, not a transient condition.
    calls = {"canonical": 0}

    def handler(request):
        if str(request.url) == "https://walled.example/robots.txt":
            calls["canonical"] += 1
        return httpx.Response(403, text="", headers={"content-type": "text/html"})

    async with client_returning(handler) as client:
        record = await fetch_domain(client, "walled.example", attempts=3, sleep=_no_op_sleep)

    assert record["outcome"] == "ServerError"
    assert calls["canonical"] == 1


@pytest.mark.asyncio
async def test_retry_backoff_is_bounded():
    delays = []

    async def recording_sleep(delay):
        delays.append(delay)

    def handler(request):
        raise httpx.ConnectTimeout("down")

    async with client_returning(handler) as client:
        await fetch_domain(client, "slow.example", attempts=4, sleep=recording_sleep)

    # Exponential, capped at 30s: the collection window is spanned by cron
    # re-running collect, not by one process sleeping.
    assert delays == [2, 4, 8]
