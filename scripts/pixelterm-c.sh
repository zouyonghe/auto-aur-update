#!/bin/bash

cd pixelterm-c

# 获取当前 PKGBUILD 中的版本号
current_ver=$(grep "pkgver=" PKGBUILD | cut -d"=" -f2)

# 获取 GitHub 最新版本号
latest_ver=$(curl -s https://api.github.com/repos/zouyonghe/PixelTerm-C/releases/latest | jq ".tag_name"|tr -d "v\"")

# 检查是否强制更新（跳过版本检测）
if [ "${FORCE_UPDATE:-false}" = "true" ]; then
    echo "Force update mode: skipping version check"
    force_update=true
else
    force_update=false
fi

# 比较版本号，如果不同才更新
if [ "$force_update" = "true" ] || [ "$current_ver" != "$latest_ver" ]; then
    echo "Version changed from $current_ver to $latest_ver, updating..."
    sed -i "s/pkgver=.*/pkgver=$latest_ver/" PKGBUILD
    sed -i "s/pkgrel=.*/pkgrel=1/" PKGBUILD
    # 手动计算多架构校验和，避免 updpkgsums 的 bug
    url="https://github.com/zouyonghe/PixelTerm-C/releases/download/v${latest_ver}"
    
    echo "Downloading and calculating checksums for x86_64..."
    wget -q "${url}/pixelterm-amd64-linux" -O /tmp/pixelterm-amd64-linux
    md5_x86_64=$(md5sum /tmp/pixelterm-amd64-linux | cut -d' ' -f1)
    
    echo "Downloading and calculating checksums for aarch64..."
    wget -q "${url}/pixelterm-arm64-linux" -O /tmp/pixelterm-arm64-linux
    md5_aarch64=$(md5sum /tmp/pixelterm-arm64-linux | cut -d' ' -f1)
    
    echo "x86_64 checksum: ${md5_x86_64}"
    echo "aarch64 checksum: ${md5_aarch64}"
    
    # 更新 PKGBUILD 中的校验和
    sed -i "s/md5sums_x86_64=('[^']*')/md5sums_x86_64=('"${md5_x86_64}"')/" PKGBUILD
    sed -i "s/md5sums_aarch64=('[^']*')/md5sums_aarch64=('"${md5_aarch64}"')/" PKGBUILD
    
    # 清理临时文件
    rm -f /tmp/pixelterm-amd64-linux /tmp/pixelterm-arm64-linux
    makepkg --printsrcinfo > .SRCINFO
    rm -f pixelterm*
else
    echo "Version $current_ver is already up to date, no changes needed."
fi

cd -
