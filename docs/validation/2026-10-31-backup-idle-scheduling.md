# Idle local-backup scheduling

**31 October 2026 — source validation for 4.46.62.** Actual Grok implementation
`3da9bb1e00649b4e83fa9b9df0b382f71e026fec` was adopted in the review checkout as
`0363b0e240e9488b0f9c727a757ade90db4ce267`, on parent
`7070dde6a157cd325e070ded0a3da7ebaed97082`.

The original isolated reproduction made three scheduler ticks with no saved
backup policy. It observed three secure-storage availability calls and no
backup runs. The probe used a fake workspace and cipher; it did not access an
OS keychain or the user's recovery files.

[LocalBackups](../../studio/electron/local-backups.ts) now checks the saved
policy before constructing any scheduling evidence. Unconfigured or disabled
backups stop there. Enabled schedules share receipt validation, actual file
availability, persisted retry state and the due-time calculation with public
status, while skipping the secure-store and retention-display reads. A backup
that actually runs still validates its protected key through the existing path.
Public status remains a fresh, complete view. The one-minute cadence and
generation, overlap, cancellation, inspection and close guards are retained.

One source-check plan ran once on the reviewed source:

| Check | Result | Scope |
| --- | --- | --- |
| Strict Electron TypeScript compilation | Passed | Existing strict project configuration |
| Existing local-backup test module with the new regression cases | 32 passed, 0 failed, 2 skipped | Temporary files, fake workspace/cipher, controlled races and reads |

The [test module](../../studio/electron/scripts/test-local-backups.mjs) covers
unconfigured and disabled idle ticks, stopped/busy hosts, enabled but not-due
backups, fresh status, changed schedules, cancellation, corrupt policy, persisted
retry deadlines and replacement of missing or changed recovery files. Its
existing key-protection and retention cases also passed. The two skipped cases
require native Windows folder protection or sharing-lock behavior; the Linux
source run does not qualify those native cases. No real backup or keychain
operation ran, and no successful check was replayed for this record.

This removes unnecessary reads; it does not establish measured CPU/RAM savings
or complete installed-app acceptance. The
[whole-product efficiency contract](../implementation/runtime-efficiency.md)
remains open. F06/R04 stays Partial, V08 stays Building, production telemetry
stays off, and all 66 requirements remain retained. Native packaging and public
update checks have separate evidence in [release status](../RELEASE_STATUS.md).
