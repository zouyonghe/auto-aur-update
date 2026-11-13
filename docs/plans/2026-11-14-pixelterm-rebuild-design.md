# PixelTerm dependency-triggered rebuilds

Approved behavior: daily PixelTerm updates reconcile libmupdf and ffmpeg against
the refreshed Arch database snapshot, then compare their installed package
versions with the last published AUR PKGBUILD. Installed versions must remain
unchanged through the build; query failure or drift stops publication. No upstream
or dependency version is hardcoded. Dependency package updates may trigger a
rebuild even when their ABI remains compatible.

Record a data-only `# rebuild-deps:` comment in the published PKGBUILD. Never
source the remote PKGBUILD. Missing records trigger one migration rebuild;
malformed records and failed dependency queries stop publication. Marker-like
comments are detected even with indentation or malformed delimiters; only one
exact canonical record is accepted. Template marker-like comments are replaced wholesale
with the canonical installed-version record. A new upstream
version starts at pkgrel=1. Otherwise use the higher of AUR pkgrel+1 (when the
record changes) and the matching committed template revision. Identical records
preserve pkgrel, and identical generated packaging skips compilation.

Preparation generates metadata only and uploads an immutable package/snapshot
artifact before any source build. Changed packaging is built from a disposable
copy on a separate credential-free runner, with startup checks. That job uploads
no artifacts. Publishing runs on a fresh runner and downloads the original
preparation artifact; it never consumes build-modified files. Deployment must still
match the AUR commit observed during preparation. Preserve existing triggers,
credentials, and main-only publishing. AUR consumers rebuild on their next update;
this does not remotely replace installed binaries or detect ARM-only changes.

Tests cover dependency changes, migration, repeat runs, manual revisions, new
upstream releases, malformed/query failures, build failure, and AUR snapshot
handoff. Verify the full unittest suite and an actual local package build.
