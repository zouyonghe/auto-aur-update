import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/pixelterm-c.sh'


class PixelTermUpdateTests(unittest.TestCase):
    def field(self, text, name):
        matches = re.findall(rf'^\s*{re.escape(name)}\s*=\s*(\S+)\s*$', text, re.MULTILINE)
        self.assertEqual(len(matches), 1, text)
        return matches[0]

    def run_update(self, current_rel, *, current_version='1.8.2',
                   template_version='1.8.2', template_rel='1', template_indent='',
                   latest_version='1.8.2', expect_success=True):
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
                f'pkgver={template_version}\n{template_indent}pkgrel={template_rel}\n'
                "sha256sums=('old')\n"
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
IFS=. read -ra left <<< "$1"
IFS=. read -ra right <<< "$2"
max=${#left[@]}
if (( ${#right[@]} > max )); then max=${#right[@]}; fi
for ((i = 0; i < max; i++)); do
  l=${left[i]:-0}
  r=${right[i]:-0}
  l=$((10#$l))
  r=$((10#$r))
  if (( l > r )); then echo 1; exit; fi
  if (( l < r )); then echo -1; exit; fi
done
echo 0
''',
                'makepkg': '''#!/bin/bash
set -eu
pkgver=$(/usr/bin/sed -n 's/^[[:space:]]*pkgver=//p' PKGBUILD)
pkgrel=$(/usr/bin/sed -n 's/^[[:space:]]*pkgrel=//p' PKGBUILD)
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
                'CURRENT_VERSION': current_version,
                'CURRENT_RELEASE': str(current_rel),
                'LATEST_VERSION': latest_version,
            }
            result = subprocess.run(
                ['bash', str(scripts_dir / SCRIPT.name)],
                cwd=package_dir,
                env=environment,
                text=True,
                capture_output=True,
            )
            if expect_success:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            else:
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                return result, None, None
            package = (package_dir / 'PKGBUILD').read_text()
            metadata = (package_dir / '.SRCINFO').read_text()
            return package, metadata

    def test_regular_same_version_update_preserves_pkgrel(self):
        package, metadata = self.run_update('8')
        self.assertEqual(self.field(package, 'pkgrel'), '8')
        self.assertEqual(self.field(metadata, 'pkgrel'), '8')

    def test_same_version_update_publishes_explicit_higher_template_pkgrel(self):
        package, metadata = self.run_update('2', template_rel='8')
        self.assertEqual(self.field(package, 'pkgrel'), '8')
        self.assertEqual(self.field(metadata, 'pkgrel'), '8')

    def test_same_version_update_does_not_lower_higher_aur_pkgrel(self):
        package, metadata = self.run_update('8', template_rel='3')
        self.assertEqual(self.field(package, 'pkgrel'), '8')
        self.assertEqual(self.field(metadata, 'pkgrel'), '8')

    def test_stale_template_pkgrel_is_ignored_for_new_upstream_version(self):
        package, metadata = self.run_update(
            '1', current_version='1.8.3', template_version='1.8.2',
            template_rel='2', latest_version='1.8.3')
        self.assertEqual(self.field(package, 'pkgrel'), '1')
        self.assertEqual(self.field(metadata, 'pkgrel'), '1')

    def test_indented_template_pkgrel_is_read(self):
        package, metadata = self.run_update('2', template_rel='8', template_indent='  ')
        self.assertEqual(self.field(package, 'pkgrel'), '8')
        self.assertEqual(self.field(metadata, 'pkgrel'), '8')

    def test_indented_lower_template_pkgrel_is_normalized_to_aur_revision(self):
        package, metadata = self.run_update(
            '8', template_rel='3', template_indent='  ')
        self.assertEqual(self.field(package, 'pkgrel'), '8')
        self.assertEqual(self.field(metadata, 'pkgrel'), '8')

    def test_new_upstream_version_starts_at_pkgrel_one(self):
        package, metadata = self.run_update('8', template_rel='12', latest_version='1.9.0')
        self.assertEqual(self.field(package, 'pkgver'), '1.9.0')
        self.assertEqual(self.field(package, 'pkgrel'), '1')
        self.assertEqual(self.field(metadata, 'pkgrel'), '1')

    def test_older_upstream_version_is_rejected(self):
        result, _, _ = self.run_update('8', latest_version='1.8.1', expect_success=False)
        self.assertIn('older than AUR version', result.stderr)


if __name__ == '__main__':
    unittest.main()
