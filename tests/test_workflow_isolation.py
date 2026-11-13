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
        cases = [('v1.9.0', '0', '', '0', 'v1.9.0'),
                 ('$(id)', '0', '', '0', None), ('v1.9.0\ntag=bad', '0', '', '0', None),
                 ('', '1', 'https://github.com/zouyonghe/PixelTerm-C/releases/tag/v1.9.1', '0', 'v1.9.1'),
                 ('bad', '0', 'https://github.com/zouyonghe/PixelTerm-C/releases/tag/v1.9.2', '0', 'v1.9.2'),
                 ('', '1', 'https://evil.invalid/releases/tag/v1.9.1', '0', None),
                 ('', '1', 'https://github.com/zouyonghe/PixelTerm-C/releases/tag/v1.9.1', '22', None)]
        for tag, api_status, url, curl_status, expected in cases:
            with self.subTest(tag=tag, url=url, api_status=api_status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                gh = root / 'gh'
                gh.write_text('#!/bin/sh\ntest "$GH_TOKEN" = request-only || exit 99\nprintf "%s\\n" "$TEST_TAG"\nexit "$API_STATUS"\n')
                gh.chmod(0o755)
                curl = root / 'curl'
                curl.write_text('#!/bin/sh\ntest -z "${GH_TOKEN:-}${GITHUB_TOKEN:-}" || exit 99\nprintf "%s" "$FALLBACK_URL"\nexit "$CURL_STATUS"\n')
                curl.chmod(0o755)
                output = root / 'output'
                result = subprocess.run(['bash', '-euo', 'pipefail', '-c', script],
                                        env={**os.environ, 'PATH': f'{root}:{os.environ["PATH"]}',
                                             'GH_TOKEN': 'request-only', 'TEST_TAG': tag,
                                             'API_STATUS': api_status, 'FALLBACK_URL': url,
                                             'CURL_STATUS': curl_status,
                                             'GITHUB_OUTPUT': str(output)}, capture_output=True, text=True)
                if expected:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(output.read_text(), f'tag={expected}\n')
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())
                self.assertNotIn('request-only', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
