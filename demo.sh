#!/usr/bin/env bash
# Stiltstep demo: runs every check end to end, non-interactively, then exits.
#
# Usage:  bash demo.sh
#         PYTHON=python3.11 bash demo.sh
#
# Nothing here prompts, downloads or writes a file. Failures marked "by design"
# are the tool reporting a rule failure (exit 1) or a usage error (exit 2).
set -uo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
crashes=0

run() {
    printf '\n$ stiltstep %s\n\n' "$*"
    output="$("$PYTHON" stiltstep.py "$@" 2>&1)"
    status=$?
    printf '%s\n' "$output"
    printf '\n[exit %d]\n' "$status"
    case "$output" in
        *"Traceback (most recent call last)"*) crashes=$((crashes + 1)) ;;
    esac
    return 0
}

printf 'STILTSTEP DEMO\n'
printf 'Staddle stone grading, granary floor layout and rodent guard checks.\n'
printf 'Every dimension below is in centimetres.\n'

run --version
run
run grade --height 60 --cap-diameter 45 --base-diameter 30
run grade --height 180 --cap-diameter 45
run grade --height 60 --cap-diameter 45 --min-height-ratio 1.40
run layout --length 400 --width 300 --stone-spacing 100
run layout --length 400 --width 300 --stone-spacing 500
run guard --guard-diameter 45 --cap-diameter 60 --gap 3 --clearance 50
run guard --guard-diameter 45 --cap-diameter 50 --gap 6 --clearance 30
run guard --guard-diameter 45 --cap-diameter 60 --gap 3 --clearance 50 --min-overhang 8

printf '\n'
printf 'DEMO ERROR PATHS\n'
run grade --height abc --cap-diameter 45
run grade --height 60
run layout --length 0 --width 300 --stone-spacing 100
run guard --guard-diameter 45 --cap-diameter 40 --gap 3 --clearance 50
run grade --height 60 --cap-diameter 45 --min-height-ratio tall

printf '\n'
if [ "$crashes" -ne 0 ]; then
    printf 'DEMO FAILED: %d invocation(s) printed a Python traceback.\n' "$crashes"
    exit 1
fi
printf 'Demo complete. Exit codes shown above: 0 pass, 1 rule failure, 2 usage error.\n'
exit 0
