#!/bin/bash

set -euo pipefail
# Retry package transactions only; never retry upstream build commands.
for attempt in 1 2 3; do
    status=0
    sudo timeout --signal=TERM --kill-after=10s 180s pacman "$@" || status=$?
    if (( status == 0 )); then exit 0; fi
    if (( attempt == 3 || status == 130 || status == 137 || status == 143 )); then
        exit "$status"
    fi
    echo "pacman attempt $attempt failed ($status); retrying" >&2
    sleep "$((attempt * 5))"
done
