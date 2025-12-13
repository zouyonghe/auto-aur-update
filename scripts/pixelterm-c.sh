#!/bin/bash

cd pixelterm-c

ver_pixelterm=$(curl -s https://api.github.com/repos/zouyonghe/PixelTerm-C/releases/latest | jq ".tag_name"|tr -d "v\"")
sed -i "s/pkgver=.*/pkgver=$ver_pixelterm/" PKGBUILD
sudo -u builder updpkgsums
makepkg --printsrcinfo > .SRCINFO

rm -f pixelterm*
cd -
