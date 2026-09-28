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
#
# Neither cares when it runs. `collect` refuses outside the window rather than
# mislabelling evidence, and `publish` asks the evidence what is outstanding
# rather than inferring a period from the clock -- so a missed run costs a
# delay, never a gap.

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
        # What to publish is decided by the evidence, not by the clock. A period
        # qualifies once it has a manifest, its window has closed, and the ledger
        # has no row for it -- so this job can run late, twice, or not at all
        # without consequence. The work is simply still pending next time.
        periods=$(python3 -m tallyhouse.cli due)
        if [ -z "$periods" ]; then
            log "nothing due"
            exit 0
        fi

        # Oldest first, because each period's like-for-like change is computed
        # against its predecessor.
        for period in $periods; do
            log "publishing $period"
            # --agents is pinned rather than inferred, and deliberately so: the
            # agent set is methodology, and bumping it restates every affected
            # published row. That should take a human editing this line, not a
            # scheduled job noticing a new file. The site reads the agent set
            # back off each print, so it can never disagree with what was
            # published.
            python3 -m tallyhouse.cli derive --period "$period" --agents 2
            python3 -m tallyhouse.cli print  --period "$period" --agents 2
            commit_data "Publish $period"
        done

        # Rendered once, after every pending period is in the ledger, rather
        # than once per period: the site shows the whole series, so intermediate
        # renders would be thrown away.
        #
        # The site is downstream of the ledger and not required for a number to
        # be published, so a missing compiler must not fail the run.
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
