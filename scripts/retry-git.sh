#!/bin/bash

set -euo pipefail
if [[ ${1:-} == clone ]]; then
    # Internal caller supports flags without separate option arguments only.
    positional=()
    for argument in "${@:2}"; do
        case "$argument" in
            --quiet|--depth=*)
                if (( ${#positional[@]} > 0 )) ||
                   { [[ "$argument" != --quiet ]] && [[ ! "$argument" =~ ^--depth=[0-9]+$ ]]; }; then
                    echo 'Clone options must precede repository and explicit destination' >&2
                    exit 2
                fi ;;
            -*) echo 'Usage: retry-git.sh clone [--quiet] [--depth=N] repository explicit destination' >&2; exit 2 ;;
            *) positional+=("$argument") ;;
        esac
    done
    if (( ${#positional[@]} != 2 )); then
        echo 'Usage: retry-git.sh clone [--quiet] [--depth=N] repository explicit destination' >&2
        exit 2
    fi
fi
(( $# > 0 )) || { echo 'Git subcommand required' >&2; exit 2; }
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
