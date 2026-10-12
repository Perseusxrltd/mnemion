# Navigation update hotfix publication — 2026-10-12

[Mnemion 4.1.4](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.1.4)
was published at **15:32:44 UTC** from
`0bb957c08597b9d3c94ca6962bb53f5eeacc282d`.

All 30 [release jobs](https://github.com/Perseusxrltd/mnemion/actions/runs/38265312522)
passed. The six installed desktop gates exercised the packaged space selector,
verified that a real unsaved memory blocks update readiness, and confirmed that
closing the disposable editor restores readiness. Existing native setup,
inference, migration, recovery and installed update checks also passed.

The automatic [independent verifier](https://github.com/Perseusxrltd/mnemion/actions/runs/38270276621)
downloaded and verified all 38 draft assets, totaling 3,865,281,429 bytes, using
the production validator from that exact source. Its
[receipt](2026-10-12-v4_1_4-hosted-verification.json) confirms unchanged asset IDs,
sizes and digests after verification. The checksum inventory's SHA-256 is
`a2d4303c64cd6572b79686578dbe5954f3d38bb7ff159f7b75628721aeed4a89`.

The [15:32:51 public check](2026-10-12-v4_1_4-publication.json) confirmed the
source tag, latest stable release, unchanged assets and all 12 anonymous public
metadata/checksum/update feeds. The [website synchronization](https://github.com/Perseusxrltd/mnemion/actions/runs/38271025181)
completed, and [live HTML verification at 15:38:53 UTC](2026-10-12-v4_1_4-website.json)
confirmed the visible version, all six downloads, current guides, notes and
checksums, the roadmap on `main`, and the homepage product link. Website code
and layout were unchanged; no new visual render is claimed.

The [public 4.1.3 → 4.1.4 upgrade rehearsals](https://github.com/Perseusxrltd/mnemion/actions/runs/38271024999)
passed on all six targets at **15:44:04 UTC**. Their [sanitized receipts](2026-10-12-v4_1_4-public-upgrades.json) confirm unchanged public packages, official feeds, real system idle, process replacement and preserved profiles.

The actual Windows session required a manual restart at **14:50 UTC** after its
old window stopped responding to navigation and the normal Quit attempt did not
exit. Before that recovery, its read-only memory view had no editors or local
workspace service, and its encrypted connection and preferences were backed up.
After reopening, the same human administrator credential authenticated, the
preferences were preserved, and navigation and native menus responded again.
The app re-protected its remembered credential during normal reconnect.
This manual recovery is distinct from the
[deterministic navigation guard bug](2026-10-12-navigation-update-safety.md)
and does not prove an unattended installation on that computer.
