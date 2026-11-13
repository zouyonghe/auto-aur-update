# auto-aur-update
Update the program in aur warehouse automatically

## AstrBot desktop

`astrbot-desktop-bin` repackages the official stable Debian binaries for
`x86_64` and `aarch64`. PixelTerm-C keeps its existing updater and build action.

- `.github/workflows/pixelterm-update.yml` updates PixelTerm-C at 02:30 UTC and supports a
  manual dispatch and owner-only repository-watch trigger. It serializes AUR publishes and is
  idempotent when the package is already current. Dependency updates trigger rebuilds
  automatically (see below). For a manual packaging-only rebuild,
  set `pkgver` in `pixelterm-c/PKGBUILD` to the current AUR version and increase `pkgrel` above
  the published revision. Commit both values, then dispatch the workflow from `main`.
- `.github/workflows/astrbot-update.yml` updates AstrBot at 03:45 UTC and supports a manual
  dispatch. It calls `.github/workflows/publish-astrbot-desktop-bin.yml` as a reusable workflow.
- `.github/workflows/task-sync.yml` keeps the repository Task sync independent from package
  publishing and retains the owner-only repository-watch trigger. Every workflow publishes
  only from `main`.
- Triggers request state reconciliation, not publication of every event or source snapshot.
  Each workflow/branch keeps one active run and at most one pending run; a later trigger
  can replace a pending run even with `cancel-in-progress: false`. Manual dispatches follow
  the same rule. If a required run was replaced or failed, dispatch again from current `main`.
  Explicit `pkgver`/`pkgrel` changes remain in Git for subsequent runs; there is no one-shot
  rebuild request or FIFO delivery guarantee.
- Pull requests are validated by `.github/workflows/astrbot-desktop-bin.yml` without AUR
  credentials.
- The updater requires both release assets and their GitHub SHA256 digests;
  makepkg downloads and verifies the actual files before publishing.
- PixelTerm-C starts a new upstream version at `pkgrel=1`. For a manual same-version
  packaging-only rebuild, first align the committed `pkgver`
  with AUR, then set `pkgrel` higher than AUR's current revision. A template's
  revision applies only to its own upstream version; older template revisions
  are ignored. AstrBot preserves higher committed/AUR revisions.
- Migration from `rebuild_current`: the build action still accepts an omitted
  input or `false` for ordinary updates. Passing `true` now fails before setup
  with migration instructions. Replace that input with the explicit
  `pkgver`/`pkgrel` commit described above; automatic release increments and
  one-shot rebuild queues are no longer used.
- PRs run tests and both repackaging builds without AUR credentials. Scheduled
  and manually dispatched runs on `main` publish using the existing
  `AUR_USERNAME`, `AUR_EMAIL`, and `AUR_SSH_PRIVATE_KEY` secrets. No binaries
  are pushed to AUR.
- Preparation records the AUR Git commit alongside the generated PKGBUILD.
  Deployment aborts if that snapshot changed; it never rebases stale packaging
  over another maintainer's update. Rerun the workflow to prepare fresh inputs.
- A publishing run uses its triggering source commit throughout preparation
  and deployment. Later `main` commits are picked up by the next scheduled or
  manually dispatched run. A Task-only `time.log` update does not invalidate
  an in-progress package build.
- Deployment rechecks the latest stable version and asset digests. A new release
  or replaced asset invalidates the build and requires rerunning the workflow.
  It rechecks the committed PKGBUILD again immediately before Git push; GitHub
  and AUR cannot be updated atomically, so a small check-to-push window remains.
  GitHub release download URLs are mutable; standard AUR `makepkg` cannot use
  GitHub's authenticated asset-ID API endpoint. Final verification downloads
  both assets and hashes their bytes immediately before push, but this cannot
  prevent an upstream replacement in the remaining check-to-push window.
- Existing AUR epochs are retained; explicit template epoch increases permit
  version resets. Preflight and final staged comparisons include epoch.
- Existing AUR packages require coherent RPC and Git `.SRCINFO` metadata. Missing
  metadata fails closed. New upstream versions do not inherit old checksum revisions.
- SSH host fingerprints are pinned to those published on the AUR homepage.
  Host-key rotation requires an explicit reviewed update, not blind keyscan trust.
- The configured AUR account must own/co-maintain an existing package, or be
  allowed to create this new package. The AUR repository is currently new.
- The upstream AGPL license is pinned to a source commit; bundled third-party
  licenses remain untouched. Review the license when upstream changes it.

Validation: `python3 -m unittest discover -s tests -v`, then `makepkg` from
`astrbot-desktop-bin/` on Arch. CI repacks ARM binaries on an x86_64 runner;
this validates archives/checksums, not native ARM execution or Wayland GUI.
Install/upgrade through your AUR helper rather than the AppImage updater.

PR validation also builds the actual deployment Docker image, checks both
equal/different-file comparisons, and runs the test suite inside it without AUR
credentials. The image explicitly installs `diffutils` for `cmp`: a fuller local
test environment previously hid
this missing dependency. Comparator failures now report a tool/access error,
not a false packaging-change error; genuine changes still require higher pkgrel.
Test checkouts do not persist credentials; container tests mount an isolated
read-only copy excluding `.git` directories and worktree credential pointers.

## PixelTerm-C dependency rebuilds

Every scheduled/manual update refreshes the Arch system, reconciles `libmupdf`
and `ffmpeg` against that database snapshot, then reads their installed versions,
including epochs and package revisions. The installed versions are checked again
after building; drift or query failure prevents publication.
It compares them with a `# rebuild-deps:` comment in the published AUR PKGBUILD;
no upstream or dependency version is hardcoded in the detector.
An isolated workflow step queries the release API using its read-only GitHub
token and passes only the validated public release tag to the updater. Neither
the updater nor upstream build tools receive the token. Local runs query public
endpoints without authentication and retain fallbacks.
If the authenticated API fails or returns an invalid tag, release resolution
falls back to the public latest-release redirect and validates its host, project,
and numeric tag before exporting it. No token is passed to this public request.

- Changed dependencies automatically request AUR's current `pkgrel + 1`.
  A higher explicit template revision wins; new upstream releases start at `1`.
- A missing legacy record triggers one baseline rebuild. Unchanged records keep
  the revision; identical packaging skips compilation. Compatible dependency
  updates also trigger rebuilds: this is package-version detection, not ABI analysis.
- Failed queries, malformed records, or failed builds stop publication. Preparation
  uploads an immutable `pixelterm-prepared` artifact before source builds run.
  A separate credential-free runner clean-builds a disposable copy and checks
  `--version` and `--help`; it uploads no artifacts. A fresh publishing runner
  downloads the original preparation artifact by its immutable numeric ID,
  never a build-produced file or a replacement artifact with the same name.
  Deployment rejects an AUR commit changed since preparation.
- Old template marker-like comments are removed before writing exactly one
  canonical installed-dependency record; malformed published records still fail.
- The published PKGBUILD is the durable baseline, updated only after successful
  publication. No GitHub cache or manual revision commit is needed for dependency
  changes. Existing explicit revision requests remain supported.

The scheduled detector runs on x86_64 Arch. ARM-only repository changes are not
detected, and ARM execution is not tested. The daily schedule may lag repository
updates or be delayed by GitHub. Installations rebuild only when users update
through their AUR helper; no installed binary is remotely replaced.

MuPDF's update from `libmupdf.so.28.5` to `libmupdf.so.28.6` illustrates why
this is needed: existing executables retain the old SONAME. Reinstalling a cached
package does not relink them.

Developer tests require PyYAML (`python-yaml` on Arch), in addition to Python.
Run `python3 -m unittest discover -s tests -v`. Checkout credential assertions
parse YAML values, so commented settings or quoted `"false"` cannot satisfy them.

For an immediate local repair after a full system upgrade, clean-build instead
of reusing a cached package:

```sh
git clone https://aur.archlinux.org/pixelterm-c.git
cd pixelterm-c
makepkg --cleanbuild --syncdeps --check --install
pixelterm --version
```

Rebuild again when MuPDF or FFmpeg changes its required SONAME. Never symlink
an old SONAME to a different library version to bypass the loader error.
