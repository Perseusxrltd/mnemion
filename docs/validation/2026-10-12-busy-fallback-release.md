# Mnemion 4.1.2 publication — 2026-10-12

Version **4.1.2** was published at **12:34:43 UTC** for Windows, macOS and Linux,
with x64 and ARM64 downloads. The [live product page](https://www.perseusxr.com/mnemion)
and [GitHub release](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.1.2)
provide the current packages. This patch adds the explicit overload fallback
described in its [release notes](../releases/4.1.2.md), with no database migration.

The immutable release source is `e01229febc0f791640365649a9653d51ae30b13e`.
The [complete release workflow](https://github.com/Perseusxrltd/mnemion/actions/runs/38242103528)
passed every product and native job, including Python 3.12/3.13/3.14, real E5/BGE
checks on Linux and both Mac architectures, both deployment containers, and
installed setup/update/relaunch checks on all six targets. The corresponding
[main product checks](https://github.com/Perseusxrltd/mnemion/actions/runs/38242054654)
also passed. [Focused source/browser evidence](2026-10-12-busy-fallback.md)
includes current authorization, byte-budgeted context and older-server behavior.

All **38 uploaded assets**, totaling **3,864,031,118 bytes**, were downloaded and
checked against their GitHub sizes and SHA-256 digests. The production verifier
from the exact release commit passed the service, Windows and Mac update
signatures, complete platform feeds, package inventories and checksum parity.
The SHA-256 digest of `SHA256SUMS.txt` is
`9aed15835e4d662b1d1fc067042db0995bf8d46c16eaaea3b48481130825d7d6`.

At **12:36:22 UTC**, a separate public check confirmed the immutable tag, latest
stable release, and unchanged IDs/sizes/digests for all 38 assets. Anonymous
downloads of the update feeds, service manifest and checksums matched the
previously verified bytes. See the
[public verification receipt](2026-10-12-v412-publication.json).

Website synchronization completed automatically in
[run 38249898873](https://github.com/Perseusxrltd/mnemion/actions/runs/38249898873),
updating the fallback on `main` in commit `4b6f7fa`. A real browser check at
**12:44:20 UTC** verified all six current download links, 4.1.2 notes and setup
guides, checksums, the live roadmap, and the existing homepage's product link
and canonical icon. Desktop (1440 px) and mobile (390 px) views had no page
overflow or uncaught JavaScript errors. See the
[website record](2026-10-12-v412-website.json). No website edit or deployment was
needed for this hotfix.

The separate public **4.1.1 → 4.1.2 automatic update and relaunch passed on all
six targets**, with preserved profiles, the official feeds, unmodified public
packages and real system idle. Windows x64/ARM64, macOS Intel/ARM64 and Linux x64
passed in the [original workflow](https://github.com/Perseusxrltd/mnemion/actions/runs/38249899263).
Linux ARM stopped before installation because GitHub returned HTTP 504 while
downloading the public checksum file. Its
[targeted rerun](https://github.com/Perseusxrltd/mnemion/actions/runs/38251756291)
passed at **13:03:34 UTC**, using the same public packages and a bounded metadata
gateway retry correction. The original workflow retains its failed result;
the [combined six-target receipt](2026-10-12-v412-public-upgrades.json) identifies
each successful run. The first website sync encountered the same gateway
failure, followed by its successful automatic run. The shared fetcher's
27 tests and 29 independent-verifier tests passed, as did the
[complete product checks](https://github.com/Perseusxrltd/mnemion/actions/runs/38251655084)
on the pipeline correction.

The subsequent independent
[hosted verification workflow](2026-10-12-artifact-verification.md) also passed,
checking all 38 published assets and production signatures on another runner.
Its [receipt](2026-10-12-v412-hosted-verification.json) exactly matches the complete
local inventory verified before publication. The initial read-only token could
not discover the draft; the corrected permission and manual verification passed.
Its automatic trigger against a future draft remains to be exercised.

The actual Windows desktop was most recently verified at 4.1.0 and the shared
server at 4.1.1. Their normal schedules are separate from publication and these
CI rehearsals. The [Windows concurrency record](2026-10-12-windows-concurrency.md)
covers that real server version and independent provider wake, not a live 4.1.2
fallback or a maximum-capacity benchmark. Individual sign-in, hosted consent,
provider capture, host inventory and broader recovery remain on the
[requirements checklist](../PRODUCT_REQUIREMENTS.md).
