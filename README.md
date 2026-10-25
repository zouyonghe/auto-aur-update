# auto-aur-update
Update the program in aur warehouse automatically

## AstrBot desktop

`astrbot-desktop-bin` repackages the official stable Debian binaries for
`x86_64` and `aarch64`. PixelTerm-C uses its existing, separate workflow.

- `.github/workflows/astrbot-desktop-bin.yml` checks daily or on manual dispatch.
- The updater requires both release assets and their GitHub SHA256 digests;
  makepkg downloads and verifies the actual files before publishing.
- New versions start at `pkgrel=1`; existing AUR revisions are never lowered.
  For packaging-only changes, bump `pkgrel` in the committed template.
- PRs run tests and both repackaging builds without AUR credentials. Only
  scheduled/manual runs on `main` publish using the existing `AUR_USERNAME`,
  `AUR_EMAIL`, and `AUR_SSH_PRIVATE_KEY` secrets. No binaries are pushed to AUR.
- Preparation records the AUR Git commit alongside the generated PKGBUILD.
  Deployment aborts if that snapshot changed; it never rebases stale packaging
  over another maintainer's update. Rerun the workflow to prepare fresh inputs.
- Deployment rechecks the latest stable version and asset digests. A new release
  or replaced asset invalidates the build and requires rerunning the workflow.
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
