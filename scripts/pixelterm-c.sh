#!/bin/bash

cd pixelterm-c

# 获取当前 PKGBUILD 中的版本号
current_ver=$(grep "pkgver=" PKGBUILD | cut -d"=" -f2)

# 获取 GitHub 最新版本号
latest_ver=$(curl -sL https://api.github.com/repos/zouyonghe/PixelTerm-C/releases/latest \
    | jq -r '.tag_name // empty' 2>/dev/null \
    | sed 's/^v//')
if [ -z "$latest_ver" ]; then
    latest_ver=$(curl -sL -o /dev/null -w '%{url_effective}' \
        https://github.com/zouyonghe/PixelTerm-C/releases/latest \
        | sed 's#.*/tag/##' \
        | sed 's/^v//')
fi
if [ -z "$latest_ver" ]; then
    latest_ver=$(git ls-remote --tags https://github.com/zouyonghe/PixelTerm-C.git \
        | awk -F/ '{print $3}' \
        | grep -E '^[v]?[0-9]+(\\.[0-9]+)*$' \
        | sed 's/^v//' \
        | sort -V \
        | tail -n1)
fi
if [ -z "$latest_ver" ]; then
    echo "Failed to determine latest version"
    exit 1
fi

echo "Updating from $current_ver to $latest_ver (always update mode)..."
sed -i "s/pkgver=.*/pkgver=$latest_ver/" PKGBUILD
sed -i "s/pkgrel=.*/pkgrel=1/" PKGBUILD

# 手动计算源码包校验和，避免 updpkgsums 的 bug
base_url="https://github.com/zouyonghe/PixelTerm-C"
tarball_url="${base_url}/archive/refs/tags/v${latest_ver}.tar.gz"

echo "Downloading and calculating checksum for source tarball..."
if curl -sL "${tarball_url}" -o /tmp/pixelterm-c.tar.gz; then
    sha256_src=$(sha256sum /tmp/pixelterm-c.tar.gz | cut -d' ' -f1)
    echo "source tarball checksum: ${sha256_src}"
else
    echo "Failed to download source tarball"
    exit 1
fi

# 检查 sha256 值是否有效
if [ -z "$sha256_src" ]; then
    echo "Error: SHA256 checksum is empty"
    exit 1
fi

# 更新 PKGBUILD 中的校验和
sed -i "s/^sha256sums=.*/sha256sums=('${sha256_src}')/" PKGBUILD

# 验证 sha256sums 是否已正确更新
echo "Verifying updated sha256sums..."
grep "^sha256sums=" PKGBUILD

# 再次检查更新后的 sha256sums 是否为空
if grep -q "^sha256sums=('')" PKGBUILD; then
    echo "Error: SHA256 checksums in PKGBUILD are empty after update"
    exit 1
fi

# 清理临时文件
rm -f /tmp/pixelterm-c.tar.gz
makepkg --printsrcinfo > .SRCINFO
rm -f pixelterm*

cd -
