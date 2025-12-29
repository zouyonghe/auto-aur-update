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

# 手动计算多架构校验和，避免 updpkgsums 的 bug
url="https://github.com/zouyonghe/PixelTerm-C/releases/download/v${latest_ver}"
comp_base="https://raw.githubusercontent.com/zouyonghe/PixelTerm-C/main/completions"

echo "Downloading and calculating checksums for x86_64..."
if curl -sL "${url}/pixelterm-amd64-linux" -o /tmp/pixelterm-amd64-linux; then
    md5_x86_64=$(md5sum /tmp/pixelterm-amd64-linux | cut -d' ' -f1)
    echo "x86_64 checksum: ${md5_x86_64}"
else
    echo "Failed to download x86_64 binary"
    exit 1
fi

echo "Downloading and calculating checksums for aarch64..."
if curl -sL "${url}/pixelterm-arm64-linux" -o /tmp/pixelterm-arm64-linux; then
    md5_aarch64=$(md5sum /tmp/pixelterm-arm64-linux | cut -d' ' -f1)
    echo "aarch64 checksum: ${md5_aarch64}"
else
    echo "Failed to download aarch64 binary"
    exit 1
fi

# 计算补全文件校验和
echo "Downloading and calculating checksums for completions..."
if curl -sL "${comp_base}/bash/pixelterm" -o /tmp/pixelterm.bash; then
    md5_bash=$(md5sum /tmp/pixelterm.bash | cut -d' ' -f1)
    echo "bash completion checksum: ${md5_bash}"
else
    echo "Failed to download bash completion"
    exit 1
fi

if curl -sL "${comp_base}/zsh/_pixelterm" -o /tmp/pixelterm.zsh; then
    md5_zsh=$(md5sum /tmp/pixelterm.zsh | cut -d' ' -f1)
    echo "zsh completion checksum: ${md5_zsh}"
else
    echo "Failed to download zsh completion"
    exit 1
fi

if curl -sL "${comp_base}/fish/pixelterm.fish" -o /tmp/pixelterm.fish; then
    md5_fish=$(md5sum /tmp/pixelterm.fish | cut -d' ' -f1)
    echo "fish completion checksum: ${md5_fish}"
else
    echo "Failed to download fish completion"
    exit 1
fi

# 检查 md5 值是否有效
if [ -z "$md5_x86_64" ] || [ -z "$md5_aarch64" ] || [ -z "$md5_bash" ] || [ -z "$md5_zsh" ] || [ -z "$md5_fish" ]; then
    echo "Error: MD5 checksums are empty"
    exit 1
fi

# 更新 PKGBUILD 中的校验和
# 使用更可靠的方式替换 md5sums
sed -i "s/^md5sums_x86_64=.*/md5sums_x86_64=('${md5_x86_64}')/" PKGBUILD
sed -i "s/^md5sums_aarch64=.*/md5sums_aarch64=('${md5_aarch64}')/" PKGBUILD
sed -i "s/^md5sums=.*/md5sums=('${md5_bash}' '${md5_zsh}' '${md5_fish}')/" PKGBUILD

# 验证 md5sums 是否已正确更新
echo "Verifying updated md5sums..."
grep "md5sums_x86_64" PKGBUILD
grep "md5sums_aarch64" PKGBUILD
grep "^md5sums=" PKGBUILD

# 再次检查更新后的 md5sums 是否为空
if grep -q "md5sums_.*=('')" PKGBUILD || grep -q "^md5sums=('')" PKGBUILD; then
    echo "Error: MD5 checksums in PKGBUILD are empty after update"
    exit 1
fi

# 清理临时文件
rm -f /tmp/pixelterm-amd64-linux /tmp/pixelterm-arm64-linux /tmp/pixelterm.bash /tmp/pixelterm.zsh /tmp/pixelterm.fish
makepkg --printsrcinfo > .SRCINFO
rm -f pixelterm*

cd -
