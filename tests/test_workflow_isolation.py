import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / '.github/workflows'


def workflow_step(filename, name):
    text = (WORKFLOWS / filename).read_text()
    step = text.split(f'      - name: {name}\n', 1)[1]
    return re.split(r'(?m)^      - ', step, maxsplit=1)[0]


class WorkflowIsolationTests(unittest.TestCase):
    def test_test_workspace_excludes_git_directories_and_credential_files(self):
        step = workflow_step('astrbot-desktop-bin.yml', 'Prepare isolated test workspace')
        script = textwrap.dedent(step.split('        run: |\n', 1)[1])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / 'checkout'
            checkout.mkdir()
            (checkout / '.git').mkdir()
            (checkout / '.git/config').write_text('dummy-checkout-credential')
            (checkout / 'nested').mkdir()
            (checkout / 'nested/.git').write_text('gitdir: /private/credentials')
            (checkout / 'test.py').write_text('test-source')
            environment = root / 'environment'
            subprocess.run(['bash', '-euo', 'pipefail', '-c', script], cwd=checkout,
                           env={**os.environ, 'RUNNER_TEMP': str(root), 'GITHUB_ENV': str(environment)},
                           check=True, capture_output=True, text=True)
            workspace = Path(environment.read_text().strip().removeprefix('TEST_WORKSPACE='))
            self.assertEqual((workspace / 'test.py').read_text(), 'test-source')
            self.assertFalse((workspace / '.git').exists())
            self.assertFalse((workspace / 'nested/.git').exists())
            self.assertEqual((checkout / '.git/config').read_text(), 'dummy-checkout-credential')

    def test_build_checkouts_do_not_persist_credentials(self):
        for filename in ('astrbot-desktop-bin.yml', 'build-astrbot-desktop-bin.yml', 'pixelterm-update.yml'):
            with self.subTest(filename=filename):
                blocks = re.findall(r'(?m)^      - uses: actions/checkout@[^\n]*\n((?:        .*\n)*)',
                                    (WORKFLOWS / filename).read_text())
                self.assertTrue(blocks)
                for block in blocks:
                    self.assertIn('persist-credentials: false', block)

    def test_release_request_exports_only_validated_public_tag(self):
        step = workflow_step('pixelterm-update.yml', 'Resolve PixelTerm release without exposing credentials to builds')
        script = textwrap.dedent(step.split('        run: |\n', 1)[1])
        prepare = workflow_step('pixelterm-update.yml', 'Prepare PixelTerm package')
        self.assertNotIn('GH_TOKEN:', prepare)
        self.assertIn('PIXELTERM_RELEASE_TAG:', prepare)
        for tag, success in (('v1.9.0', True), ('$(id)', False), ('v1.9.0\ntag=bad', False)):
            with self.subTest(tag=tag), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                gh = root / 'gh'
                gh.write_text('#!/bin/sh\ntest "$GH_TOKEN" = request-only || exit 99\nprintf "%s\\n" "$TEST_TAG"\n')
                gh.chmod(0o755)
                output = root / 'output'
                result = subprocess.run(['bash', '-euo', 'pipefail', '-c', script],
                                        env={**os.environ, 'PATH': f'{root}:{os.environ["PATH"]}',
                                             'GH_TOKEN': 'request-only', 'TEST_TAG': tag,
                                             'GITHUB_OUTPUT': str(output)}, capture_output=True, text=True)
                if success:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(output.read_text(), 'tag=v1.9.0\n')
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())
                self.assertNotIn('request-only', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
