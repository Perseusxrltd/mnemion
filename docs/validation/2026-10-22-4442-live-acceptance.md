# Live 4.44.2 Windows and shared-host acceptance

The actual Windows x64 installation completed **4.44.1 → 4.44.2** and
reopened its saved shared workspace. The paired acceptance completed on
**22 October 2026 at 16:35:34 UTC**, against published source `3bdb3371ccd31bcf095d2e25a4b7d8263260b735`.
The [public release](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.44.2) remains separate from unreleased durable capture.

The normal agent-controlled restart applied the downloaded update after the app’s draft and transfer guards passed. This was a guarded restart; unattended idle restart is not claimed.

The shared Linux service also reported **4.44.2**, automatic updates enabled,
healthy supervision and no pending recovery. This compatible update did not
invoke a schema migration. The saved human administrator login, bookmarks and
automatic-update, startup and background preferences survived the Windows update.

The external check made **15 requests**. The same human owner,
Codex and Grok Build identities retained their existing roles. Both sampled
agent memories retained their exact versions and content hashes; MCP tool
discovery, OAuth discovery and the recorded deletion also remained valid.

The isolated contributor lab completed **41 requests** covering
idempotent saves, CPU indexing, lexical and semantic retrieval, revision,
stale-write rejection and deletion. All synthetic memories were cleaned up.
There were **zero production memory writes and zero cloud model calls**.

## Evidence and limits

The original baseline and any stopped observer receipts are retained. Explicitly
reviewed intervening configuration is checked separately from the release:
existing roles and exact memory evidence must remain, and every additional
visible space must match its recorded principal and role, including metadata-only
administrator visibility. The verifier does not grant access or replay an update.

Private evidence is in `2026-10-22-shared-host-4442/`: `acceptance.receipt.json`,
`windows-before.json`, `windows-after.json`, `live-before.json`, `live-after.json`
and the referenced isolated lab receipt. The public-safe report is generated
from those validated receipts by the private release automation.

This covers one real Windows x64 installation and its shared Linux service.
Broader machine-boot, fleet/load, independent backup/recovery and provider
acceptance remain in the [complete audit](../implementation/completion-audit.md).
[Issue #45](https://github.com/Perseusxrltd/mnemion/issues/45) retains its separate
paused-publisher guard/security review. No publisher was resumed by this update.
