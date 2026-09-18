"""Runs the compiled Elm site generator inside an embedded JavaScript engine.

There is no Node here. The generator is a pure function from committed data to
a set of files, and running it inside QuickJS — a pinned Python dependency —
rather than a system-wide runtime is the safer bet for a project whose central
claim is that a stranger can clone the repo in ten years and reproduce every
published figure.

Two things the embedding needs, both non-obvious and both found by running it:

- **A setTimeout shim.** Elm's scheduler really calls setTimeout during
  Platform.worker startup; a bare context dies with ReferenceError. A minimal
  job queue is enough, and draining it explicitly makes effect ordering
  deterministic. It also explains why subscribing to a port *after* init works:
  the send is deferred into that queue.
- **A raised stack limit.** QuickJS's default overflows on Elm's list recursion
  at around a thousand elements — which is exactly the panel page. This is a
  property of list length, not page size, so it scales with the panel.
- **A console stub.** An `elm make --optimize` build never calls `console`, but
  an unoptimised one does, through `_Debug_log`. Stubbing it costs two lines and
  means a development build runs here exactly as the optimised one does, rather
  than failing in a way that tempts you to only ever test the optimised output.
"""

import json

import quickjs

STACK_BYTES = 64 * 1024 * 1024
MEMORY_BYTES = 512 * 1024 * 1024

# A minimal event loop. Elm needs somewhere to defer effects; it does not need
# real time to pass, and draining explicitly keeps ordering deterministic.
SHIM = """
var __jobs = [];
var console = { log: function () {}, warn: function () {}, error: function () {} };
function setTimeout(fn, _delay) { __jobs.push(fn); return __jobs.length; }
function clearTimeout(_id) {}
function __drain() { var n = 0; while (__jobs.length) { __jobs.shift()(); n++; } return n; }
"""

DRIVER = """
var __out = [];
var app = Elm.%(module)s.init({ flags: %(flags)s });
app.ports.%(port)s.subscribe(function (payload) { __out.push(payload); });
__drain();
JSON.stringify(__out);
"""


class RenderError(Exception):
    """The generator failed to produce output."""


def render(program: str, flags, *, module: str = "Site", port: str = "emit") -> list:
    """Run a compiled Elm worker and return everything it sent out its port.

    `program` is the output of `elm make`. Evaluated as a script rather than a
    module, Elm's trailing `}(this))` binds to the global object, so `Elm` lands
    on globalThis — which is why this needs none of the CommonJS ceremony Node
    would require.
    """
    context = quickjs.Context()
    context.set_max_stack_size(STACK_BYTES)
    context.set_memory_limit(MEMORY_BYTES)
    try:
        context.eval(SHIM)
        context.eval(program)
        emitted = context.eval(
            DRIVER % {"module": module, "flags": json.dumps(flags), "port": port}
        )
    except Exception as exc:  # quickjs raises its own exception types
        raise RenderError(f"{type(exc).__name__}: {exc}") from exc
    return json.loads(emitted)


def render_site(program: str, flags) -> dict[str, str]:
    """Render the site as a mapping of published path to file content.

    The generator emits one JSON document describing every page, so the whole
    site is produced by a single pass and Python does all the file writing.
    """
    emitted = render(program, flags)
    if not emitted:
        raise RenderError("the generator emitted nothing")
    pages = json.loads(emitted[0]) if isinstance(emitted[0], str) else emitted[0]
    files = {}
    for page in pages:
        path, content = page["path"], page["content"]
        if path in files:
            raise RenderError(f"the generator emitted {path} twice")
        if path.startswith("/") or ".." in path:
            raise RenderError(f"refusing an unsafe published path: {path}")
        files[path] = content
    return files
