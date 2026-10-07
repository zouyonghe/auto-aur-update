#!/bin/bash

pkgdir=$1
pkgname=$2
rebuild_current=${3:-false}

if [[ "$rebuild_current" != true && "$rebuild_current" != false ]]; then
    echo "rebuild_current must be true or false" >&2
    exit 1
fi

useradd builder -m
echo "builder ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
chown -R builder:builder .
chmod -R a+rw .

pacman-key --init
pacman -Sy --noconfirm &&

# 切换到 builder 用户执行脚本
su - builder -c "cd /github/workspace && REBUILD_CURRENT=${rebuild_current} bash scripts/${pkgname}.sh"

#echo OK
