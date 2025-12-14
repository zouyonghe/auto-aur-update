#!/bin/bash

pkgdir=$1
pkgname=$2


useradd builder -m
echo "builder ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
chmod -R a+rw .

pacman-key --init
pacman -Sy --noconfirm &&

bash scripts/${pkgname}.sh

#echo OK
