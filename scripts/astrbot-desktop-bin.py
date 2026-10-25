#!/usr/bin/env python3
"""Update the trusted AstrBot template using stable GitHub release metadata."""
import json
import os
from pathlib import Path
import re
import argparse
import subprocess
import tempfile
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
    if current and current['Version'].rsplit('-', 1)[0] == version and current.get('Checksums'):
        if any(current['Checksums'].get(arch) != checksum for arch, checksum in checksums.items()):
            pkgrel = max_pkgrel(pkgrel, current_pkgrel)
            # Advance the final numeric revision component after a replacement.
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


def read_current():
    aur = read_json('https://aur.archlinux.org/rpc/v5/info?arg[]=astrbot-desktop-bin')
    if aur.get('type') != 'multiinfo' or len(aur['results']) > 1:
        raise ValueError('Unexpected AUR metadata response')
    current = next(iter(aur['results']), None)
    if not current:
        return None
    # Read metadata and revision from one Git snapshot, without sourcing PKGBUILD.
    with tempfile.TemporaryDirectory() as directory:
        subprocess.check_output(['git', 'clone', '--quiet', '--depth=1',
                                 'https://aur.archlinux.org/astrbot-desktop-bin.git', directory], timeout=60)
        revision = subprocess.check_output(['git', '-C', directory, 'rev-parse', 'HEAD'], text=True, timeout=30).strip()
        srcinfo = subprocess.check_output(['git', '-C', directory, 'show', 'HEAD:.SRCINFO'], text=True, timeout=30)
    def field(name):
        values = re.findall(rf'^\s*{name} = (.+)$', srcinfo, re.M)
        if len(values) != 1:
            raise ValueError(f'Missing or ambiguous AUR {name}')
        return values[0]
    if f"{field('pkgver')}-{field('pkgrel')}" != current['Version']:
        raise ValueError('AUR RPC and Git versions differ; retry later')
    current['Checksums'] = {arch: field(f'sha256sums_{arch}') for arch in ('x86_64', 'aarch64')}
    if not all(re.fullmatch(r'[0-9a-f]{64}', checksum) for checksum in current['Checksums'].values()):
        raise ValueError('Invalid AUR checksum metadata')
    current['Revision'] = revision
    return current


def verify_release(package, release):
    # A second update must not change the built version or either payload digest.
    if update(package, release, None) != package:
        raise ValueError('Stable release changed after build; rerun preparation')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    release = read_json('https://api.github.com/repos/AstrBotDevs/AstrBot-desktop/releases/latest', os.environ.get('GH_TOKEN'))
    package = Path(__file__).resolve().parents[1] / 'astrbot-desktop-bin/PKGBUILD'
    if args.verify:
        verify_release(package.read_text(), release)
    else:
        current = read_current()
        package.write_text(update(package.read_text(), release, current))
        package.with_name('aur-revision').write_text(current['Revision'] if current else 'absent')
    print(f"Validated astrbot-desktop-bin for {release['tag_name']}")
