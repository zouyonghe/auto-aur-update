import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SourceRevisionTests(unittest.TestCase):
    def test_current_main_matches_but_new_main_commit_blocks_publication(self):
        source = (ROOT / '.github/actions/deploy-aur/build.sh').read_text()
        function = 'verify_source_revision() {' + source.split('verify_source_revision() {', 1)[1].split('\nexpected_source_revision_file=', 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / 'remote.git'
            seed = root / 'seed'
            env = {**os.environ, 'GIT_AUTHOR_NAME': 'Test', 'GIT_COMMITTER_NAME': 'Test',
                   'GIT_AUTHOR_EMAIL': 'test@example.org', 'GIT_COMMITTER_EMAIL': 'test@example.org'}
            def git(*args):
                return subprocess.check_output(['git', *map(str, args)], env=env, text=True, stderr=subprocess.DEVNULL).strip()
            git('init', '--bare', '--initial-branch=main', remote)
            git('clone', remote, seed)
            git('-C', seed, 'commit', '--allow-empty', '-m', 'prepared')
            git('-C', seed, 'push', 'origin', 'main')
            revision = git('-C', seed, 'rev-parse', 'HEAD')
            for advanced in (False, True):
                if advanced:
                    git('-C', seed, 'commit', '--allow-empty', '-m', 'new packaging')
                    git('-C', seed, 'push', 'origin', 'main')
                result = subprocess.run(['bash', '-euo', 'pipefail', '-c', function + '\nverify_source_revision'],
                                        env={**env, 'source_repository': str(remote), 'expected_source_revision': revision},
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode == 0, not advanced, result.stderr)
