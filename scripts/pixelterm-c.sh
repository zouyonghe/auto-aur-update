#!/bin/bash

set -o errexit -o nounset -o pipefail

# Release authentication belongs to a separate workflow step, never build tools.
unset GH_TOKEN GITHUB_TOKEN
script_dir=$(cd "$(dirname "$0")" && pwd)
curl() {
    command curl --connect-timeout 10 --max-time 180 --retry 2 --retry-delay 5 \
        --retry-max-time 240 "$@"
}

cd "$(dirname "$0")/../pixelterm-c"

# Treat AUR metadata and the dependency comment as data; never source its PKGBUILD.
aur_dir=$(mktemp -d)
trap 'rm -rf "$aur_dir"' EXIT
if bash "$script_dir/retry-git.sh" clone --quiet --depth=1 https://aur.archlinux.org/pixelterm-c.git "$aur_dir/package"; then
    aur_srcinfo="$aur_dir/package/.SRCINFO"
else
    echo "Failed to read current package metadata from AUR" >&2
    exit 1
fi

git -C "$aur_dir/package" rev-parse HEAD > .aur-revision

current_ver=$(sed -n 's/^[[:space:]]*pkgver = //p' "$aur_srcinfo" | head -n1)
current_rel=$(sed -n 's/^[[:space:]]*pkgrel = //p' "$aur_srcinfo" | head -n1)
if [[ ! "$current_ver" =~ ^[0-9]+(\.[0-9]+)*$ || ! "$current_rel" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    echo "Invalid pkgver/pkgrel in AUR .SRCINFO" >&2
    exit 1
fi
template_ver=$(sed -n 's/^[[:space:]]*pkgver=//p' PKGBUILD | head -n1)
template_rel=$(sed -n 's/^[[:space:]]*pkgrel=//p' PKGBUILD | head -n1)
if [[ ! "$template_ver" =~ ^[0-9]+(\.[0-9]+)*$ || ! "$template_rel" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    echo "Invalid pkgver/pkgrel in PKGBUILD" >&2
    exit 1
fi

# Reconcile against the entrypoint's refreshed snapshot, then record build inputs.
# shortcut: x86_64 repository only; add per-arch probes if ARM-only updates matter.
bash "$script_dir/retry-pacman.sh" -Su --needed --noconfirm libmupdf ffmpeg
installed_dependency_record() {
    LC_ALL=C pacman -Q libmupdf ffmpeg | awk '{print $1 "=" $2}' | paste -sd ' ' -
}
if ! dependency_record=$(installed_dependency_record); then
    echo "Failed to query dependency versions" >&2
    exit 1
fi
dependency_pattern='^libmupdf=[a-zA-Z0-9.:_+~-]+ ffmpeg=[a-zA-Z0-9.:_+~-]+$'
if [[ ! "$dependency_record" =~ $dependency_pattern ]]; then
    echo "Invalid dependency versions from Arch" >&2
    exit 1
fi
published_record=$(sed -n 's/^# rebuild-deps: //p' "$aur_dir/package/PKGBUILD")
record_count=$(grep -cE '^[[:space:]]*#+[[:space:]]*rebuild-deps' "$aur_dir/package/PKGBUILD" || true)
if (( record_count > 1 )) ||
   { (( record_count == 1 )) && [[ ! "$published_record" =~ $dependency_pattern ]]; }; then
    echo "Invalid published dependency record" >&2
    exit 1
fi

# CI passes only public release metadata from its authenticated request.
latest_ver=''
if [[ -n "${PIXELTERM_RELEASE_TAG:-}" ]]; then
    if [[ ! "$PIXELTERM_RELEASE_TAG" =~ ^v[0-9]+(\.[0-9]+)*$ ]]; then
        echo "Invalid pre-resolved release tag" >&2
        exit 1
    fi
    latest_ver=${PIXELTERM_RELEASE_TAG#v}
else
    latest_ver=$(curl --fail --silent --show-error --location https://api.github.com/repos/zouyonghe/PixelTerm-C/releases/latest \
        | jq -r '.tag_name // empty' 2>/dev/null \
        | sed 's/^v//' || true)
fi
if [ -z "$latest_ver" ]; then
    latest_ver=$(curl --fail --silent --show-error --location -o /dev/null -w '%{url_effective}' \
        https://github.com/zouyonghe/PixelTerm-C/releases/latest \
        | sed 's#.*/tag/##' \
        | sed 's/^v//' || true)
fi
if [ -z "$latest_ver" ]; then
    latest_ver=$(bash "$script_dir/retry-git.sh" ls-remote --tags https://github.com/zouyonghe/PixelTerm-C.git \
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
    if [[ "$published_record" != "$dependency_record" || "$latest_ver" != "$current_ver" ]]; then
        next_rel=$((10#${current_rel##*.} + 1))
        if [[ "$current_rel" == *.* ]]; then
            next_rel="${current_rel%.*}.${next_rel}"
        fi
        if (( $(vercmp "$next_rel" "$current_rel") <= 0 )); then
            echo "Cannot safely increment pkgrel=$current_rel" >&2
            exit 1
        fi
        current_rel=$next_rel
        echo "Dependency versions or upstream version spelling changed; requesting pkgrel=$current_rel"
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
sed -i -E '/^[[:space:]]*#+[[:space:]]*rebuild-deps/d' PKGBUILD
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
comparison_status=0
cmp -s PKGBUILD "$aur_dir/package/PKGBUILD" || comparison_status=$?
case "$comparison_status" in
    0)
        metadata_status=0
        cmp -s .SRCINFO "$aur_srcinfo" || metadata_status=$?
        case "$metadata_status" in
            0) echo "Package and dependency versions unchanged; skipping build" ;;
            1) echo "Repairing generated AUR metadata without a source rebuild" ;;
            *) echo "Failed to compare .SRCINFO" >&2; exit 1 ;;
        esac
        echo false > build-required ;;
    1) echo true > build-required ;;
    *) echo "Failed to compare PKGBUILD; check diffutils and file access." >&2; exit 1 ;;
esac

cd -
