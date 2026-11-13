from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / 'build-aur-action/entrypoint.sh'


class BuildActionMigrationTests(unittest.TestCase):
    def run_entrypoint(self, *extra_args, pkgname='pixelterm-c'):
        # Exercise input validation without running privileged container setup.
        validation = ENTRYPOINT.read_text().split('\nuseradd builder -m\n', 1)[0]
        return subprocess.run(
            ['bash', '-c', validation + '\nexit 91\n',
             'entrypoint.sh', 'pixelterm-c', pkgname, *extra_args],
            text=True, capture_output=True,
        )

    def run_full_entrypoint(self, *extra_args, pacman_status='0', release_tag=''):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / 'entrypoint.sh'
            sudoers = root / 'sudoers'
            script.write_text(ENTRYPOINT.read_text().replace('/etc/sudoers', str(sudoers)))
            script.chmod(0o755)
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            (root / 'scripts').mkdir()
            (root / 'scripts/retry-pacman.sh').write_text((ROOT / 'scripts/retry-pacman.sh').read_text())
            calls = root / 'calls'
            calls.mkdir()
            for command in ('useradd', 'chown', 'chmod', 'pacman-key', 'pacman'):
                shim = bin_dir / command
                shim.write_text(
                    '#!/bin/sh\n'
                    f'printf "%s\\n" "{command}:$*" >> "$CALLS"\n'
                    + ('exit "$PACMAN_STATUS"\n' if command == 'pacman' else '')
                )
                shim.chmod(0o755)
            for name, content in {'sudo': 'test "$1" = timeout || exit 99; exec "$@"',
                                  'sleep': 'exit 0'}.items():
                tool = bin_dir / name
                tool.write_text('#!/bin/sh\n' + content + '\n')
                tool.chmod(0o755)
            su = bin_dir / 'runuser'
            su.write_text(
                '#!/bin/sh\n'
                'test -z "${GH_TOKEN:-}${GITHUB_TOKEN:-}" || exit 77\n'
                'printf "tag:%s\\n" "${PIXELTERM_RELEASE_TAG:-}"\n'
                'printf "runuser:%s\\n" "$*" >> "$CALLS"\n'
            )
            su.chmod(0o755)
            result = subprocess.run(
                ['bash', str(script), 'pixelterm-c', 'pixelterm-c', *extra_args],
                cwd=root,
                env={**__import__('os').environ, 'PATH': f'{bin_dir}:{__import__("os").environ["PATH"]}',
                     'CALLS': str(calls / 'commands'), 'PACMAN_STATUS': pacman_status,
                     'GH_TOKEN': 'must-not-reach-updater', 'GITHUB_TOKEN': 'must-not-reach-updater',
                     'PIXELTERM_RELEASE_TAG': release_tag},
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
        self.assertEqual(calls.splitlines(), ['useradd:builder -m', 'chown:-R builder:builder .',
                                              'chmod:-R a+rw .', 'pacman-key:--init',
                                              'pacman:-Syu --noconfirm',
                                              'runuser:--user builder -- bash /github/workspace/scripts/pixelterm-c.sh'])
        self.assertIn('builder ALL=(ALL) NOPASSWD: ALL\n', sudoers)

    def test_failed_system_upgrade_stops_preparation(self):
        result, calls, _ = self.run_full_entrypoint('false', pacman_status='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('runuser:', calls)
        self.assertEqual(calls.splitlines().count('pacman:-Syu --noconfirm'), 3)

    def test_package_name_injection_is_rejected_before_setup(self):
        for name in ('pixelterm-c; id', '$(id)', '../pixelterm-c', 'pixelterm-c\nid', '-bad'):
            with self.subTest(name=name):
                result = self.run_entrypoint('false', pkgname=name)
                self.assertNotEqual(result.returncode, 91)
                self.assertIn('Invalid package name', result.stderr)

    def test_release_tag_survives_entrypoint_without_forwarding_tokens(self):
        result, _, _ = self.run_full_entrypoint('false', release_tag='v1.9.0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('tag:v1.9.0', result.stdout)

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
