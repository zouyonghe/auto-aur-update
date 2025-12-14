#!/bin/bash

pkgdir=$1
pkgname=$2

useradd builder -m
echo "builder ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
chown -R builder:builder .
chmod -R a+rw .

pacman-key --init
pacman -Sy --noconfirm &&

# 切换到 builder 用户执行脚本
su - builder -c "cd /github/workspace && bash scripts/${pkgname}.sh"

#echo OK
