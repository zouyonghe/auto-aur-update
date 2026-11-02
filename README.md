# auto-aur-update
Update the program in aur warehouse automatically

## AstrBot desktop

`astrbot-desktop-bin` repackages the official stable Debian binaries for
`x86_64` and `aarch64`. PixelTerm-C keeps its existing updater and build action.

- `.github/workflows/pixelterm-update.yml` updates PixelTerm-C at 02:30 UTC and supports a
  manual dispatch. It serializes AUR publishes and is idempotent when the package is already
  current. For a dependency ABI or packaging-only rebuild, increase `pkgrel` in the committed
  `pixelterm-c/PKGBUILD` and dispatch the workflow; the change is explicit and reviewable.
- `.github/workflows/astrbot-update.yml` updates AstrBot at 03:45 UTC and supports a manual
  dispatch. It calls `.github/workflows/publish-astrbot-desktop-bin.yml` as a reusable workflow.
- `.github/workflows/task-sync.yml` keeps the repository Task sync independent from package
  publishing and retains the owner-only repository-watch trigger. Every workflow publishes
  only from `main`.
- Pull requests are validated by `.github/workflows/astrbot-desktop-bin.yml` without AUR
  credentials.
- The updater requires both release assets and their GitHub SHA256 digests;
  makepkg downloads and verifies the actual files before publishing.
- PixelTerm-C starts a new upstream version at `pkgrel=1`. For a same-version
  dependency ABI or packaging-only rebuild, bump `pkgrel` in the committed
  `pixelterm-c/PKGBUILD`; the updater keeps the higher of that value and AUR's
  current revision. AstrBot preserves higher committed/AUR revisions.
- PRs run tests and both repackaging builds without AUR credentials. Scheduled
  and manually dispatched runs on `main` publish using the existing
  `AUR_USERNAME`, `AUR_EMAIL`, and `AUR_SSH_PRIVATE_KEY` secrets. No binaries
  are pushed to AUR.
- Preparation records the AUR Git commit alongside the generated PKGBUILD.
  Deployment aborts if that snapshot changed; it never rebases stale packaging
  over another maintainer's update. Rerun the workflow to prepare fresh inputs.
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
