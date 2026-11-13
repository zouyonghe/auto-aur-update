#!/bin/bash

set -o errexit -o nounset -o pipefail

cd "$(dirname "$0")/../pixelterm-c"

# Treat AUR metadata and the dependency comment as data; never source its PKGBUILD.
aur_dir=$(mktemp -d)
trap 'rm -rf "$aur_dir"' EXIT
if git clone --quiet --depth=1 https://aur.archlinux.org/pixelterm-c.git "$aur_dir/package"; then
    aur_srcinfo="$aur_dir/package/.SRCINFO"
else
    echo "Failed to read current package metadata from AUR" >&2
    exit 1
fi

git -C "$aur_dir/package" rev-parse HEAD > .aur-revision

current_ver=$(sed -n 's/^[[:space:]]*pkgver = //p' "$aur_srcinfo" | head -n1)
current_rel=$(sed -n 's/^[[:space:]]*pkgrel = //p' "$aur_srcinfo" | head -n1)
if [[ ! "$current_ver" =~ ^[0-9]+(\.[0-9]+)*$ || ! "$current_rel" =~ ^[0-9]+$ ]]; then
    echo "Invalid pkgver/pkgrel in AUR .SRCINFO" >&2
    exit 1
fi
template_ver=$(sed -n 's/^[[:space:]]*pkgver=//p' PKGBUILD | head -n1)
template_rel=$(sed -n 's/^[[:space:]]*pkgrel=//p' PKGBUILD | head -n1)
if [[ ! "$template_ver" =~ ^[0-9]+(\.[0-9]+)*$ || ! "$template_rel" =~ ^[0-9]+$ ]]; then
    echo "Invalid pkgver/pkgrel in PKGBUILD" >&2
    exit 1
fi

# Query the refreshed Arch database, preserving epochs and package revisions.
# shortcut: x86_64 repository only; add per-arch probes if ARM-only updates matter.
if ! dependency_packages=$(LC_ALL=C pacman -Sp --print-format '%n=%v' --nodeps libmupdf ffmpeg); then
    echo "Failed to query dependency versions" >&2
    exit 1
fi
dependency_record=$(printf '%s\n' "$dependency_packages" | paste -sd ' ' -)
dependency_pattern='^libmupdf=[a-zA-Z0-9.:_+~-]+ ffmpeg=[a-zA-Z0-9.:_+~-]+$'
if [[ ! "$dependency_record" =~ $dependency_pattern ]]; then
    echo "Invalid dependency versions from Arch" >&2
    exit 1
fi
published_record=$(sed -n 's/^# rebuild-deps: //p' "$aur_dir/package/PKGBUILD")
record_count=$(grep -c '^# rebuild-deps:' "$aur_dir/package/PKGBUILD" || true)
if (( record_count > 1 )) ||
   { (( record_count == 1 )) && [[ ! "$published_record" =~ $dependency_pattern ]]; }; then
    echo "Invalid published dependency record" >&2
    exit 1
fi

# 获取 GitHub 最新版本号
api_headers=()
if [[ -n "${GH_TOKEN:-}" ]]; then
    api_headers=(-H "Authorization: Bearer ${GH_TOKEN}")
fi
latest_ver=$(curl --fail --silent --show-error --location "${api_headers[@]}" https://api.github.com/repos/zouyonghe/PixelTerm-C/releases/latest \
    | jq -r '.tag_name // empty' 2>/dev/null \
    | sed 's/^v//' || true)
if [ -z "$latest_ver" ]; then
    latest_ver=$(curl --fail --silent --show-error --location -o /dev/null -w '%{url_effective}' \
        https://github.com/zouyonghe/PixelTerm-C/releases/latest \
        | sed 's#.*/tag/##' \
        | sed 's/^v//' || true)
fi
if [ -z "$latest_ver" ]; then
    latest_ver=$(git ls-remote --tags https://github.com/zouyonghe/PixelTerm-C.git \
        | awk -F/ '{print $3}' \
        | grep -E '^v?[0-9]+(\.[0-9]+)*$' \
        | sed 's/^v//' \
        | sort -V \
        | tail -n1 || true)
fi
if [[ ! "$latest_ver" =~ ^[0-9]+(\.[0-9]+)*$ ]]; then
    echo "Failed to determine latest version"
    exit 1
fi

echo "Reconciling $current_ver with upstream $latest_ver..."
version_order=$(vercmp "$latest_ver" "$current_ver")
if (( version_order < 0 )); then
    echo "Latest upstream version $latest_ver is older than AUR version $current_ver" >&2
    exit 1
fi

sed -i "s/^[[:space:]]*pkgver=.*/pkgver=$latest_ver/" PKGBUILD
if (( version_order > 0 )); then
    # New upstream version starts a fresh package release.
    sed -i "s/^[[:space:]]*pkgrel=.*/pkgrel=1/" PKGBUILD
else
    if [[ "$published_record" != "$dependency_record" ]]; then
        current_rel=$((10#$current_rel + 1))
        echo "Dependency versions changed; requesting pkgrel=$current_rel"
    fi
    if (( $(vercmp "$template_ver" "$current_ver") == 0 )) &&
       (( $(vercmp "$template_rel" "$current_rel") > 0 )); then
        current_rel=$template_rel
    fi
    # Keep the higher revision from the committed template or published AUR package.
    sed -i "s/^[[:space:]]*pkgrel=.*/pkgrel=$current_rel/" PKGBUILD
fi

# 手动计算源码包校验和，避免 updpkgsums 的 bug
base_url="https://github.com/zouyonghe/PixelTerm-C"
tarball_url="${base_url}/archive/refs/tags/v${latest_ver}.tar.gz"

echo "Downloading and calculating checksum for source tarball..."
curl --fail --silent --show-error --location "${tarball_url}" -o "$aur_dir/source.tar.gz"
sha256_src=$(sha256sum "$aur_dir/source.tar.gz" | cut -d' ' -f1)
echo "source tarball checksum: ${sha256_src}"

# 检查 sha256 值是否有效
if [ -z "$sha256_src" ]; then
    echo "Error: SHA256 checksum is empty"
    exit 1
fi

# 更新 PKGBUILD 中的校验和
sed -i "s/^sha256sums=.*/sha256sums=('${sha256_src}')/" PKGBUILD
sed -i '/^# rebuild-deps:/d' PKGBUILD
printf '# rebuild-deps: %s\n' "$dependency_record" >> PKGBUILD

# 验证 sha256sums 是否已正确更新
echo "Verifying updated sha256sums..."
grep "^sha256sums=" PKGBUILD

# 再次检查更新后的 sha256sums 是否为空
if grep -q "^sha256sums=('')" PKGBUILD; then
    echo "Error: SHA256 checksums in PKGBUILD are empty after update"
    exit 1
fi

makepkg --printsrcinfo > .SRCINFO
if cmp -s PKGBUILD "$aur_dir/package/PKGBUILD"; then
    echo "Package and dependency versions unchanged; skipping build"
else
    makepkg --cleanbuild --syncdeps --noconfirm --force
fi

cd -
