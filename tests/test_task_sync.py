import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/task-sync.yml'


def task_sync_script(*, commit_only=False):
    """Execute the workflow's commit and publication steps, not a copied script."""
    publication = WORKFLOW.read_text().split('      - name: Commit refresh token changes\n', 1)[1]
    if commit_only:
        publication = publication.split('      - name:', 1)[0]
    blocks = re.findall(r'(?m)^        run: (?:\|\n((?:^          .*\n)+)|([^\n]+))', publication)
    return 'set -euo pipefail\n' + '\n'.join(
        textwrap.dedent(multiline) if multiline else singleline
        for multiline, singleline in blocks
    )


class TaskSyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.remote = self.root / 'remote.git'
        self.runner = self.root / 'runner'
        self.writer = self.root / 'writer'
        self.counter = self.root / 'push-count'
        self.real_git = shutil.which('git')
        self.environment = {
            **os.environ,
            'GIT_CONFIG_GLOBAL': os.devnull,
            'GIT_CONFIG_NOSYSTEM': '1',
        }
        self.git('init', '--bare', '--initial-branch=main', str(self.remote))
        seed = self.root / 'seed'
        self.git('clone', str(self.remote), str(seed))
        self.configure_identity(seed)
        (seed / 'time.log').write_text('original\n')
        (seed / 'unrelated.txt').write_text('original unrelated content\n')
        self.git('add', 'time.log', 'unrelated.txt', cwd=seed)
        self.git('commit', '-m', 'seed', cwd=seed)
        self.git('push', 'origin', 'main', cwd=seed)
        for checkout in (self.runner, self.writer):
            self.git('clone', str(self.remote), str(checkout))
            self.configure_identity(checkout)

        # Real repositories provide the races; the shim injects another writer
        # immediately before a push, after the workflow's last fetch.
        shim = self.root / 'bin'
        shim.mkdir()
        (shim / 'git').write_text('''#!/bin/bash
set -euo pipefail
if [[ ${1:-} == push ]]; then
  count=0
  [[ ! -f "$PUSH_COUNT" ]] || count=$(cat "$PUSH_COUNT")
  count=$((count + 1))
  printf '%s\\n' "$count" > "$PUSH_COUNT"
  if [[ $RACE_MODE == authentication-failure ]]; then
    echo 'fatal: Authentication failed' >&2
    exit 128
  fi
  if [[ $RACE_MODE == always || ($RACE_MODE == once && $count == 1) ||
        ($RACE_MODE == conflict && $count == 1) ]]; then
    if [[ $RACE_MODE == conflict ]]; then
      printf 'other timestamp\\n' > "$WRITER/time.log"
    else
      printf 'other update %s\\n' "$count" > "$WRITER/writer-$count.txt"
    fi
    "$REAL_GIT" -C "$WRITER" add .
    "$REAL_GIT" -C "$WRITER" commit -m "other writer $count" >/dev/null
    "$REAL_GIT" -C "$WRITER" push origin HEAD:main >/dev/null 2>&1
  fi
fi
exec "$REAL_GIT" "$@"
''')
        (shim / 'git').chmod(0o755)
        self.environment.update({
            'PATH': str(shim) + os.pathsep + os.environ['PATH'],
            'REAL_GIT': self.real_git,
            'PUSH_COUNT': str(self.counter),
            'WRITER': str(self.writer),
            'RACE_MODE': 'none',
        })

    def git(self, *arguments, cwd=None):
        return subprocess.run(
            [self.real_git, *arguments], cwd=cwd, env=self.environment,
            check=True, text=True, capture_output=True,
        ).stdout.strip()

    def configure_identity(self, checkout):
        self.git('config', 'user.email', 'test@example.org', cwd=checkout)
        self.git('config', 'user.name', 'Test', cwd=checkout)

    def run_sync(self, *, changed=True, race='none', commit_only=False):
        if changed:
            (self.runner / 'time.log').write_text('new timestamp\n')
        return subprocess.run(
            ['bash', '-c', task_sync_script(commit_only=commit_only)], cwd=self.runner,
            env={**self.environment, 'RACE_MODE': race}, text=True, capture_output=True,
        )

    def push_count(self):
        return int(self.counter.read_text()) if self.counter.exists() else 0

    def remote_file(self, path):
        return self.git('--git-dir', str(self.remote), 'show', f'main:{path}')

    def test_checkout_is_pinned_and_keeps_push_credentials(self):
        workflow = WORKFLOW.read_text()
        self.assertIn('actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09', workflow)
        self.assertNotIn('persist-credentials: false', workflow)

    def test_noop_does_not_create_a_commit(self):
        before = self.git('--git-dir', str(self.remote), 'rev-parse', 'main')
        result = self.run_sync(changed=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('No changes to commit', result.stdout)
        self.assertEqual(self.git('--git-dir', str(self.remote), 'rev-parse', 'main'), before)

    def test_commit_failure_stops_before_push(self):
        hook = self.runner / '.git/hooks/pre-commit'
        hook.write_text('#!/bin/sh\necho COMMIT_REJECTED >&2\nexit 1\n')
        hook.chmod(0o755)
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('COMMIT_REJECTED', result.stderr)
        self.assertNotIn('No changes to commit', result.stdout)
        self.assertEqual(self.push_count(), 0)
        self.assertEqual(self.remote_file('time.log'), 'original')

    def test_commit_excludes_unrelated_tracked_and_untracked_changes(self):
        (self.runner / 'unrelated.txt').write_text('unrelated local change\n')
        (self.runner / 'untracked.txt').write_text('untracked local content\n')
        # Test the commit step alone: a later rebase correctly rejects a dirty
        # tracked file, which is separate from deciding what gets committed.
        result = self.run_sync(commit_only=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.git('diff-tree', '--no-commit-id', '--name-only',
                                  '-r', 'HEAD', cwd=self.runner), 'time.log')
        self.assertEqual(self.git('diff', '--cached', '--name-only', cwd=self.runner), '')
        self.assertEqual(self.git('diff', '--name-only', cwd=self.runner), 'unrelated.txt')
        self.assertEqual(self.git('ls-files', '--others', '--exclude-standard',
                                  cwd=self.runner), 'untracked.txt')

    def test_push_race_rebases_and_preserves_both_writers(self):
        result = self.run_sync(race='once')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.push_count(), 2)
        self.assertEqual(self.remote_file('time.log'), 'new timestamp')
        self.assertEqual(self.remote_file('writer-1.txt'), 'other update 1')
        self.assertEqual(self.git('--git-dir', str(self.remote), 'rev-list', '--count', 'main'), '3')

    def test_push_races_stop_after_three_attempts_without_losing_local_commit(self):
        result = self.run_sync(race='always')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.push_count(), 3)
        self.assertEqual(self.remote_file('time.log'), 'original')
        self.assertEqual(self.remote_file('writer-3.txt'), 'other update 3')
        self.assertEqual(self.git('show', 'HEAD:time.log', cwd=self.runner), 'new timestamp')
        self.assertEqual(self.git('log', '-1', '--format=%s', cwd=self.runner), 'update new time.log')

    def test_remote_rejection_is_not_retried(self):
        hook = self.remote / 'hooks/pre-receive'
        hook.write_text('#!/bin/sh\necho ACCESS_DENIED >&2\nexit 1\n')
        hook.chmod(0o755)
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('ACCESS_DENIED', result.stdout + result.stderr)
        self.assertEqual(self.push_count(), 1)
        self.assertEqual(self.remote_file('time.log'), 'original')

    def test_authentication_failure_is_not_retried(self):
        result = self.run_sync(race='authentication-failure')
        self.assertEqual(result.returncode, 128, result.stdout + result.stderr)
        self.assertIn('Authentication failed', result.stdout + result.stderr)
        self.assertEqual(self.push_count(), 1)
        self.assertEqual(self.remote_file('time.log'), 'original')

    def test_fetch_failure_stops_before_push(self):
        self.git('remote', 'set-url', 'origin', str(self.root / 'missing.git'), cwd=self.runner)
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.push_count(), 0)
        self.assertEqual(self.git('show', 'HEAD:time.log', cwd=self.runner), 'new timestamp')

    def test_rebase_conflict_stops_without_retrying_or_discarding_local_commit(self):
        result = self.run_sync(race='conflict')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.push_count(), 1)
        self.assertIn('CONFLICT', result.stdout + result.stderr)
        self.assertEqual(self.remote_file('time.log'), 'other timestamp')
        self.assertEqual(self.git('show', 'ORIG_HEAD:time.log', cwd=self.runner), 'new timestamp')


if __name__ == '__main__':
    unittest.main()
