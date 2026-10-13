# Personal sign-in, search passages and update guards — 4.2.0

[Mnemion 4.2.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.2.0)
was published on **13 October 2026 at 14:26:07 UTC**, from
`af7f9b795bc94b36c432810148e80a82fd1ce340`, for all six desktop targets.

All 30 [signed release jobs](https://github.com/Perseusxrltd/mnemion/actions/runs/38402533389)
and all 11 [separate product jobs](https://github.com/Perseusxrltd/mnemion/actions/runs/38402470751)
passed on that exact source. Native acceptance includes actual workspace setup,
invitations, individual sign-in, protected remembering and reopen, revocation,
and guarded update/relaunch. The preceding
[source and browser checks](2026-10-13-individual-sign-in.md) remain separate evidence.

The [independent uploaded-byte verifier](https://github.com/Perseusxrltd/mnemion/actions/runs/38409308511)
passed for **38 assets**, totaling **3,871,326,506 bytes**. The
[receipt](2026-10-13-v4_2_0-hosted-verification.json) records the production
validator and unchanged uploaded IDs, sizes and digests. The checksum inventory
SHA-256 is `e736739aa882a0653473b1aeed9d6580f8cf32de28553250eeac8ce1068f5979`.

## Installed schema migration and recovery

The [4.1.7 → 4.2.0 installed migration](https://github.com/Perseusxrltd/mnemion/actions/runs/38411957565)
passed on Windows, macOS and Linux, each on x64 and ARM64. The
[six receipts](2026-10-13-v4_2_0-installed-migrations.json) establish actual
installed setup/model use, schema 014 → 015, automatic reopen, unchanged original
credentials/identities/grants/memories, contributor withdrawal, and verified
pre-migration backups. Isolated restoration applied the current deletion ledger,
kept withdrawn content absent, rotated restored recovery keys without changing
the original workspace's keys, and shut down its database cleanly.

The validation driver accounts for migration 015's false-by-default API-key
session marker only in the previous snapshot. The candidate's actual values
remain checked. Real PostgreSQL tests also reject an erroneous marker change.
That correction changed the driver, not the frozen application packages.

## Public delivery

The [14:27:00 publication check](2026-10-13-v4_2_0-publication.json) confirmed
the exact tag, latest stable release, unchanged assets and all 12 anonymous
metadata/checksum/update feeds. [Website synchronization](https://github.com/Perseusxrltd/mnemion/actions/runs/38413327167)
completed automatically. The [14:28:07 live HTML check](2026-10-13-v4_2_0-website.json)
verified the visible version, all six installers, current notes and guides,
checksums, the roadmap on `main`, and the homepage product link. No website
layout change or new visual render is claimed.

The [public 4.1.7 → 4.2.0 automatic-update rehearsals](https://github.com/Perseusxrltd/mnemion/actions/runs/38413324257)
passed on all six targets by **14:37:29 UTC**. The
[sanitized results](2026-10-13-v4_2_0-public-upgrades.json) confirm the official
feed, unchanged packages, real system idle, process replacement and preserved
profiles. The starting installer hashes match the independently verified 4.1.7
release. These results are separate from installed migration and prepublication gates.

At 14:29:53 UTC, the user's existing Windows app still ran 4.1.7 in the
background. No forced update, changed preference or user-profile installer
probe was used. The shared host was last independently authenticated as 4.1.7;
it still needs a backed-up, controlled migration before personal sign-in is
available there. Updating a desktop does not upgrade its remote workspace.

Hosted OAuth/consent, company SSO, delegated host recovery, source-provider
onboarding and broader hardware/quality measurements remain on the full
[requirements list](../PRODUCT_REQUIREMENTS.md). The released matching-passage
correction closes issue 35; exact-identifier ranking, recency and relevance
calibration remain separate retrieval work.
