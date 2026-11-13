import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/retry-git.sh'


class GitRetryTests(unittest.TestCase):
    def run_git(self, clone, failures):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / 'tools'
            tools.mkdir()
            for name, content in {
                'timeout': 'test "$1 $2 $3" = "--signal=TERM --kill-after=5s 60s" || exit 99; shift 3; export TIMED_GIT=1; exec "$@"',
                'sleep': 'echo "$1" >> "$TEST_ROOT/backoff"',
                'git': '''test "${TIMED_GIT:-}" = 1 || exit 99
n=0; test ! -e "$TEST_ROOT/count" || n=$(cat "$TEST_ROOT/count")
n=$((n+1)); echo "$n" > "$TEST_ROOT/count"
if [ "$1" = clone ]; then
  for destination; do :; done
  test ! -e "$destination" || exit 99
  mkdir -p "$destination"; echo done > "$destination/data"
fi
if [ "$n" -le "$FAILURES" ]; then echo partial-output; exit 1; fi
echo validated-output''',
            }.items():
                target = tools / name
                target.write_text('#!/bin/sh\n' + content + '\n')
                target.chmod(0o755)
            args = ['clone', 'https://example.invalid/repo', str(root / 'destination')] if clone else ['ls-remote', '--tags', 'https://example.invalid/repo']
            result = subprocess.run(['bash', str(SCRIPT), *args], text=True, capture_output=True,
                                    env={**os.environ, 'PATH': f'{tools}:{os.environ["PATH"]}',
                                         'TEST_ROOT': str(root), 'FAILURES': str(failures), 'TMPDIR': str(root)})
            return result, int((root / 'count').read_text()), (root / 'destination/data').exists()

    def test_partial_clone_is_retried_in_clean_temporary_destination(self):
        result, count, exists = self.run_git(True, 2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(count, 3)
        self.assertTrue(exists)
        self.assertEqual(result.stdout, 'validated-output\n')

    def test_failed_tag_request_does_not_leak_partial_stdout(self):
        result, count, _ = self.run_git(False, 2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(count, 3)
        self.assertEqual(result.stdout, 'validated-output\n')

    def test_failed_clone_never_installs_partial_repository(self):
        result, count, exists = self.run_git(True, 9)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(count, 3)
        self.assertFalse(exists)
        self.assertEqual(result.stdout, '')
