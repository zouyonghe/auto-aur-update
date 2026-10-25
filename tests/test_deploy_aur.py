import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / '.github/actions/deploy-aur/build.sh'


class CloneTests(unittest.TestCase):
    def run_clone(self, *, empty=True, fail=False, force=False, expected=None):
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
  if [[ $SIMULATE_FAILURE == true ]]; then
    echo 'SIMULATED_CLONE_TRANSPORT_FAILURE' >&2
    exit 128
  fi
  args=("$@")
  for i in "${!args[@]}"; do
    if [[ ${args[$i]} == ssh://* ]]; then args[$i]=$TEST_REMOTE; fi
  done
  exec "$REAL_GIT" "${args[@]}"
fi
echo 'POST_CLONE_GIT_COMMAND' >&2
exec "$REAL_GIT" "$@"
''')
            shim.chmod(0o755)
            block = SCRIPT.read_text().split("echo '::group::Cloning AUR package into /tmp/local-repo'", 1)[1]
            block = block.split("echo '::group::Copying files into /tmp/local-repo'", 1)[0]
            target = root / 'checkout'
            revision_file = root / 'revision'
            revision_file.write_text(expected or '')
            block = block.replace('/tmp/local-repo', str(target))
            env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'],
                   'REAL_GIT': real_git, 'TEST_REMOTE': str(remote),
                   'SIMULATE_FAILURE': str(fail).lower()}
            setup = '\n'.join(['set -euo pipefail', 'pkgname=test-package',
                               f"expected_revision_file='{revision_file if expected else ''}'",
                               f'force_push={str(force).lower()}', block])
            result = subprocess.run(['bash', '-c', setup], env=env, text=True, capture_output=True)
            exists = target.exists()
            branch = subprocess.run([real_git, '-C', str(target), 'symbolic-ref', '--short', 'HEAD'],
                                    text=True, capture_output=True).stdout.strip() if exists else None
            return result, exists, branch

    def test_network_failure_aborts_without_initializing_repository(self):
        result, exists, _ = self.run_clone(fail=True, force=True)
        self.assertEqual(result.returncode, 128)
        self.assertIn('SIMULATED_CLONE_TRANSPORT_FAILURE', result.stderr)
        self.assertNotIn('POST_CLONE_GIT_COMMAND', result.stderr)
        self.assertNotIn('First publication', result.stderr)
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

    def test_changed_aur_snapshot_aborts(self):
        result, _, _ = self.run_clone(empty=False, expected='0' * 40)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('AUR changed after preparation', result.stderr)

    def test_confirmed_absence_matches_empty_namespace(self):
        result, _, _ = self.run_clone(expected='absent')
        self.assertEqual(result.returncode, 0, result.stderr)


def section(start, end):
    return SCRIPT.read_text().split(start, 1)[1].split(end, 1)[0]


class DeploymentTests(unittest.TestCase):
    def test_unborn_head_commits_staged_files(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(['git', 'init', '--initial-branch=master', directory], check=True, capture_output=True)
            Path(directory, 'PKGBUILD').write_text('pkgname=test-package\n')
            block = section("echo '::group::Committing files to the repository'",
                            "echo '::group::Publishing the repository'")
            result = subprocess.run(['bash', '-c', '\n'.join([
                'set -euo pipefail', "assets=''", 'allow_empty_commits=false',
                'commit_message=initial', 'git add PKGBUILD',
                # Supply SRCINFO because the actual staging block includes it.
                'touch .SRCINFO', block])], cwd=directory, text=True, capture_output=True,
                env={**os.environ, 'GIT_AUTHOR_NAME': 'Test', 'GIT_COMMITTER_NAME': 'Test',
                     'GIT_AUTHOR_EMAIL': 'test@example.org', 'GIT_COMMITTER_EMAIL': 'test@example.org'})
            self.assertEqual(result.returncode, 0, result.stderr)
            committed = subprocess.check_output(['git', '-C', directory, 'show', 'HEAD:PKGBUILD'], text=True)
            self.assertEqual(committed, 'pkgname=test-package\n')

    def copy_package(self, existing, incoming, *, accepted=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clone = root / 'clone'
            clone.mkdir()
            (clone / 'PKGBUILD').write_text(existing)
            source = root / 'incoming'
            source.write_text(incoming)
            block = section("echo '::group::Copying files into /tmp/local-repo'",
                            'if [[ -n "$assets" ]]')
            block = block.replace('/tmp/local-repo', str(clone)).replace('/tmp/generated-PKGBUILD', str(root / 'generated'))
            result = subprocess.run(['bash', '-c', 'set -euo pipefail\npkgbuild=$1\n' + block,
                                     'bash', str(source)], text=True, capture_output=True)
            self.assertEqual((clone / 'PKGBUILD').read_text(), incoming if accepted else existing)
            return result

    def test_malicious_pkgrel_is_rejected_before_sed_or_vercmp(self):
        incoming = 'pkgver=4.29.1\npkgrel=1\n'
        for payload in ('99/e touch /tmp/not-allowed', '9; touch /tmp/not-allowed', '$(id)', '9\npkgrel=10'):
            with self.subTest(payload=payload):
                result = self.copy_package(f'pkgver=4.29.1\npkgrel={payload}\n', incoming)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Invalid pkgrel', result.stderr)

    def test_same_version_changed_content_requires_higher_revision(self):
        result = self.copy_package('pkgver=4.29.1\npkgrel=2\n# new AUR content\n',
                                   'pkgver=4.29.1\npkgrel=1\n# stale incoming content\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('strictly higher pkgrel', result.stderr)

    def test_higher_revision_can_publish_changed_packaging(self):
        result = self.copy_package('pkgver=4.29.1\npkgrel=2\n',
                                   'pkgver=4.29.1\npkgrel=3\n# reviewed change\n', accepted=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unpinned_ssh_host_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.ssh').mkdir()
            subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(root / 'rogue')], check=True)
            scan = root / 'ssh-keyscan'
            scan.write_text('#!/bin/sh\ncat "$HOME/rogue.pub"\n')
            scan.chmod(0o755)
            block = section("echo '::group::Adding aur.archlinux.org to known hosts'",
                            "echo '::group::Importing private key'")
            result = subprocess.run(['bash', '-c', 'set -euo pipefail\nssh_keyscan_types=ed25519\n' + block],
                                    text=True, capture_output=True,
                                    env={**os.environ, 'HOME': str(root), 'PATH': str(root) + os.pathsep + os.environ['PATH']})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Unrecognized AUR SSH host fingerprint', result.stderr)
            self.assertEqual((root / '.ssh/known_hosts').read_text(), '')


class FinalPackageTests(unittest.TestCase):
    def run_final_package(self, *, change='', bump=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {**os.environ, 'GIT_AUTHOR_NAME': 'Test', 'GIT_COMMITTER_NAME': 'Test',
                   'GIT_AUTHOR_EMAIL': 'test@example.org', 'GIT_COMMITTER_EMAIL': 'test@example.org'}
            def git(*args):
                return subprocess.check_output(['git', '-C', directory, *args], env=env, text=True)
            git('init', '--initial-branch=master')
            (root / 'PKGBUILD').write_text('pkgver=4.29.1\npkgrel=1\n')
            metadata = 'pkgbase = test-package\n\tpkgver = 4.29.1\n\tpkgrel = 1\n'
            (root / '.SRCINFO').write_text(metadata)
            (root / 'helper.sh').write_text('original asset')
            git('add', '.')
            git('commit', '-qm', 'initial')
            original = git('rev-parse', 'HEAD').strip()
            if change == 'asset':
                (root / 'helper.sh').write_text('changed asset')
            elif change == 'deleted_asset':
                (root / 'helper.sh').unlink()
            elif change == 'post_process':
                block = section("if [ -n \"$post_process\" ]; then",
                                "echo '::group::Generating .SRCINFO'")
                block = 'if [ -n \"$post_process\" ]; then' + block
                block = block.replace('/tmp/local-repo/', directory + '/')
                subprocess.run(['bash', '-c', block], cwd=directory, check=True,
                               env={**env, 'post_process': 'echo changed >> PKGBUILD'}, capture_output=True)
            if bump:
                (root / '.SRCINFO').write_text(metadata.replace('pkgrel = 1', 'pkgrel = 2'))
                (root / 'PKGBUILD').write_text('pkgver=4.29.1\npkgrel=2\n')
            block = section("echo '::group::Committing files to the repository'",
                            "echo '::group::Publishing the repository'")
            result = subprocess.run(['bash', '-c', 'set -euo pipefail\nassets=helper.sh\nallow_empty_commits=false\ncommit_message=update\n' + block],
                                    cwd=directory, env=env, text=True, capture_output=True)
            return result, original == git('rev-parse', 'HEAD').strip()

    def test_final_changes_require_version_bump(self):
        for change in ('asset', 'deleted_asset', 'post_process'):
            with self.subTest(change=change):
                result, unchanged = self.run_final_package(change=change)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(unchanged)
                self.assertIn('strictly higher', result.stderr)

    def test_final_asset_change_with_bump_is_committed(self):
        result, unchanged = self.run_final_package(change='asset', bump=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(unchanged)

    def test_identical_package_does_not_need_bump(self):
        result, unchanged = self.run_final_package()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(unchanged)


if __name__ == '__main__':
    unittest.main()
