#!/bin/bash

pkgdir=$1
pkgname=$2
rebuild_current=${3:-false}

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
pacman -Sy --noconfirm &&

# 切换到 builder 用户执行脚本
su - builder -c "cd /github/workspace && bash scripts/${pkgname}.sh"

#echo OK
