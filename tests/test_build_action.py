from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / 'build-aur-action/entrypoint.sh'


class BuildActionMigrationTests(unittest.TestCase):
    def run_entrypoint(self, *extra_args):
        # Exercise input validation without running privileged container setup.
        validation = ENTRYPOINT.read_text().split('\nuseradd builder -m\n', 1)[0]
        return subprocess.run(
            ['bash', '-c', validation + '\nexit 91\n',
             'entrypoint.sh', 'pixelterm-c', 'pixelterm-c', *extra_args],
            text=True, capture_output=True,
        )

    def run_full_entrypoint(self, *extra_args):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / 'entrypoint.sh'
            sudoers = root / 'sudoers'
            script.write_text(ENTRYPOINT.read_text().replace('/etc/sudoers', str(sudoers)))
            script.chmod(0o755)
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            calls = root / 'calls'
            calls.mkdir()
            for command in ('useradd', 'chown', 'chmod', 'pacman-key', 'pacman'):
                shim = bin_dir / command
                shim.write_text(
                    '#!/bin/sh\n'
                    f'printf "%s\\n" "{command}" >> "$CALLS"\n'
                )
                shim.chmod(0o755)
            su = bin_dir / 'su'
            su.write_text(
                '#!/bin/sh\n'
                'printf "su:%s\\n" "$*" >> "$CALLS"\n'
            )
            su.chmod(0o755)
            result = subprocess.run(
                ['bash', str(script), 'pixelterm-c', 'pixelterm-c', *extra_args],
                cwd=root,
                env={**__import__('os').environ, 'PATH': f'{bin_dir}:{__import__("os").environ["PATH"]}',
                     'CALLS': str(calls / 'commands')},
                text=True, capture_output=True,
            )
            return (result,
                    (calls / 'commands').read_text() if (calls / 'commands').exists() else '',
                    sudoers.read_text() if sudoers.exists() else '')

    def test_deprecated_rebuild_request_fails_with_migration_instructions(self):
        result = self.run_entrypoint('true')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual(result.returncode, 91)
        self.assertIn('rebuild_current is no longer supported', result.stderr)
        self.assertIn('pkgver', result.stderr)
        self.assertIn('pkgrel', result.stderr)

    def test_invalid_rebuild_input_is_rejected_before_setup(self):
        result = self.run_entrypoint('invalid')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual(result.returncode, 91)
        self.assertIn('rebuild_current must be true or false', result.stderr)

    def test_regular_calls_still_reach_container_setup(self):
        for extra_args in ((), ('false',)):
            with self.subTest(extra_args=extra_args):
                result = self.run_entrypoint(*extra_args)
                self.assertEqual(result.returncode, 91, result.stderr)

    def test_regular_call_runs_the_full_setup_after_validation(self):
        result, calls, sudoers = self.run_full_entrypoint('false')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(calls.splitlines(), ['useradd', 'chown', 'chmod', 'pacman-key', 'pacman',
                                              'su:- builder -c cd /github/workspace && bash scripts/pixelterm-c.sh'])
        self.assertIn('builder ALL=(ALL) NOPASSWD: ALL\n', sudoers)

    def test_deprecated_input_is_declared_and_forwarded(self):
        action = (ROOT / 'build-aur-action/action.yml').read_text()
        self.assertIn('\n  rebuild_current:\n', action)
        args = action.split('\n  args:\n', 1)[1].splitlines()
        self.assertEqual(args[:3], [
            '    - ${{ inputs.pkgdir }}',
            '    - ${{ inputs.pkgname }}',
            '    - ${{ inputs.rebuild_current }}',
        ])


if __name__ == '__main__':
    unittest.main()
