# Maintainer: Zenvie <134689569+Zenvie@users.noreply.github.com>
# Contributor: Felix Yan <felixonmars@archlinux.org>
# Contributor: buding <1259085392z@gmail.com>

pkgname=v2ray-rules-dat
pkgver=202407152211
pkgrel=2
pkgdesc="Enhanced edition of V2Ray rules dat files"
arch=(any)
url="https://github.com/Loyalsoldier/$pkgname"
license=(CC-BY-SA-4.0 MIT GPL-3.0-or-later)

provides=(v2ray-domain-list-community v2ray-geoip)
conflicts=(v2ray-domain-list-community v2ray-geoip)

source=("$url/releases/download/$pkgver/geoip.dat"
        "$url/releases/download/$pkgver/geosite.dat"
        "$url/releases/download/$pkgver/geoip.dat.sha256sum"
        "$url/releases/download/$pkgver/geosite.dat.sha256sum"
        "https://raw.githubusercontent.com/Loyalsoldier/domain-list-custom/master/LICENSE")
sha256sums=('fd224548b0309f0810b03c13ae61cc41a6968fe6b1639c82de371485200fbcbb'
            '2aa65adc62f65c0f3a2f44b09574b9b4371b3082e024a0c4ca13d688294038ac'
            '2a189edbd913172257960946fea01b430e552a7d2d3eb3c6b6dd430be37633fc'
            '9d07a0613a96c95da722982a29e4baafd2d69c5dc598811b045b74a41df274a8'
            '35f18e0331a1ecd1835400c50e3b367c2ce09f6c13d91c4a0f3cb11f71d3bbc3')

prepare() {
  sha256sum -c *.dat.sha256sum
}

package() {
  install -dm755 "$pkgdir/usr/share/v2ray"
  install -Dm644 *.dat "$pkgdir/usr/share/v2ray"
  install -Dm644 LICENSE -t "$pkgdir/usr/share/licenses/$pkgname"
}
