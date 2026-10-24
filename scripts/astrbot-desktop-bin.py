#!/usr/bin/env python3
"""Update the trusted AstrBot template using stable GitHub release metadata."""
import json
import os
from pathlib import Path
import re
import urllib.request


def pkgrel_parts(value):
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', value):
        raise ValueError(f'Unsupported pkgrel: {value}')
    return tuple(int(part) for part in value.split('.'))


def max_pkgrel(*values):
    return max(values, key=lambda value: pkgrel_parts(value))


def update(template, release, current):
    tag = release.get('tag_name', '')
    if release.get('draft') or release.get('prerelease') or not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', tag):
        raise ValueError('Expected a published stable vMAJOR.MINOR.PATCH release')
    version = tag[1:]
    template_pkgrel = re.search(r'^pkgrel=([0-9]+(?:\.[0-9]+)*)$', template, re.M)[1]
    local_version = re.search(r'^pkgver=([0-9.]+)$', template, re.M)[1]
    versions = [(local_version, template_pkgrel)]
    current_pkgrel = None
    if current:
        match = re.fullmatch(r'([0-9]+\.[0-9]+\.[0-9]+)-([0-9]+(?:\.[0-9]+)*)', current['Version'])
        if not match:
            raise ValueError('Unexpected AUR version format')
        current_pkgrel = match[2]
        versions.append((match[1], current_pkgrel))
    pkgrel = template_pkgrel if local_version != version else '1'
    for previous, revision in versions:
        if tuple(map(int, previous.split('.'))) > tuple(map(int, version.split('.'))):
            raise ValueError('Refusing to downgrade the package')
        if previous == version:
            pkgrel = max_pkgrel(pkgrel, revision)
    result = re.sub(r'^pkgver=.*$', f'pkgver={version}', template, flags=re.M)
    result = re.sub(r'^pkgrel=.*$', f'pkgrel={pkgrel}', result, flags=re.M)
    checksums = {}
    for arch, debarch in [('x86_64', 'amd64'), ('aarch64', 'arm64')]:
        name = f'AstrBot_{version}_linux_{debarch}.deb'
        assets = [a for a in release['assets'] if a['name'] == name]
        if len(assets) != 1 or not re.fullmatch(r'sha256:[0-9a-f]{64}', assets[0].get('digest') or ''):
            raise ValueError(f'Missing asset or SHA256 digest: {name}')
        checksum = assets[0]['digest'].split(':')[1]
        checksums[arch] = checksum
        result, count = re.subn(rf'^sha256sums_{arch}=.*$', f"sha256sums_{arch}=('{checksum}')", result, flags=re.M)
        if count != 1:
            raise ValueError(f'Missing checksum field for {arch}')
    if current and current_pkgrel and current.get('Checksums'):
        if any(current['Checksums'].get(arch) != checksum for arch, checksum in checksums.items()):
            pkgrel = max_pkgrel(pkgrel, current_pkgrel)
            # Numeric pkgrels use their next integer revision after a replacement.
            parts = list(pkgrel_parts(pkgrel))
            parts[-1] += 1
            result = re.sub(r'^pkgrel=.*$', f"pkgrel={'.'.join(map(str, parts))}", result, flags=re.M)
    return result


def read_json(url, token=None):
    headers = {'User-Agent': 'astrbot-aur-update'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return json.load(response)


if __name__ == '__main__':
    release = read_json('https://api.github.com/repos/AstrBotDevs/AstrBot-desktop/releases/latest', os.environ.get('GH_TOKEN'))
    aur = read_json('https://aur.archlinux.org/rpc/v5/info?arg[]=astrbot-desktop-bin')
    if aur.get('type') != 'multiinfo' or len(aur['results']) > 1:
        raise ValueError('Unexpected AUR metadata response')
    current = next(iter(aur['results']), None)
    if current:
        try:
            with urllib.request.urlopen(
                'https://aur.archlinux.org/cgit/aur.git/plain/.SRCINFO?h=astrbot-desktop-bin',
                timeout=60,
            ) as response:
                srcinfo = response.read().decode()
            current['Checksums'] = {
                arch: next((line.split('=', 1)[1].strip() for line in srcinfo.splitlines()
                            if line.strip().startswith(f'sha256sums_{arch} = ')), None)
                for arch in ('x86_64', 'aarch64')
            }
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
    package = Path(__file__).resolve().parents[1] / 'astrbot-desktop-bin/PKGBUILD'
    package.write_text(update(package.read_text(), release, current))
    print(f"Prepared astrbot-desktop-bin for {release['tag_name']}")
