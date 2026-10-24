#!/usr/bin/env python3
"""Update the trusted AstrBot template using stable GitHub release metadata."""
import json
import os
from pathlib import Path
import re
import urllib.request


def update(template, release, current):
    tag = release.get('tag_name', '')
    if release.get('draft') or release.get('prerelease') or not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', tag):
        raise ValueError('Expected a published stable vMAJOR.MINOR.PATCH release')
    version = tag[1:]
    pkgrel = int(re.search(r'^pkgrel=([0-9]+)$', template, re.M)[1])
    local_version = re.search(r'^pkgver=([0-9.]+)$', template, re.M)[1]
    versions = [(local_version, pkgrel)]
    if current:
        match = re.fullmatch(r'([0-9]+\.[0-9]+\.[0-9]+)-([0-9]+)', current['Version'])
        if not match:
            raise ValueError('Unexpected AUR version format')
        versions.append((match[1], int(match[2])))
    pkgrel = 1
    for previous, revision in versions:
        if tuple(map(int, previous.split('.'))) > tuple(map(int, version.split('.'))):
            raise ValueError('Refusing to downgrade the package')
        if previous == version:
            pkgrel = max(pkgrel, revision)
    result = re.sub(r'^pkgver=.*$', f'pkgver={version}', template, flags=re.M)
    result = re.sub(r'^pkgrel=.*$', f'pkgrel={pkgrel}', result, flags=re.M)
    for arch, debarch in [('x86_64', 'amd64'), ('aarch64', 'arm64')]:
        name = f'AstrBot_{version}_linux_{debarch}.deb'
        assets = [a for a in release['assets'] if a['name'] == name]
        if len(assets) != 1 or not re.fullmatch(r'sha256:[0-9a-f]{64}', assets[0].get('digest') or ''):
            raise ValueError(f'Missing asset or SHA256 digest: {name}')
        checksum = assets[0]['digest'].split(':')[1]
        result, count = re.subn(rf'^sha256sums_{arch}=.*$', f"sha256sums_{arch}=('{checksum}')", result, flags=re.M)
        if count != 1:
            raise ValueError(f'Missing checksum field for {arch}')
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
    package = Path(__file__).resolve().parents[1] / 'astrbot-desktop-bin/PKGBUILD'
    package.write_text(update(package.read_text(), release, next(iter(aur['results']), None)))
    print(f"Prepared astrbot-desktop-bin for {release['tag_name']}")
