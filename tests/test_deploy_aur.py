import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / '.github/actions/deploy-aur/build.sh'


class CloneTests(unittest.TestCase):
    def run_clone(self, *, empty=True, fail=False, force=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / 'remote.git'
            real_git = shutil.which('git')
            subprocess.run([real_git, 'init', '--bare', '--initial-branch=master', str(remote)],
                           check=True, capture_output=True)
            if not empty:
                seed = root / 'seed'
                subprocess.run([real_git, 'clone', str(remote), str(seed)], check=True, capture_output=True)
                subprocess.run([real_git, '-C', str(seed), '-c', 'user.name=Test',
                                '-c', 'user.email=test@example.org', 'commit', '--allow-empty',
                                '-m', 'existing history'], check=True, capture_output=True)
                subprocess.run([real_git, '-C', str(seed), 'push', 'origin', 'master'],
                               check=True, capture_output=True)
            shim = root / 'git'
            shim.write_text('''#!/bin/bash
set -eu
if [[ " $* " == *" clone "* ]]; then
  [[ " $* " == *" ssh://aur@aur.archlinux.org/test-package.git "* ]] || exit 65
  [[ $SIMULATE_FAILURE != true ]] || exit 128
  args=("$@")
  for i in "${!args[@]}"; do
    if [[ ${args[$i]} == ssh://* ]]; then args[$i]=$TEST_REMOTE; fi
  done
  exec "$REAL_GIT" "${args[@]}"
fi
exec "$REAL_GIT" "$@"
''')
            shim.chmod(0o755)
            block = SCRIPT.read_text().split("echo '::group::Cloning AUR package into /tmp/local-repo'", 1)[1]
            block = block.split("echo '::group::Copying files into /tmp/local-repo'", 1)[0]
            target = root / 'checkout'
            block = block.replace('/tmp/local-repo', str(target))
            env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'],
                   'REAL_GIT': real_git, 'TEST_REMOTE': str(remote),
                   'SIMULATE_FAILURE': str(fail).lower()}
            setup = '\n'.join(['set -euo pipefail', 'pkgname=test-package',
                               f'force_push={str(force).lower()}', block])
            result = subprocess.run(['bash', '-c', setup], env=env, text=True, capture_output=True)
            exists = target.exists()
            branch = subprocess.run([real_git, '-C', str(target), 'symbolic-ref', '--short', 'HEAD'],
                                    text=True, capture_output=True).stdout.strip() if exists else None
            return result, exists, branch

    def test_network_failure_aborts_without_initializing_repository(self):
        result, exists, _ = self.run_clone(fail=True, force=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(exists, result.stdout + result.stderr)

    def test_authenticated_empty_repository_supports_first_publication(self):
        result, exists, branch = self.run_clone()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(exists)
        self.assertEqual(branch, 'master')

    def test_first_publication_rejects_force_push(self):
        result, _, _ = self.run_clone(force=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('force', result.stderr.lower())

    def test_existing_history_remains_supported(self):
        result, exists, branch = self.run_clone(empty=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(exists)
        self.assertEqual(branch, 'master')


if __name__ == '__main__':
    unittest.main()
