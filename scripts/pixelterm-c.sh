#!/bin/bash

cd pixelterm-c

# 获取当前 PKGBUILD 中的版本号
current_ver=$(grep "pkgver=" PKGBUILD | cut -d"=" -f2)

# 获取 GitHub 最新版本号
latest_ver=$(curl -s https://api.github.com/repos/zouyonghe/PixelTerm-C/releases/latest | jq ".tag_name"|tr -d "v\"")

# 比较版本号，如果不同才更新
if [ "$current_ver" != "$latest_ver" ]; then
    echo "Version changed from $current_ver to $latest_ver, updating..."
    sed -i "s/pkgver=.*/pkgver=$latest_ver/" PKGBUILD
    sed -i "s/pkgrel=.*/pkgrel=1/" PKGBUILD
    sudo -u builder updpkgsums
    makepkg --printsrcinfo > .SRCINFO
    rm -f pixelterm*
else
    echo "Version $current_ver is already up to date, no changes needed."
fi

cd -
