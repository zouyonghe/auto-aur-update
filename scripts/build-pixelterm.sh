#!/bin/bash

set -o errexit -o nounset -o pipefail
unset GH_TOKEN GITHUB_TOKEN

# CI runs this on a disposable runner, never the preparation/publishing runner.
package=$(realpath "$1")
expected=$(sed -n 's/^# rebuild-deps: //p' "$package/PKGBUILD")
pattern='^libmupdf=[a-zA-Z0-9.:_+~-]+ ffmpeg=[a-zA-Z0-9.:_+~-]+$'
[[ "$expected" =~ $pattern ]] || { echo 'Invalid build dependency record' >&2; exit 1; }
installed_dependencies() {
    LC_ALL=C pacman -Q libmupdf ffmpeg | awk '{print $1 "=" $2}' | paste -sd ' ' -
}
sudo pacman -Su --needed --noconfirm libmupdf ffmpeg
actual=$(installed_dependencies)
[[ "$actual" == "$expected" ]] || { echo 'Dependencies changed since preparation; rerun' >&2; exit 1; }

workspace=$(mktemp -d)
trap 'rm -rf "$workspace"' EXIT
cp "$package/PKGBUILD" "$workspace/PKGBUILD"
cd "$workspace"
makepkg --cleanbuild --syncdeps --check --noconfirm --force
actual=$(installed_dependencies)
[[ "$actual" == "$expected" ]] || { echo 'Dependency versions changed during build' >&2; exit 1; }
# No build outputs are returned to the publishing job.
