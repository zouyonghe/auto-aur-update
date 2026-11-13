import os
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/pixelterm-c.sh'
DEPENDENCIES = 'libmupdf=1.28.6-1 ffmpeg=2:9.0.2-3'


class PixelTermUpdateTests(unittest.TestCase):
    def field(self, text, name):
        matches = re.findall(rf'^\s*{re.escape(name)}\s*=\s*(\S+)\s*$', text, re.MULTILINE)
        self.assertEqual(len(matches), 1, text)
        return matches[0]

    def run_update(self, current_rel, *, current_version='1.8.2',
                   template_version='1.8.2', template_rel='1', template_indent='',
                   latest_version='1.8.2', expect_success=True,
                   published_deps=DEPENDENCIES, dependencies=DEPENDENCIES,
                   query_status='0', build_status='0', identical=False, token='',
                   release_tag='', published_marker=None, cmp_status=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bin_dir = root / 'bin'
            package_dir = root / 'pixelterm-c'
            scripts_dir = root / 'scripts'
            bin_dir.mkdir()
            package_dir.mkdir()
            scripts_dir.mkdir()
            checksum = hashlib.sha256(b'test source archive\n').hexdigest()
            (package_dir / 'PKGBUILD').write_text(
                f'pkgver={template_version}\n{template_indent}pkgrel={template_rel}\n'
                f"sha256sums=('{checksum if identical else 'old'}')\n"
            )
            (scripts_dir / SCRIPT.name).write_text(SCRIPT.read_text())

            commands = {
                'git': '''#!/bin/bash
set -eu
if [[ $1 == -C ]]; then printf '%040d\\n' 1; exit; fi
[[ $1 == clone ]]
destination=${@: -1}
mkdir -p "$destination"
printf 'pkgver = %s\\npkgrel = %s\\n' "$CURRENT_VERSION" "$CURRENT_RELEASE" > "$destination/.SRCINFO"
printf "pkgver=%s\\npkgrel=%s\\nsha256sums=('%s')\\n" "$CURRENT_VERSION" "$CURRENT_RELEASE" "$SOURCE_CHECKSUM" > "$destination/PKGBUILD"
if [[ -n $PUBLISHED_MARKER ]]; then
  printf '%s\\n' "$PUBLISHED_MARKER" >> "$destination/PKGBUILD"
elif [[ -n $PUBLISHED_DEPS ]]; then
  printf '# rebuild-deps: %s\\n' "$PUBLISHED_DEPS" >> "$destination/PKGBUILD"
fi
''',
                'curl': '''#!/bin/bash
set -eu
if [[ " $* " == *"/releases/latest"* ]]; then
  printf '%s\\n' "$@" > api-request
fi
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
test -z "${GH_TOKEN:-}${GITHUB_TOKEN:-}"
if [[ $1 != --printsrcinfo ]]; then
  printf '%s\\n' "$*" >> build-calls
  exit "$BUILD_STATUS"
fi
pkgver=$(/usr/bin/sed -n 's/^[[:space:]]*pkgver=//p' PKGBUILD)
pkgrel=$(/usr/bin/sed -n 's/^[[:space:]]*pkgrel=//p' PKGBUILD)
printf 'pkgver = %s\\npkgrel = %s\\n' "$pkgver" "$pkgrel"
''',
                'pacman': '''#!/bin/bash
set -eu
[[ "$*" == "-Sp --print-format %n=%v --nodeps libmupdf ffmpeg" ]]
printf '%s\\n' "$DEPENDENCIES" | tr ' ' '\\n'
exit "$QUERY_STATUS"
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
            if cmp_status is not None:
                commands['cmp'] = f'#!/bin/sh\nexit {cmp_status}\n'
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
                'PUBLISHED_DEPS': published_deps,
                'DEPENDENCIES': dependencies,
                'QUERY_STATUS': query_status,
                'BUILD_STATUS': build_status,
                'SOURCE_CHECKSUM': checksum,
                'GH_TOKEN': token,
                'GITHUB_TOKEN': token,
                'PIXELTERM_RELEASE_TAG': release_tag,
                'PUBLISHED_MARKER': published_marker or '',
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
            self.last_builds = ((package_dir / 'build-calls').read_text()
                                if (package_dir / 'build-calls').exists() else '')
            self.last_revision = ((package_dir / '.aur-revision').read_text()
                                  if (package_dir / '.aur-revision').exists() else '')
            self.last_api_request = ((package_dir / 'api-request').read_text()
                                     if (package_dir / 'api-request').exists() else '')
            self.last_output = result.stdout + result.stderr
            return package, metadata

    def test_inherited_tokens_do_not_reach_makepkg(self):
        self.run_update('8', token='test-workflow-token')
        self.assertNotIn('Authorization:', self.last_api_request)
        self.assertNotIn('test-workflow-token', self.last_output)

    def test_pre_resolved_release_tag_skips_api_request(self):
        package, _ = self.run_update('8', release_tag='v1.9.0')
        self.assertEqual(self.field(package, 'pkgver'), '1.9.0')
        self.assertEqual(self.last_api_request, '')

    def test_invalid_pre_resolved_release_is_rejected(self):
        self.run_update('8', release_tag='$(id)', expect_success=False)

    def test_local_update_without_token_omits_authentication(self):
        self.run_update('8')
        self.assertNotIn('Authorization:', self.last_api_request)

    def test_each_dependency_change_increments_release(self):
        for previous in ('libmupdf=1.28.5-1 ffmpeg=2:9.0.2-3',
                         'libmupdf=1.28.6-1 ffmpeg=2:9.0.1-1'):
            with self.subTest(previous=previous):
                package, _ = self.run_update('8', published_deps=previous)
                self.assertEqual(self.field(package, 'pkgrel'), '9')
                self.assertIn('# rebuild-deps: ' + DEPENDENCIES, package)
                self.assertIn('--syncdeps', self.last_builds.split())
                self.assertIn('--cleanbuild', self.last_builds.split())
                self.assertIn('--check', self.last_builds.split())
                self.assertEqual(self.last_revision, '0' * 39 + '1\n')

    def test_legacy_package_gets_one_baseline_rebuild(self):
        package, _ = self.run_update('8', published_deps='')
        self.assertEqual(self.field(package, 'pkgrel'), '9')

    def test_dependency_change_preserves_higher_explicit_revision(self):
        package, _ = self.run_update('8', published_deps='', template_rel='12')
        self.assertEqual(self.field(package, 'pkgrel'), '12')

    def test_new_release_and_dependency_change_start_at_one(self):
        package, _ = self.run_update('8', published_deps='', latest_version='1.9.0')
        self.assertEqual(self.field(package, 'pkgrel'), '1')

    def test_identical_published_package_skips_build(self):
        package, _ = self.run_update('8', identical=True)
        self.assertEqual(self.field(package, 'pkgrel'), '8')
        self.assertEqual(self.last_builds, '')

    def test_comparison_errors_stop_instead_of_rebuilding(self):
        for status in (2, 127):
            with self.subTest(status=status):
                result, _, _ = self.run_update('8', cmp_status=status, expect_success=False)
                self.assertIn('Failed to compare PKGBUILD', result.stderr)

    def test_dependency_queries_fail_closed(self):
        for values in ({'query_status': '1'}, {'dependencies': ''},
                       {'dependencies': 'libmupdf=bad;command ffmpeg=1'},
                       {'dependencies': 'libmupdf=1'},
                       {'dependencies': DEPENDENCIES + ' extra=1'}):
            with self.subTest(values=values):
                result, _, _ = self.run_update('8', expect_success=False, **values)
                self.assertIn('dependency', result.stderr)

    def test_malformed_published_record_fails_closed(self):
        for record in ('garbage', ' ',
                       DEPENDENCIES + '\n# rebuild-deps: ' + DEPENDENCIES,
                       DEPENDENCIES + '\n# rebuild-deps:'):
            result, _, _ = self.run_update('8', published_deps=record, expect_success=False)
            self.assertIn('dependency', result.stderr)

    def test_failed_build_blocks_publication(self):
        self.run_update('8', published_deps='', build_status='1', expect_success=False)

    def test_noncanonical_markers_fail_closed(self):
        for marker in ('  # rebuild-deps: ' + DEPENDENCIES,
                       '\t# rebuild-deps: ' + DEPENDENCIES,
                       '#rebuild-deps: ' + DEPENDENCIES,
                       '## rebuild-deps: ' + DEPENDENCIES,
                       '# rebuild-deps = ' + DEPENDENCIES,
                       '# rebuild-deps ' + DEPENDENCIES,
                       '# rebuild-deps: ' + DEPENDENCIES + ' ',
                       '# rebuild-deps: ' + DEPENDENCIES + '\n  # rebuild-deps: bad'):
            with self.subTest(marker=marker):
                result, _, _ = self.run_update('8', published_marker=marker, expect_success=False)
                self.assertIn('dependency', result.stderr)

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
