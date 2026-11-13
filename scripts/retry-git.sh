#!/bin/bash

set -euo pipefail
workspace=$(mktemp -d)
trap 'rm -rf "$workspace"' EXIT
arguments=("$@")
if [[ ${arguments[0]} == clone ]]; then
    destination=${arguments[-1]}
    [[ ! -e "$destination" ]] || { echo 'Clone destination already exists' >&2; exit 1; }
    arguments[-1]="$workspace/package"
fi
for attempt in 1 2 3; do
    status=0
    timeout --signal=TERM --kill-after=5s 60s git "${arguments[@]}" > "$workspace/output" || status=$?
    if (( status == 0 )); then
        if [[ ${arguments[0]} == clone ]]; then mv "$workspace/package" "$destination"; fi
        cat "$workspace/output"
        exit 0
    fi
    if (( attempt == 3 || status == 130 || status == 137 || status == 143 )); then exit "$status"; fi
    if [[ ${arguments[0]} == clone ]]; then rm -rf "$workspace/package"; fi
    sleep "$((attempt * 5))"
done
