import json

import pytest

from tallyhouse.render import RenderError, render, render_site

# A stand-in for compiled Elm: same shape the real runtime presents — an Elm
# global whose init returns an object with subscribable ports — so the harness
# is tested without needing the Elm toolchain at test time.
STUB = """
var Elm = { Site: { init: function (config) {
    var subs = [];
    // Defer the send, exactly as Elm's scheduler does, so the test exercises
    // the shim rather than accidentally passing without it.
    setTimeout(function () { subs.forEach(function (f) { f(config.flags.out); }); });
    return { ports: { emit: { subscribe: function (f) { subs.push(f); } } } };
} } };
"""

def stub_pages(pages):
    return {"out": json.dumps(pages)}


def test_output_is_collected_from_the_port():
    got = render(STUB, {"out": "hello"})
    assert got == ["hello"]


def test_a_send_deferred_into_the_shim_still_arrives():
    # Elm defers port sends into setTimeout; without the shim and an explicit
    # drain, the subscriber registered after init would never fire.
    assert render(STUB, {"out": "deferred"}) == ["deferred"]


def test_flags_reach_the_program():
    assert render(STUB, {"out": "x" * 50}) == ["x" * 50]


def test_a_program_that_throws_reports_a_render_error():
    with pytest.raises(RenderError):
        render("throw new Error('boom');", {})


def test_a_missing_module_reports_a_render_error():
    with pytest.raises(RenderError):
        render("var Elm = {};", {}, module="Nope")


def test_site_is_returned_as_path_to_content():
    pages = [{"path": "index.html", "content": "<h1>a</h1>"},
             {"path": "about/index.html", "content": "<h1>b</h1>"}]
    files = render_site(STUB, stub_pages(pages))
    assert files == {"index.html": "<h1>a</h1>", "about/index.html": "<h1>b</h1>"}


def test_a_duplicate_path_is_refused():
    pages = [{"path": "index.html", "content": "a"},
             {"path": "index.html", "content": "b"}]
    # Silently keeping one of them would publish a page nobody intended.
    with pytest.raises(RenderError):
        render_site(STUB, stub_pages(pages))


def test_an_absolute_or_escaping_path_is_refused():
    for bad in ("/etc/passwd", "../outside.html"):
        with pytest.raises(RenderError):
            render_site(STUB, stub_pages([{"path": bad, "content": "x"}]))


def test_emitting_nothing_is_an_error():
    silent = "var Elm = { Site: { init: function () { return { ports: { emit: { subscribe: function () {} } } } }; } };"
    with pytest.raises(RenderError):
        render_site(silent, {})


def test_deep_recursion_does_not_blow_the_stack():
    # QuickJS's default stack overflows on Elm's list recursion at around a
    # thousand elements, which is exactly the panel page. The raised limit is
    # load-bearing, so it is pinned here.
    program = STUB.replace("config.flags.out", "buildDeep(2000)") + """
    function buildDeep(n) { return n === 0 ? "" : "x" + buildDeep(n - 1); }
    """
    assert len(render(program, {})[0]) == 2000


def test_an_unoptimised_build_that_logs_still_runs():
    # `elm make` without --optimize emits calls to console via _Debug_log. The
    # optimised build never does, so testing only the optimised output would
    # hide this — and a development build would fail where production works.
    program = STUB.replace(
        "var Elm =", "console.log('elm debug'); var Elm =")
    assert render(program, {"out": "ok"}) == ["ok"]


def test_a_rejected_decode_stops_the_build_with_its_message():
    # Elm reports a failed flags decode as an object, not an array of pages.
    # Rendering a silently wrong page would be worse than failing.
    program = STUB.replace("config.flags.out", '\'{"error":"Problem with field \\\'period\\\'"}\'')
    with pytest.raises(RenderError) as excinfo:
        render_site(program, {})
    assert "period" in str(excinfo.value)
