import importlib.util
from pathlib import Path
import unittest
import re
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/astrbot-desktop-bin.py'


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), 'AstrBot updater is not implemented')
        spec = importlib.util.spec_from_file_location('astrbot_update', SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.template = (SCRIPT.parent.parent / 'astrbot-desktop-bin/PKGBUILD').read_text()
        self.release = {
            'tag_name': 'v4.30.0', 'draft': False, 'prerelease': False,
            'assets': [
                {'id': 430001, 'name': 'AstrBot_4.30.0_linux_amd64.deb', 'digest': 'sha256:' + 'a' * 64},
                {'id': 430002, 'name': 'AstrBot_4.30.0_linux_arm64.deb', 'digest': 'sha256:' + 'b' * 64},
            ],
        }

    def test_new_release_updates_both_architectures_and_resets_pkgrel(self):
        result = self.module.update(self.template, self.release, {'Version': '4.29.1-5'})
        self.assertIn('pkgver=4.30.0\npkgrel=1', result)
        self.assertIn("sha256sums_x86_64=('" + 'a' * 64 + "')", result)
        self.assertIn("sha256sums_aarch64=('" + 'b' * 64 + "')", result)
        self.assertIn('releases/assets/430001', result)
        self.assertIn('releases/assets/430002', result)

    def test_first_publication_needs_no_existing_aur_package(self):
        self.assertIn('pkgver=4.30.0\npkgrel=1', self.module.update(self.template, self.release, None))

    def test_same_release_preserves_higher_aur_pkgrel(self):
        result = self.module.update(self.template, self.release, {'Version': '4.30.0-7'})
        self.assertEqual([line for line in result.splitlines() if line.startswith('pkgrel=')], ['pkgrel=7'])

    def test_dotted_pkgrel_is_preserved(self):
        result = self.module.update(self.template, self.release, {'Version': '4.30.0-1.1'})
        self.assertIn('pkgrel=1.1', result)

    def test_changed_same_version_checksum_increments_pkgrel(self):
        current = {
            'Version': '4.30.0-7',
            'Checksums': {'x86_64': 'c' * 64, 'aarch64': 'b' * 64},
        }
        result = self.module.update(self.template, self.release, current)
        self.assertIn('pkgrel=8', result)

    def test_same_version_checksum_match_does_not_increment_pkgrel(self):
        current = {
            'Version': '4.30.0-7',
            'Checksums': {'x86_64': 'a' * 64, 'aarch64': 'b' * 64},
        }
        result = self.module.update(self.template, self.release, current)
        self.assertIn('pkgrel=7', result)

    def test_bumped_template_pkgrel_survives_new_upstream_version(self):
        template = re.sub(r'pkgver=[^\n]+\npkgrel=1', 'pkgver=4.29.1\npkgrel=3', self.template)
        result = self.module.update(template, self.release, {'Version': '4.29.1-1'})
        self.assertIn('pkgrel=3', result)

    def test_rejects_downgrade(self):
        with self.assertRaises(ValueError):
            self.module.update(self.template, self.release, {'Version': '4.31.0-1'})

    def test_new_version_does_not_inherit_old_checksum_revision(self):
        current = {'Version': '4.29.1-7',
                   'Checksums': {'x86_64': 'c' * 64, 'aarch64': 'd' * 64}}
        result = self.module.update(self.template, self.release, current)
        self.assertIn('pkgver=4.30.0\npkgrel=1', result)

    def test_existing_package_requires_srcinfo(self):
        with mock.patch.object(self.module, 'read_json', return_value={
                'type': 'multiinfo', 'results': [{'Version': '4.29.1-1'}]}), \
                mock.patch.object(self.module.subprocess, 'check_output', return_value=''), \
                self.assertRaises(ValueError):
            self.module.read_current()

    def test_verify_rejects_newer_stable_release(self):
        with self.assertRaises(ValueError):
            self.module.verify_release(self.template, self.release)

    def test_verify_rejects_replaced_release_asset(self):
        built = self.module.update(self.template, self.release, None)
        self.release['assets'][0]['digest'] = 'sha256:' + 'c' * 64
        with self.assertRaises(ValueError):
            self.module.verify_release(built, self.release)

    def test_replaced_release_asset_id_invalidates_prepared_package(self):
        built = self.module.update(self.template, self.release, None)
        self.release['assets'][0]['id'] += 1
        self.assertRaises(ValueError, self.module.verify_release, built, self.release)

    def test_verify_accepts_built_release(self):
        built = self.module.update(self.template, self.release, None)
        self.module.verify_release(built, self.release)

    def test_verify_preserves_prepared_revisions(self):
        built = self.module.update(self.template, self.release, None)
        for revision in ('7', '1.1'):
            with self.subTest(revision=revision):
                self.module.verify_release(built.replace('pkgrel=1\n', f'pkgrel={revision}\n'), self.release)

    def test_update_preserves_existing_aur_epoch(self):
        result = self.module.update(self.template, self.release, {'Version': '2:4.30.0-7'})
        self.assertIn('epoch=2', result.splitlines())
        self.assertIn('pkgrel=7', result.splitlines())

    def test_explicit_epoch_upgrade_allows_lower_upstream_version(self):
        template = 'epoch=3\n' + self.template
        result = self.module.update(template, self.release, {'Version': '2:5.0.0-9'})
        self.assertIn('epoch=3', result.splitlines())
        self.assertIn('pkgver=4.30.0', result.splitlines())

    def test_read_current_accepts_epoch_in_rpc(self):
        srcinfo = 'pkgver = 4.29.1\npkgrel = 1\nepoch = 2\n'
        srcinfo += 'sha256sums_x86_64 = ' + 'a' * 64 + '\nsha256sums_aarch64 = ' + 'b' * 64 + '\n'
        with mock.patch.object(self.module, 'read_json', return_value={
                'type': 'multiinfo', 'results': [{'Version': '2:4.29.1-1'}]}), \
                mock.patch.object(self.module.subprocess, 'check_output', side_effect=['', 'f' * 40, srcinfo]):
            self.assertEqual(self.module.read_current()['Version'], '2:4.29.1-1')

    def test_rejects_missing_asset_invalid_checksum_and_nonstable_release(self):
        for change in ('asset', 'checksum', 'prerelease', 'tag', 'draft'):
            with self.subTest(change=change):
                release = {**self.release, 'assets': [dict(x) for x in self.release['assets']]}
                if change == 'asset':
                    release['assets'].pop()
                elif change == 'checksum':
                    release['assets'][0]['digest'] = None
                elif change == 'tag':
                    release['tag_name'] = 'nightly'
                else:
                    release[change] = True
                with self.assertRaises(ValueError):
                    self.module.update(self.template, release, None)


if __name__ == '__main__':
    unittest.main()
