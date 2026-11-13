# AUR publishing CI failure fixes

## Evidence

Reviewed the latest 30 runs (2026-11-04 through 2026-11-13). All 19 failed
PixelTerm/AstrBot runs reached shared deployment and failed with
`/build.sh: line 152: cmp: command not found`, followed by the misleading
`Changed package requires a strictly higher pkgrel` message. The deploy image
installs neither diffutils nor base-devel. Tests ran on a fuller host, hiding
the missing runtime dependency. Example runs: 43404883858 and 43418100631.

PixelTerm run 43404883858 also received an unauthenticated GitHub API 403;
its existing fallback succeeded, so this was not the terminal failure.
Node 20 deprecation warnings are non-blocking and out of this focused fix.

## Plan

1. Exercise identical-package deployment and cmp execution errors in regression
   tests. Distinguish real content differences from comparison tool failures.
2. Install diffutils explicitly in the deployment image and verify cmp while
   building it. Add a credential-free PR job building/testing the actual image.
3. Authenticate PixelTerm release API requests in an isolated workflow step.
   Pass only the validated public tag across the builder login; clear any
   inherited tokens before updater/build execution. Retain public local queries.
4. Run full unittest/shell checks and rootless container smoke tests. Review the
   complete diff, commit the automatic-rebuild and CI fixes, and open a PR.
   Do not merge or publish AUR packages.

Use this repository's Bash/Python checks, not the Warp-specific Rust presubmit
commands referenced by the generic CI/PR skills.

## Verification and review

- Reproduced missing cmp using the original deployment image built locally.
  Rootless Podman needed host networking because this machine's proxy listens
  on loopback; this is a local verification setting, not a CI change.
- Fixed image built successfully; equal/different-file smoke checks passed.
  The initial PR's 87 unit tests passed on the host and inside the deploy image.
- Initial builder-token forwarding was removed during review: only the public
  release tag now crosses the login boundary. PR checkouts disable persisted
  credentials, and container tests receive a copy without Git metadata.
- Reviewed version precedence, migration/idempotence, invalid input rejection,
  build failure propagation, AUR commit guards, credential scope, and PR-only
  image validation. Existing same-revision content-change guards remain intact.
- ShellCheck passes the updater. Pre-existing entrypoint unused-pkgdir and
  deploy-asset globbing warnings remain outside this change. Workflow YAML and
  embedded Bash syntax were checked; Node action version migration is deferred.
- No AUR publish, merge, ARM execution, or system package replacement performed.

## Review follow-up verification

- 95 tests pass on the host and inside the credential-free workspace mounted by
  the exact updated PR container validation block.
- The workflow workspace-copy test plants dummy credentials in `.git/config`
  and a nested `.git` worktree file, then verifies neither reaches the copy.
- Release-query tests validate public tag output and reject malformed/multiline
  tags. Entrypoint and makepkg probes reject inherited GH_TOKEN/GITHUB_TOKEN.
- Mutation probes remove --help, --cleanbuild, --check, or token clearing from
  temporary copies; the corresponding regression tests fail for every mutation.
- A real makepkg probe with BUILDENV=!check skips a deliberately failing check
  without --check, but invokes it and exits 4 with --check. No package is installed.
- Comparison errors (2/127) and noncanonical/duplicate dependency markers stop
  the updater. Reproduction commands and historical test-count stages are
  documented in the implementation plan instead of machine-local log paths.

## Build-input and release-fallback follow-up

- Reconcile tracked dependencies against the entrypoint's database snapshot,
  record installed versions with pacman -Q, then recheck them after building.
  Failed reconciliation/query or version drift prevents publication. A remote
  repository change alone does not refresh pacman's local sync database; the
  underlying correctness issue is using desired rather than installed versions,
  including dependencies absent from a fresh preparation container.
- Remove all template marker-like comments before appending one canonical record.
  Published malformed baselines still fail closed rather than being normalized.
- Capture the version probe separately and reject a nonzero exit even when stdout
  equals pkgver. Explicit comparison failure also returns before the help probe.
- The preparation image explicitly installs diffutils and checks cmp; PR validation
  now builds and smoke-tests that image as well as the deploy image.
- Failed/invalid authenticated API responses fall back to the public latest-release
  redirect, with credentials cleared, timeout bounds, and exact host/project/tag
  validation. Invalid URLs and failed fallback requests produce no release output.
- 101 tests pass on the host and isolated deploy-image workspace. Preparation-image
  build and real cmp checks passed. Temporary mutation probes catch reverting the
  installed query, template cleanup, and version-probe exit-status guard.
- An additional fresh-container run (before the build-job split) installed/
  reconciled dependencies and completed the updater's initial archive download
  and checksum. The log then printed `==> Making package: pixelterm-c 1.8.6-2`
  and `==> Retrieving sources...`: makepkg's separate source download ended with
  curl 56 (TLS unexpected EOF) before compilation. This run did not establish a fresh
  full PixelTerm build result. The real minimal makepkg probe did reject expected
  version text with exit 1 (makepkg status 4). No host packages were changed.

## Source-build deployment boundary

- Source code no longer executes in the preparation script/action. Preparation
  generates metadata and a build decision, then uploads the protected
  `pixelterm-prepared` artifact containing PKGBUILD and the observed AUR commit.
- A separate, credential-free build job downloads that artifact and invokes
  `scripts/build-pixelterm.sh`. The script builds only a temporary PKGBUILD copy,
  checks installed-version consistency, and deletes build outputs. The job
  uploads nothing. Its entire VM/container is disposable, including sudo access.
- Publication waits for successful preparation and a successful required build
  (or an explicit no-op), starts on a fresh runner, and downloads the original
  preparation artifact pinned by its numeric artifact ID, not a mutable name.
  Neither a writable copy nor an attacker-created replacement artifact
  from the source build can become a deployment input.
- Test checkout assertions now parse workflow YAML using PyYAML and require the
  actual boolean false; the required python-yaml tooling is installed in CI test
  images. The token-bearing fixture forces a changed package and asserts the
  build shim ran, not merely that the logs contained no token.
- The hostile-build test overwrites PKGBUILD and creates a forged AUR revision
  in its disposable build directory; the prepared package/snapshot remain intact.
  Workflow assertions verify no artifact upload or publishing credentials in the
  build job and that publication downloads the preparation artifact.
- 104 tests pass on the host and inside the rebuilt deploy image (including
  python-yaml). ShellCheck and workflow YAML/embedded Bash checks pass. Mutation
  probes replacing credential settings with comments and skipping the forced
  token-bearing build both fail the corresponding tests as intended.
