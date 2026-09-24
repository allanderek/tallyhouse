#!/usr/bin/env bash
#
# Build the site and serve it for local inspection.
#
#   ./debug.sh          serve on port 8080
#   ./debug.sh 9000     serve on another port
#
# Ctrl+C stops the server and releases the port: the final `exec` replaces this
# shell with the server, so the signal reaches the server directly and there is
# no parent left holding the socket open afterwards.

set -euo pipefail

cd "$(dirname "$0")"

PORT="${1:-8080}"
OUT=site

# Refuse rather than fight over the port. Killing whatever is listening would be
# the convenient thing and the wrong thing -- on a shared machine it might not be
# ours, and this script is for looking at a website.
if command -v ss >/dev/null 2>&1; then
    if ss -ltn "sport = :$PORT" 2>/dev/null | grep -q LISTEN; then
        echo "error: port $PORT is already in use. Listening process:" >&2
        # `>&2` before `2>/dev/null`: the other order copies fd2 after it has
        # already been pointed at /dev/null, so the diagnostic goes nowhere.
        ss -ltnp "sport = :$PORT" >&2 2>/dev/null || true
        echo "Stop it, or pass a different port: ./debug.sh 9000" >&2
        exit 1
    fi
fi

echo "==> compiling the generator"
# Always recompiled: the generate step refuses a site.js older than its sources
# rather than silently rendering a stale site, and this script exists precisely
# to look at changes just made.
(cd generate && elm make src/Site.elm --optimize --output=site.js)

echo "==> deriving the latest published period"
# The crawler pages' stance counts come from data/derived/, which is gitignored
# and holds whichever period was derived last. Deriving the latest published
# period here keeps the served pages consistent with the headline they sit under.
period=$(PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
from tallyhouse.ledger import read_rows
from tallyhouse.publish import INDEX_ID
periods = [r["period"] for r in read_rows(Path("data/prints.csv"))
           if r["index_id"] == INDEX_ID]
print(max(periods) if periods else "")
PY
)
if [ -n "$period" ]; then
    # A failure here costs the per-crawler stance counts, not the site, so say
    # so and carry on rather than refusing to serve anything.
    PYTHONPATH=src python3 -m tallyhouse.cli derive --period "$period" --agents 2 \
        || echo "warning: derive failed for $period; crawler pages will show zeroes" >&2
else
    echo "warning: no published prints found; skipping derive" >&2
fi

echo "==> generating the site"
PYTHONPATH=src python3 -m tallyhouse.cli generate --out "$OUT"

echo
echo "==> serving $OUT on http://localhost:$PORT/   (Ctrl+C to stop)"
echo
exec python3 -m http.server "$PORT" --directory "$OUT"
