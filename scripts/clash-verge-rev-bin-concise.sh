#!/bin/bash

cd clash-verge-rev-bin-concise

ver_clash=$(curl -s https://api.github.com/repos/clash-verge-rev/clash-verge-rev/releases/latest | jq '.tag_name'|tr -d 'v"')
sed -i "s/pkgver=.*/pkgver=$ver_clash/" PKGBUILD
sudo -u builder  updpkgsums
makepkg --printsrcinfo > .SRCINFO

rm clash-verge-rev-"$ver_clash"-x86_64.deb
cd -
