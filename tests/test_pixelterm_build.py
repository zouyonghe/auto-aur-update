import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/build-pixelterm.sh'


class PixelTermBuildIsolationTests(unittest.TestCase):
    def test_hostile_build_cannot_modify_prepared_package_or_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'prepared'
            package.mkdir()
            original = '# rebuild-deps: libmupdf=1 ffmpeg=2\n'
            (package / 'PKGBUILD').write_text(original)
            (package / '.aur-revision').write_text('trusted-commit\n')
            tools = root / 'tools'
            tools.mkdir()
            for name, text in {
                'sudo': '#!/bin/sh\nexec "$@"\n',
                'pacman': '#!/bin/sh\nif [ "$1" = -Q ]; then printf "libmupdf 1\\nffmpeg 2\\n"; fi\n',
                'makepkg': '''#!/bin/sh
set -eu
test -z "${GH_TOKEN:-}${GITHUB_TOKEN:-}"
test "$1" = --config
test -f "$2"
grep -q -- '--connect-timeout 10 --max-time 180 --retry 2 --retry-delay 5 --retry-max-time 240' "$2"
shift 2
test "$*" = '--cleanbuild --syncdeps --check --noconfirm --force'
test ! -e .aur-revision
printf 'attacker-package' > PKGBUILD
printf 'attacker-revision' > .aur-revision
printf 'build-ran' > "$BUILD_LOG"
''',
            }.items():
                executable = tools / name
                executable.write_text(text)
                executable.chmod(0o755)
            result = subprocess.run(['bash', str(SCRIPT), str(package)],
                                    env={**os.environ, 'PATH': f'{tools}:{os.environ["PATH"]}',
                                         'GH_TOKEN': 'must-not-leak', 'GITHUB_TOKEN': 'must-not-leak',
                                         'BUILD_LOG': str(root / 'calls'), 'TMPDIR': str(root)},
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((root / 'calls').read_text(), 'build-ran')
            self.assertEqual((package / 'PKGBUILD').read_text(), original)
            self.assertEqual((package / '.aur-revision').read_text(), 'trusted-commit\n')
            self.assertEqual(sorted(path.name for path in root.iterdir()), ['calls', 'prepared', 'tools'])


if __name__ == '__main__':
    unittest.main()
