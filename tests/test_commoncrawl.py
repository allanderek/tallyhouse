import gzip
import io
import json

import pytest

from tallyhouse.commoncrawl import IndexUnavailable, cdx_lookup, fetch_record, observe


class FakeResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def index_line(**over):
    rec = {"urlkey": "com,example)/robots.txt", "timestamp": "20230126210953",
           "url": "https://example.com/robots.txt", "status": "200",
           "filename": "crawl-data/X/robotstxt/y.warc.gz",
           "offset": "0", "length": "10"}
    rec.update(over)
    return ('{"urlkey": "x", ' + json.dumps(rec)[1:]).encode()


def warc_bytes(body: bytes) -> bytes:
    return gzip.compress(b"WARC/1.0\r\nWARC-Type: response\r\n\r\n"
                         b"HTTP/1.1 200 OK\r\n\r\n" + body)


def opener_for(pages):
    """pages: list of bytes, returned in order; an Exception instance raises."""
    calls = {"n": 0}
    def opener(req, timeout=None):
        item = pages[min(calls["n"], len(pages) - 1)]
        calls["n"] += 1
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)
    opener.calls = calls
    return opener


def test_a_missing_capture_is_not_an_error():
    opener = opener_for([b'{"message": "No Captures found"}'])
    assert cdx_lookup("CC-MAIN-2023-06", "x.com/robots.txt", opener=opener) == []


def test_a_flaky_index_is_retried_then_gives_up_loudly():
    # A transport failure is not the same as "no record": losing records
    # silently across 36,000 queries would corrupt the series invisibly.
    opener = opener_for([OSError("502")])
    with pytest.raises(IndexUnavailable):
        cdx_lookup("CC-MAIN-2023-06", "x.com/robots.txt", opener=opener, sleep=lambda _: None)
    assert opener.calls["n"] == 4


def test_a_transient_failure_then_success_is_recovered():
    opener = opener_for([OSError("504"), index_line()])
    recs = cdx_lookup("CC-MAIN-2023-06", "x.com/robots.txt", opener=opener, sleep=lambda _: None)
    assert recs[0]["status"] == "200"


def test_fetch_record_extracts_the_body_from_the_warc():
    opener = opener_for([warc_bytes(b"User-agent: *\nDisallow: /\n")])
    body = fetch_record({"filename": "f", "offset": "0", "length": "10"}, opener=opener)
    assert body == b"User-agent: *\nDisallow: /\n"


def test_a_captured_robots_txt_is_fetched():
    opener = opener_for([index_line(), warc_bytes(b"User-agent: GPTBot\nDisallow: /\n")])
    rec = observe("CC-MAIN-2023-06", "example.com", opener=opener)
    assert rec["outcome"] == "Fetched"
    assert rec["body"] == b"User-agent: GPTBot\nDisallow: /\n"
    # The honest fetched_at is when Common Crawl saw it, not when we ran.
    assert rec["fetched_at"] == "2023-01-26T21:09:53Z"
    assert rec["crawl"] == "CC-MAIN-2023-06"


def test_a_domain_absent_from_the_crawl_is_not_in_crawl():
    opener = opener_for([b'{"message": "No Captures found"}'])
    rec = observe("CC-MAIN-2023-06", "x.com", opener=opener)
    # Absence of evidence about the CRAWL, not about the site.
    assert rec["outcome"] == "NotInCrawl"
    assert rec["body"] is None


def test_a_404_record_is_conclusive():
    opener = opener_for([index_line(status="404")])
    assert observe("CC-MAIN-2023-06", "x.com", opener=opener)["outcome"] == "NoRobotsTxt"


def test_a_200_is_selected_from_among_redirect_captures():
    # One query returns every capture under the urlkey. Chasing the `redirect`
    # field does not work — CDX urlkeys ignore the scheme, so an http->https
    # redirect points back at the same key — so the 200 is selected instead.
    page = (index_line(status="301", timestamp="20230126210000")
            + b"\n"
            + index_line(status="200", url="https://www.example.com/robots.txt",
                         timestamp="20230126211000"))
    opener = opener_for([page, warc_bytes(b"User-agent: *\nAllow: /\n")])
    rec = observe("CC-MAIN-2023-06", "example.com", opener=opener)
    assert rec["outcome"] == "Fetched"
    assert rec["final_url"] == "https://www.example.com/robots.txt"


def test_a_200_beats_a_404_even_when_the_404_is_newer():
    page = (index_line(status="404", timestamp="20230126990000")
            + b"\n" + index_line(status="200", timestamp="20230126210000"))
    opener = opener_for([page, warc_bytes(b"User-agent: *\nAllow: /\n")])
    assert observe("CC-MAIN-2023-06", "example.com", opener=opener)["outcome"] == "Fetched"


def test_captured_only_as_a_redirect_is_inconclusive():
    opener = opener_for([index_line(status="301")])
    rec = observe("CC-MAIN-2023-06", "a.com", opener=opener)
    assert rec["outcome"] == "TransportError"


def test_the_www_variant_is_tried_when_the_apex_has_no_200():
    # Apex returns only redirects; www. carries the real file.
    apex = index_line(status="301")
    www = index_line(status="200", url="https://www.example.com/robots.txt")
    opener = opener_for([apex, www, warc_bytes(b"User-agent: *\nAllow: /\n")])
    rec = observe("CC-MAIN-2023-06", "example.com", opener=opener)
    assert rec["outcome"] == "Fetched"
