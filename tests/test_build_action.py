from pathlib import Path
import subprocess
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

    def test_deprecated_input_is_declared_and_forwarded(self):
        action = (ROOT / 'build-aur-action/action.yml').read_text()
        self.assertIn('\n  rebuild_current:\n', action)
        self.assertIn('    - ${{ inputs.rebuild_current }}',
                      action.split('\n  args:\n', 1)[1])


if __name__ == '__main__':
    unittest.main()
