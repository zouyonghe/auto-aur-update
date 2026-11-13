# PixelTerm dependency-triggered rebuilds

Approved behavior: daily PixelTerm updates compare the current Arch package
versions of libmupdf and ffmpeg with the last published AUR PKGBUILD. No upstream
or dependency version is hardcoded. Dependency package updates may trigger a
rebuild even when their ABI remains compatible.

Record a data-only `# rebuild-deps:` comment in the published PKGBUILD. Never
source the remote PKGBUILD. Missing records trigger one migration rebuild;
malformed records and failed dependency queries stop publication. Marker-like
comments are detected even with indentation or malformed delimiters; only one
exact canonical record is accepted. A new upstream
version starts at pkgrel=1. Otherwise use the higher of AUR pkgrel+1 (when the
record changes) and the matching committed template revision. Identical records
preserve pkgrel, and identical generated packaging skips compilation.

Preparation builds changed packaging with makepkg, installs build dependencies,
and runs the PKGBUILD startup checks before deployment. Deployment must still
match the AUR commit observed during preparation. Preserve existing triggers,
credentials, and main-only publishing. AUR consumers rebuild on their next update;
this does not remotely replace installed binaries or detect ARM-only changes.

Tests cover dependency changes, migration, repeat runs, manual revisions, new
upstream releases, malformed/query failures, build failure, and AUR snapshot
handoff. Verify the full unittest suite and an actual local package build.
