#!/usr/bin/env bash
#
# The weekly run, for cron.
#
#   ./weekly.sh collect    gather evidence; safe and useful to run repeatedly
#   ./weekly.sh publish    derive, print and render, once the window has closed
#
# Split in two because collection and publication want different schedules.
# `collect` merges into the period's existing manifest, keeping every
# conclusive observation and re-attempting only the domains we learned nothing
# about, so running it several times across the 72-hour window is how coverage
# climbs. `publish` freezes the number and must therefore happen once, after
# the window has closed and the evidence has stopped improving.

set -euo pipefail

cd "$(dirname "$0")"

export PYTHONPATH=src
LOG_DIR=.cache/logs
mkdir -p "$LOG_DIR"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

# Committing is part of the run, not an afterthought: a print that exists only
# on one machine's disk is not published, and the ledger's promise is about
# what is committed. Nothing is pushed -- that stays a human decision.
commit_data() {
    local message="$1"
    if [ -z "$(git status --porcelain data/)" ]; then
        log "nothing to commit"
        return 0
    fi
    git add data/
    git commit -q -m "$message"
    log "committed: $message"
}

case "${1:-}" in
    collect)
        period=$(python3 -c 'from datetime import datetime, timezone; from tallyhouse.periods import period_for; print(period_for(datetime.now(timezone.utc)))')
        log "collecting $period"
        # No --ignore-window: outside the window this is meant to fail. Evidence
        # labelled with a week it was not gathered in is worse than no evidence.
        python3 -m tallyhouse.cli collect --agents 2
        commit_data "Collect $period"
        ;;

    publish)
        # Run after the window has closed, so the period to publish is the one
        # that just ended rather than the one now open.
        period=$(python3 -c '
from datetime import datetime, timezone
from tallyhouse.periods import period_for, previous_period, is_within_window
now = datetime.now(timezone.utc)
current = period_for(now)
# Inside the window the current period is still collecting; the finished one
# is the week before.
print(current if not is_within_window(current, now) else previous_period(current))
')
        log "publishing $period"
        # --agents is pinned rather than inferred, and deliberately so: the
        # agent set is methodology, and bumping it restates every affected
        # published row. That should take a human editing this line, not a
        # scheduled job noticing a new file. The site reads the agent set back
        # off each print, so it can never disagree with what was published.
        python3 -m tallyhouse.cli derive --period "$period" --agents 2
        python3 -m tallyhouse.cli print --period "$period" --agents 2
        commit_data "Publish $period"

        # The site is downstream of the ledger and not required for the number
        # to be published, so a missing compiler must not fail the run.
        if command -v elm >/dev/null 2>&1; then
            (cd generate && elm make src/Site.elm --optimize --output=site.js >/dev/null)
            python3 -m tallyhouse.cli generate --out site
        else
            log "warning: elm not on PATH; skipped rendering the site"
        fi
        ;;

    *)
        echo "usage: $0 {collect|publish}" >&2
        exit 2
        ;;
esac
