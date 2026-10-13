# Desktop update retry publication — 2026-10-13

[Mnemion 4.1.5](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.1.5)
was published at **07:32:09 UTC** from
`d154f7a132d2ca3aaf92e0c15ff2aaa040d2bfa1`.

All 30 [release jobs](https://github.com/Perseusxrltd/mnemion/actions/runs/38273454238)
passed, including the six native installer, local-workspace and update/relaunch
targets. The [product checks](https://github.com/Perseusxrltd/mnemion/actions/runs/38273382633)
also passed. The [retry validation](2026-10-12-update-retries.md) records the
106 Electron tests and distinguishes controlled transport failures from actual
Windows observations.

The [automatic independent verifier](https://github.com/Perseusxrltd/mnemion/actions/runs/38278099847)
validated all 38 draft assets, totaling 3,865,376,305 bytes, with the production
validator from the exact source above. Its [receipt](2026-10-13-v4_1_5-hosted-verification.json)
records unchanged uploaded IDs, sizes and digests. The checksum inventory's
SHA-256 is `267c24ad06988d70e1b92ac8f05ea5fddd384f170ee7ff38f7f8bcc44d79e531`.

The [07:32:20 public verification](2026-10-13-v4_1_5-publication.json) confirmed
the source tag, latest stable release, unchanged assets and all 12 anonymous
metadata/checksum/update feeds. [Website synchronization](https://github.com/Perseusxrltd/mnemion/actions/runs/38363270717)
completed automatically. [Live HTML verification at 07:36:55 UTC](2026-10-13-v4_1_5-website.json)
confirmed the visible version, all six installer links, current notes, guides
and checksums, the roadmap on `main`, and the homepage product link. The website
layout was unchanged; no new visual render is claimed.

The [public 4.1.4 → 4.1.5 update rehearsals](https://github.com/Perseusxrltd/mnemion/actions/runs/38363270715)
passed on all six targets at **07:43:23 UTC**. The
[sanitized receipts](2026-10-13-v4_1_5-public-upgrades.json) confirm official feeds,
unchanged public packages, real system idle, process replacement and preserved
profiles. The starting installer digests match the independently verified 4.1.4
release. These results are separate from the prepublication native gates.

At **07:30 UTC**, the actual Windows installation was 4.1.3, with automatic
updates, background operation and login startup enabled. Its saved independent
human administrator authenticated to the shared 4.1.4 service. The observation
gap means the initiation of that desktop installation is not established; it
is not presented as proof of an unattended 4.1.5 update or automatic retry.
