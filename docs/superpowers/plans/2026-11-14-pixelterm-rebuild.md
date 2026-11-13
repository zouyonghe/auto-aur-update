# PixelTerm Automatic Rebuild Implementation Plan

> Execution: native in this session. User subsequently requested review and a PR;
> commit and push the reviewed branch, but do not publish AUR packages or merge.

**Goal:** Automatically publish a higher pkgrel when libmupdf or ffmpeg changes.

**Architecture:** Reconcile dependencies, then record installed Arch versions in a data-only PKGBUILD
comment. Compare against AUR, upload trusted preparation inputs, build changed
packaging on a disposable runner, and pass the original artifact to guarded
deployment on a fresh runner. Build jobs cannot return deployment inputs.

**Tech Stack:** Bash, pacman, makepkg, Python unittest, GitHub Actions.

**Spec:** `docs/plans/2026-11-14-pixelterm-rebuild-design.md`

## Global Constraints

- No hardcoded upstream/dependency version or sourcing remote shell code.
  Required image tooling such as diffutils may be installed explicitly.
- Failed queries or builds must prevent deployment; preserve main-only scheduling.
- New upstream versions start at pkgrel=1; unchanged inputs do not repeatedly bump.

## Review Focus

- Missing legacy metadata: establish a baseline through one rebuild.
- Epoch-bearing dependency versions: retain the complete pacman version string.
- Malformed/duplicate records: fail closed without executing remote content.
- Explicit higher template pkgrel: preserve it rather than incrementing twice.
- Concurrent AUR edits: reject deployment using expected_revision_file.

## Task 1: Implement and verify the updater

Files: `scripts/pixelterm-c.sh`, `tests/test_pixelterm_update.py`,
`build-aur-action/entrypoint.sh`, `tests/test_build_action.py`,
`.github/workflows/pixelterm-update.yml`, `README.md`.

- [x] Add failing tests for the review-focus cases, per-dependency changes,
  no-op builds, query failures, and build failure propagation.
- [x] Run `python3 -m unittest discover -s tests -v` and confirm expected failures.
- [x] Query each dependency using pacman print mode, validate versions, write the
  comment, and choose pkgrel according to the design. Clean-build changed inputs.
- [x] Refresh the build container with a full upgrade and propagate setup errors.
  Write `.aur-revision` and connect it to deployment's existing snapshot input.
- [x] Update README; run the full tests, bash syntax checks, and package build.
- [x] Review diff for idempotence, unsafe shell interpolation, and publish gates.

After review, commit and open a PR as subsequently requested by the user.
Do not dispatch publishing workflows or merge.

## Verification evidence

- The initial rebuild-only slice passed 83 unittest cases; the initial PR's
  combined CI fixes passed 87. Re-run the full suite for the current count:
  `python3 -m unittest discover -s tests -v`.
  Inverting the dependency-change condition in a
  temporary copy failed both MuPDF and FFmpeg regression cases as expected.
- Running the actual updater in an isolated directory queried live dependencies,
  migrated current AUR 1.8.6-1 to 1.8.6-2, and built a package successfully.
  Packaged version output was `1.8.6`; readelf showed `libmupdf.so.28.6`.
  Reproduce without installing PixelTerm into the system on fully upgraded x86_64 Arch,
  with base-devel, git, curl, jq, pkgconf, chafa, glib2, gdk-pixbuf2, ffmpeg, and
  libmupdf installed, as a non-root user with sudo permission for pacman.
  Use a disposable build container: the updater installs/upgrades dependencies
  and performs a full upgrade against its existing sync database snapshot.

  ```sh
  set -eu
  sandbox="$(mktemp -d)"
  mkdir -p "$sandbox/scripts" "$sandbox/pixelterm-c"
  cp scripts/pixelterm-c.sh "$sandbox/scripts/"
  cp scripts/build-pixelterm.sh "$sandbox/scripts/"
  cp pixelterm-c/PKGBUILD "$sandbox/pixelterm-c/"
  bash "$sandbox/scripts/pixelterm-c.sh"
  bash "$sandbox/scripts/build-pixelterm.sh" "$sandbox/pixelterm-c"
  ```

  This reads live upstream/AUR state, so generated versions and SONAMEs will
  change. The second command deliberately forces a verification build even when
  preparation reports no changes. It runs startup checks within makepkg and
  deletes all source/build outputs when finished; there is no packaged binary
  to inspect afterward. CI uses different disposable runners for these commands
  and a third fresh runner for publishing the original preparation artifact.
- Bash syntax and git whitespace checks passed. ShellCheck passed the updater;
  the container entrypoint retains pre-existing SC2034 (`pkgdir` unused).
- No PixelTerm system-package installation, publishing-workflow dispatch, AUR publication,
  or native ARM validation was performed.
