import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/retry-pacman.sh'


class PacmanRetryTests(unittest.TestCase):
    def run_retry(self, failures, failure_status='1'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in {
                'sudo': 'exec "$@"',
                'timeout': 'test "$1 $2 $3" = "--signal=TERM --kill-after=10s 180s" || exit 99; shift 3; exec "$@"',
                'sleep': 'echo "sleep:$1" >> "$LOG"',
                'pacman': '''n=0; test ! -f "$COUNT" || n=$(cat "$COUNT")
n=$((n+1)); echo "$n" > "$COUNT"
echo "pacman:$*" >> "$LOG"
if [ "$n" -le "$FAILURES" ]; then exit "$FAILURE_STATUS"; fi''',
            }.items():
                executable = root / name
                executable.write_text('#!/bin/sh\n' + content + '\n')
                executable.chmod(0o755)
            result = subprocess.run(['bash', str(SCRIPT), '-Su', '--needed', '--noconfirm', 'libmupdf', 'ffmpeg'],
                                    env={**os.environ, 'PATH': f'{root}:{os.environ["PATH"]}',
                                         'COUNT': str(root / 'count'), 'LOG': str(root / 'log'),
                                         'FAILURES': str(failures), 'FAILURE_STATUS': failure_status}, text=True, capture_output=True)
            return result, (root / 'log').read_text().splitlines() if (root / 'log').exists() else []

    def test_transient_failure_retries_with_bounded_backoff(self):
        result, calls = self.run_retry(2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([line for line in calls if line.startswith('sleep:')], ['sleep:5', 'sleep:10'])
        self.assertEqual(sum(line.startswith('pacman:') for line in calls), 3)

    def test_persistent_failure_stops_after_three_attempts(self):
        result, calls = self.run_retry(9)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sum(line.startswith('pacman:') for line in calls), 3)

    def test_success_does_not_retry(self):
        result, calls = self.run_retry(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ['pacman:-Su --needed --noconfirm libmupdf ffmpeg'])

    def test_forced_termination_does_not_start_another_transaction(self):
        for status in ('130', '137', '143'):
            with self.subTest(status=status):
                result, calls = self.run_retry(9, status)
                self.assertEqual(result.returncode, int(status))
                self.assertEqual(len(calls), 1)

    def test_timeout_retries_are_limited(self):
        result, calls = self.run_retry(9, '124')
        self.assertEqual(result.returncode, 124)
        self.assertEqual(sum(line.startswith('pacman:') for line in calls), 3)
