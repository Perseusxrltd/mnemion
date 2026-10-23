# Live 4.46.3 Windows and shared-host acceptance

The actual Windows x64 installation completed **4.46.2 → 4.46.3** and
reopened its saved shared workspace. The paired acceptance completed on
**23 October 2026 at 15:54:32 UTC**, against published source `56e29f2c58d746170fa64bab09e7da91589efeee`.
The [public release](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.3) defines the features available in this version.

The normal agent-controlled restart applied the downloaded update after the app’s draft and transfer guards passed. This was a guarded restart; unattended idle restart is not claimed.

The preceding 4.46.2 attempt updated Windows, while the host remained on 4.46.1. That failed attempt remains preserved. Fresh read-only inspection verified the original saved administrator login, bookmarks and preferences before this continuation; the earlier installation was not repeated.

The shared Linux service also reported **4.46.3**, automatic updates enabled,
healthy supervision and no pending recovery. This compatible update did not
invoke a schema migration. The saved human administrator login, bookmarks and
automatic-update, startup and background preferences survived the Windows update.

The external check made **15 requests**. The same human owner, Codex and Grok Build identities retained their existing roles. Both sampled
agent memories retained their exact versions and content hashes; MCP tool
discovery, OAuth discovery and the recorded deletion also remained valid.

The isolated contributor lab completed **42 requests** covering
idempotent saves, CPU indexing, lexical and semantic retrieval, revision,
stale-write rejection and deletion. All synthetic memories were cleaned up.
There were **zero production memory writes and zero cloud model calls**.

## Preserved interruptions and inspected continuation

The compatible host operator completed the memory-service update at
**15:27:40 UTC**. The original paired observer subsequently stopped when two
previously visible source spaces were temporarily absent. The unchanged
15-request identity/access comparison passed after provider renewal; no
permission or lease configuration was edited to make the comparison pass.
The original observer directory remains preserved.

The original Windows lab cycle also remains **failed**: **40 requests succeeded
and one was interrupted during deletion**. Read-only native inspection then
confirmed all three synthetic deletion operations were ready and their records
returned HTTP 404. A correction to the private lab's cleanup handling passed
four focused Windows checks; it did not modify the product binary. The fresh
42-request cycle above passed with exactly the original request, concurrency,
time and resource limits.

The final paired continuation used the already completed update receipts,
unchanged guards and that fresh passed lab. It requested **no additional update,
restart or lab cycle**. It did not replace the original failure with a passing
receipt. The accepted receipt's timestamp is **15:54:31.783013 UTC**, rounded
to 15:54:32 UTC above.

## Evidence and limits

The original baseline and any stopped observer receipts are retained. Explicitly
reviewed intervening configuration is checked separately from the release:
existing access and exact memory evidence must remain. Every additional visible
space or reviewed role promotion must match its independently recorded principal
and role, including metadata-only administrator visibility. Role promotions also
require the original administrator change records and verified pre-migration
chronology. The verifier does not grant access or replay an update.

Private evidence is in `2026-10-23-shared-host-4463-access-recovery/`: `acceptance.receipt.json`,
`windows-before.json`, `windows-after.json`, `live-before.json`, `live-after.json`
and the referenced isolated lab receipt. The public-safe report is generated
from those validated receipts by the private release automation.

This covers one real Windows x64 installation and its shared Linux service.
Broader machine-boot, fleet/load, independent backup/recovery and provider
acceptance remain in the [complete audit](../implementation/completion-audit.md).
Publisher settings and their separate review are tracked in the
[issue plan](../implementation/github-issues.md); this update check does not
authorize changing those settings.

At this acceptance checkpoint, the full two-custodian operational journey,
fresh native backup delivery and independent production restore had not passed.
The original dependent jobs stopped at their prerequisites before effects.
No whole-machine boot, separate physical-device custody or controller-authority
escrow is established. Issues [#44](https://github.com/Perseusxrltd/mnemion/issues/44)
and [#45](https://github.com/Perseusxrltd/mnemion/issues/45) remain open for their
outstanding criteria. The local-note publisher remains deliberately paused
pending its separate guard/QC review; service health does not establish new
local-note publication.

The subsequent [two-custodian journey](2026-10-23-4463-custody-acceptance.md)
passed at **16:25:34 UTC**, with its original interrupted observations preserved.
Fresh backup and independent restore remained pending at that later checkpoint.

All 66 requirement texts and states remain unchanged. V08 product telemetry
is Planned and inactive. The later [legacy vendor-telemetry correction](2026-10-23-legacy-vendor-telemetry.md)
on main is not included in this frozen 4.46.3 release.
