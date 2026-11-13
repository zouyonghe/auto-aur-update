#!/bin/bash

set -o errexit -o nounset -o pipefail

unset GH_TOKEN GITHUB_TOKEN

pkgdir=$1
pkgname=$2
rebuild_current=${3:-false}
if [[ ! "$pkgname" =~ ^[a-z0-9][a-z0-9@._+-]*$ ]]; then
    echo 'Invalid package name' >&2
    exit 1
fi

case "$rebuild_current" in
    false) ;;
    true)
        echo '::error::rebuild_current is no longer supported. Set the committed pkgver to the current AUR version, increase pkgrel above the published revision, and dispatch without rebuild_current.' >&2
        exit 1
        ;;
    *)
        echo '::error::rebuild_current must be true or false' >&2
        exit 1
        ;;
esac

useradd builder -m
echo "builder ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
chown -R builder:builder .
chmod -R a+rw .

pacman-key --init
bash scripts/retry-pacman.sh -Syu --noconfirm

# 切换到 builder 用户执行脚本
runuser --user builder -- bash "/github/workspace/scripts/${pkgname}.sh"

#echo OK
