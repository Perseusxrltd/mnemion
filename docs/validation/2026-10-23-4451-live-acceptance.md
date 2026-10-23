# Live 4.45.1 Windows and shared-host acceptance

The actual Windows x64 installation completed **4.45.0 → 4.45.1** and
reopened its saved shared workspace. Its paired Hostinger Linux service also
reported **4.45.1**. The acceptance receipt is dated **23 October 2026 at
00:33:04 UTC**; the controller recorded completion at **00:33:05 UTC**, against
published source `70ec58d8dbf4018ee35a9a57bd0a4677ee45cdf1`.
The [public release](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.45.1)
defines the features available in this version. Current availability follows
[release status](../RELEASE_STATUS.md).

The normal agent-controlled restart applied the downloaded Windows update after
the app's draft and transfer guards passed. This was a **guarded agent restart**;
unattended idle restart is not claimed. A transient `desktop_control_unavailable`
read at **00:16:50 UTC** occurred during that expected restart, before 4.45.1
reported ready at **00:17:10 UTC**. It remains logged as a restart observation,
not an unreviewed repeat of the update.

The shared Linux service used its **compatible automatic update**, with healthy
supervision, automatic updates enabled and no pending recovery. It invoked no
schema migration. This controller **did not perform a fresh post-update backup**;
the cycle does not establish a new backup or restore receipt. The saved human
administrator login, bookmarks and automatic-update, startup and background
preferences survived the Windows update.

The external check made **15 requests**. The same human owner, Codex and Grok
Build identities retained their existing roles. Both sampled agent memories
retained their exact versions and content hashes; MCP tool discovery, OAuth
discovery and the recorded deletion also remained valid.

The isolated contributor lab completed **51 requests** covering idempotent saves,
CPU indexing, lexical and semantic retrieval, revision, stale-write rejection
and deletion. All synthetic memories were cleaned up, with **zero cleanup
remaining**. There were **zero production memory writes and zero cloud model
calls**.

## Publication and public delivery

[Native release run 39860098559](https://github.com/Perseusxrltd/mnemion/actions/runs/39860098559)
passed all six targets. [Exact-asset verifier 39876232059](https://github.com/Perseusxrltd/mnemion/actions/runs/39876232059)
then passed for the unchanged source and all **38 assets**. Publication completed
at **00:14:17 UTC on 23 October 2026**. All six
[public installed-update targets](https://github.com/Perseusxrltd/mnemion/actions/runs/39876903393)
passed at **00:26:21 UTC**.

The website receipt at **00:16:44 UTC** verified the public version, all six
installer links, checksums, release notes, current guides and Git-owned content.
It used anonymous public HTML, excluding script/style/template text; no website
code or deployment changed, and no new visual render was performed.

## Evidence and limits

The original baseline and any stopped observer receipts are retained. Explicitly
reviewed intervening configuration is checked separately from the release:
existing access and exact memory evidence must remain. Every additional visible
space or reviewed role promotion must match its independently recorded principal
and role, including metadata-only administrator visibility. Role promotions also
require the original administrator change records and verified pre-migration
chronology. The verifier does not grant access or replay an update.

Private evidence is retained in `2026-10-23-shared-host-4451/`:
`acceptance-progress.json`, `acceptance.receipt.json`, `windows-before.json`,
`windows-after.json`, `live-before.json`, `live-after.json` and the referenced
isolated lab receipt. This report uses the public-safe report generated from
those validated receipts and the separate public-delivery evidence.
The original [native failures](2026-10-22-provider-recovery-hardening.md#native-qualification-and-exit-diagnostics)
and [rejected scan](2026-10-23-release-scan-public-metadata.md) remain historical
evidence alongside the successful later gates.

This covers one real Windows x64 installation and its shared Linux service.
Broader machine-boot, fleet/load, independent backup/recovery and provider
acceptance remain in the [complete audit](../implementation/completion-audit.md).
Publisher settings and their separate review are tracked in the
[issue plan](../implementation/github-issues.md); this update check does not
authorize changing those settings. Issues **#44/#45 remain open**. Production
adoption of the independent host controller has not occurred, and the separate
**4.46.0** source and native gates are not qualified by this 4.45.1 acceptance.
All **65 requirement rows and states** remain unchanged.
