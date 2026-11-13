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
3. Authenticate PixelTerm release API requests with the workflow token, preserve
   that variable across the builder login, and retain unauthenticated local use
   and existing fallback paths. Never print the token.
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
  All 87 unit tests passed both on the host and inside the actual deploy image.
- Verified the real builder login preserves a dummy GH_TOKEN without logging it.
- Reviewed version precedence, migration/idempotence, invalid input rejection,
  build failure propagation, AUR commit guards, credential scope, and PR-only
  image validation. Existing same-revision content-change guards remain intact.
- ShellCheck passes the updater. Pre-existing entrypoint unused-pkgdir and
  deploy-asset globbing warnings remain outside this change. Workflow YAML and
  embedded Bash syntax were checked; Node action version migration is deferred.
- No AUR publish, merge, ARM execution, or system package replacement performed.
