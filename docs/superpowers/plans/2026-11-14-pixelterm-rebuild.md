# PixelTerm Automatic Rebuild Implementation Plan

> Execution: native in this session. User subsequently requested review and a PR;
> commit and push the reviewed branch, but do not publish AUR packages or merge.

**Goal:** Automatically publish a higher pkgrel when libmupdf or ffmpeg changes.

**Architecture:** Record queried Arch package versions in a data-only PKGBUILD
comment. Compare against AUR, build changed packaging, and pass its AUR snapshot
to the existing guarded deployment action.

**Tech Stack:** Bash, pacman, makepkg, Python unittest, GitHub Actions.

**Spec:** `docs/plans/2026-11-14-pixelterm-rebuild-design.md`

## Global Constraints

- No hardcoded upstream/dependency version; no new dependencies or remote sourcing.
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

- 83 unittest cases passed. Inverting the dependency-change condition in a
  temporary copy failed both MuPDF and FFmpeg regression cases as expected.
- Running the actual updater in an isolated directory queried live dependencies,
  migrated current AUR 1.8.6-1 to 1.8.6-2, and built a package successfully.
  Packaged `pixelterm -V` returned `1.8.6`; readelf showed `libmupdf.so.28.6`.
  Evidence: `/tmp/opencode/pixelterm-auto-rebuild-mmcynk3y/build.log`.
- Bash syntax and git whitespace checks passed. ShellCheck passed the updater;
  the container entrypoint retains pre-existing SC2034 (`pkgdir` unused).
- No system package installation, GitHub workflow execution, AUR publication,
  or native ARM validation was performed.
