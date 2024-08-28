#!/bin/bash

cd v2ray-rules-dat

ver_dat=$(curl -s https://api.github.com/repos/Loyalsoldier/v2ray-rules-dat/releases/latest | jq '.tag_name'|tr -d 'v"')
sed -i "s/pkgver=.*/pkgver=$ver_dat/" PKGBUILD
sudo -u builder  updpkgsums
makepkg --printsrcinfo > .SRCINFO

cd -
