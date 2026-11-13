from pathlib import Path
import subprocess
import tempfile
import unittest


PKGBUILD = Path(__file__).resolve().parents[1] / 'pixelterm-c/PKGBUILD'


class PixelTermPackageTests(unittest.TestCase):
    def run_check(self, binary):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'PixelTerm-C-test/bin'
            source.mkdir(parents=True)
            executable = source / 'pixelterm'
            executable.write_text('#!/bin/bash\n' + binary)
            executable.chmod(0o755)
            result = subprocess.run(
                ['bash', '-ec', 'source "$1"; srcdir=$2; pkgver=test; check',
                 'check-package', str(PKGBUILD), directory],
                text=True, capture_output=True,
            )
            arguments = source / 'arguments'
            self.last_arguments = arguments.read_text().splitlines() if arguments.exists() else []
            return result

    def test_runnable_binary_passes(self):
        result = self.run_check(
            'printf "%s\\n" "$@" >> "$(dirname "$0")/arguments"\n'
            'case "$1" in --version) echo test;; --help) exit 0;; *) exit 2;; esac\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.last_arguments, ['--version', '--help'])

    def test_failed_help_rejects_package(self):
        result = self.run_check('case "$1" in --version) echo test;; --help) exit 1;; esac\n')
        self.assertNotEqual(result.returncode, 0)

    def test_missing_shared_library_rejects_package(self):
        result = self.run_check(
            'echo "libmupdf.so.28.5: cannot open shared object file" >&2\nexit 127\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('libmupdf.so.28.5', result.stderr)

    def test_wrong_version_rejects_package(self):
        result = self.run_check('echo stale\n')
        self.assertNotEqual(result.returncode, 0)

    def test_expected_version_with_failed_exit_is_rejected(self):
        result = self.run_check('case "$1" in --version) echo test; exit 1;; --help) exit 0;; esac\n')
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
