import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/pixelterm-c.sh'


class PixelTermUpdateTests(unittest.TestCase):
    def run_update(self, current_rel, *, rebuild=False, latest_version='1.8.2'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bin_dir = root / 'bin'
            package_dir = root / 'pixelterm-c'
            scripts_dir = root / 'scripts'
            bin_dir.mkdir()
            package_dir.mkdir()
            scripts_dir.mkdir()
            source_archive = root / 'source.tar.gz'
            (package_dir / 'PKGBUILD').write_text(
                f'pkgver=1.8.2\npkgrel=1\nsha256sums=(\'old\')\n'
            )
            script = SCRIPT.read_text().replace('/tmp/pixelterm-c.tar.gz', str(source_archive))
            (scripts_dir / SCRIPT.name).write_text(script)

            commands = {
                'git': '''#!/bin/bash
set -eu
[[ $1 == clone ]]
destination=${@: -1}
mkdir -p "$destination"
printf 'pkgver = %s\\npkgrel = %s\\n' "$CURRENT_VERSION" "$CURRENT_RELEASE" > "$destination/.SRCINFO"
''',
                'curl': '''#!/bin/bash
set -eu
if [[ " $* " == *"/archive/refs/tags/"* ]]; then
  output=
  while (($#)); do
    if [[ $1 == -o ]]; then output=$2; shift 2; else shift; fi
  done
  printf 'test source archive\\n' > "$output"
fi
''',
                'jq': '''#!/bin/bash
printf 'v%s\\n' "$LATEST_VERSION"
''',
                'vercmp': '''#!/bin/bash
if [[ $1 == "$2" ]]; then echo 0; else echo 1; fi
''',
                'makepkg': '''#!/bin/bash
set -eu
pkgver=$(/usr/bin/sed -n 's/^pkgver=//p' PKGBUILD)
pkgrel=$(/usr/bin/sed -n 's/^pkgrel=//p' PKGBUILD)
printf 'pkgver = %s\\npkgrel = %s\\n' "$pkgver" "$pkgrel"
''',
                'sed': '''#!/bin/bash
set -eu
if [[ ${1:-} == -i ]]; then
  shift
  if [[ $(uname -s) == Darwin ]]; then
    exec /usr/bin/sed -i '' "$@"
  fi
  exec /usr/bin/sed -i "$@"
fi
exec /usr/bin/sed "$@"
''',
            }
            for name, content in commands.items():
                executable = bin_dir / name
                executable.write_text(content)
                executable.chmod(0o755)

            environment = {
                **os.environ,
                'PATH': f'{bin_dir}{os.pathsep}{os.environ["PATH"]}',
                'CURRENT_VERSION': '1.8.2',
                'CURRENT_RELEASE': str(current_rel),
                'LATEST_VERSION': latest_version,
                'REBUILD_CURRENT': 'true' if rebuild else 'false',
            }
            result = subprocess.run(
                ['bash', str(scripts_dir / SCRIPT.name)],
                cwd=package_dir,
                env=environment,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            package = (package_dir / 'PKGBUILD').read_text()
            metadata = (package_dir / '.SRCINFO').read_text()
            return package, metadata

    def test_requested_rebuild_increments_current_pkgrel(self):
        cases = (
            ('1', '2'),
            ('2', '3'),
            ('8', '9'),
            ('9', '10'),
            ('0008', '9'),
            ('0009', '10'),
            ('9223372036854775808', '9223372036854775809'),
        )
        for current_rel, expected in cases:
            with self.subTest(current_rel=current_rel):
                package, metadata = self.run_update(current_rel, rebuild=True)
                self.assertIn(f'pkgrel={expected}', package)
                self.assertIn(f'pkgrel = {expected}', metadata)

    def test_regular_same_version_update_preserves_pkgrel(self):
        package, metadata = self.run_update('8')
        self.assertIn('pkgrel=8', package)
        self.assertIn('pkgrel = 8', metadata)

    def test_new_upstream_version_starts_at_pkgrel_one(self):
        package, metadata = self.run_update('8', rebuild=True, latest_version='1.9.0')
        self.assertIn('pkgver=1.9.0', package)
        self.assertIn('pkgrel=1', package)
        self.assertIn('pkgrel = 1', metadata)


if __name__ == '__main__':
    unittest.main()
