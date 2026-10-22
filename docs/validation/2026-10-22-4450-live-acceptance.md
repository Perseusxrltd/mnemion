# Live 4.45.0 Windows and shared-host acceptance

The actual Windows x64 installation completed **4.44.2 → 4.45.0** and
reopened its saved shared workspace. The paired acceptance completed on
**22 October 2026 at 20:24:17 UTC**, against published source `d8083b068ea0d6866747b8128b1edd8b5f256f69`.
The [public release](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.45.0) defines the features available in this version.

The normal agent-controlled restart applied the downloaded update after the app’s draft and transfer guards passed. This was a guarded restart; unattended idle restart is not claimed.

The shared Linux service also reported **4.45.0**, automatic updates enabled,
healthy supervision and no pending recovery. The guarded schema migration and independent pre/post backup receipts were verified. The saved human administrator login, bookmarks and
automatic-update, startup and background preferences survived the Windows update.

The external check made **15 requests**. The human owner, Codex and Grok Build identities and existing space access were preserved. 10 explicitly reviewed role promotions from a separate administrator task, verified before migration, were retained. No permission loss was accepted. Both sampled
agent memories retained their exact versions and content hashes; MCP tool
discovery, OAuth discovery and the recorded deletion also remained valid.

The isolated contributor lab completed **42 requests** covering
idempotent saves, CPU indexing, lexical and semantic retrieval, revision,
stale-write rejection and deletion. All synthetic memories were cleaned up.
There were **zero production memory writes and zero cloud model calls**.

## Evidence and limits

The original baseline and any stopped observer receipts are retained. Explicitly
reviewed intervening configuration is checked separately from the release:
existing access and exact memory evidence must remain. Every additional visible
space or reviewed role promotion must match its independently recorded principal
and role, including metadata-only administrator visibility. Role promotions also
require the original administrator change records and verified pre-migration
chronology. The verifier does not grant access or replay an update.

Private evidence is in `2026-10-22-shared-host-4450/`: `acceptance.receipt.json`,
`windows-before.json`, `windows-after.json`, `live-before.json`, `live-after.json`
and the referenced isolated lab receipt. The public-safe report is generated
from those validated receipts by the private release automation.

This covers one real Windows x64 installation and its shared Linux service.
Broader machine-boot, fleet/load, independent backup/recovery and provider
acceptance remain in the [complete audit](../implementation/completion-audit.md).
Publisher settings and their separate review are tracked in the
[issue plan](../implementation/github-issues.md); this update check does not
authorize changing those settings.
