# Scheduled backup delivery gate — 29 October 2026

The guarded shared-host upgrade stopped **before requesting any upgrade action**
when the existing scheduled backup failed during Git delivery. At **03:45:43 UTC**
the service remained **4.46.44**. Its auto-updater was enabled with the
`identical` schema policy; [migration 036](../../mnemion/service/migrations/036_vault_metadata_auditors.sql)
was still required for [vault metadata auditors](../service/secrets-vault.md).
No migration or additional backup capture was requested by the stopped guard.

This incident concerns the private canonical-host backup helper. It does not
establish a defect in every released application's Git provider.

## Successful capture, failed publication

All times below are UTC on 29 October. The snapshot unit began at **03:16:13**
under the existing operating-system schedule; the guard reused that work.

| Stage | Started | Completed | Retained result |
| --- | --- | --- | --- |
| Snapshot capture | 03:16:15 | 03:38:13 | Exit 0; archive and capture receipt present. |
| Ledger capture | 03:38:38 | 03:40:45 | Exit 0; archive and capture receipt present. |
| Overall scheduled snapshot unit | 03:16:13 | 03:42:06 | Failed, exit 1, during Git publication. |

Git reported unavailable pack indexes: its multi-pack index (MIDX) still
referenced `.tmp-*` pack indexes removed by the abandoned-upload cleanup routine.
The last recorded Git command exited **128**. A separate read-only connectivity
check with MIDX disabled exited **0**, with no writes requested. This supports
an index-metadata failure; it does not qualify a complete restore.

The last independently verified delivery in the failed-job observation was
**03:15:59**, before these captures. The guard stopped for inspection at
**03:43:31** with an empty action list and **zero additional captures requested**.
Successful capture therefore did not satisfy the delivery gate. The
[earlier delivered backup and 45-minute controller timeout](2026-10-29-field-operations.md)
remain separate retained evidence.

## Local repair qualification

The **03:53:25** qualification used real local Git repositories and recorded
four cases, with **zero production mutations**:

| Case | Result |
| --- | --- |
| Original cleanup removes pack indexes still named by MIDX. | Failure reproduced. |
| Repair derived index metadata while preserving refs and the archive. | Git access restored; preservation checks passed. |
| Corrected cleanup retains indexed temporary packs and their companions. | Passed. |
| Healthy index needs no repair. | Unchanged. |

The candidate helper retains potentially indexed temporary packs and their
companions. Its recorded SHA-256 is
`1808ae7b8d0bb9ae85b98f7f360623aa93dac7318d34a6a5a43d31aa57787a85`.

## Production repair and release scope

The corrected helper was installed at **03:57:00 UTC**. The production index
repair succeeded with **refs unchanged, zero pack files deleted and zero backup
archives deleted**. Publication then exited **1**, leaving the repair unit
failed overall. All three ledger, snapshot and cache-maintenance timers were
restored **active**. The follow-up upgrade guard stopped at **04:09:01** with
an empty action list and **zero additional captures requested**.

The service-account ownership repair completed at **04:21:38**: **29 cache
entries** were reassigned, the original empty Git index lock was quarantined,
archive inventory was unchanged, and Git was verified as the actual service
account. No packs were deleted and no memory services were restarted.

The corrected uploader was installed at **04:24:13**, with SHA-256
`ac7de7ac749be2aec13ed9b2bf4ba63c5152d795831322ea0713becbe3cff810`.
It places its private index outside the published tree, uses level-zero Git
compression for new encrypted objects, and reuses parts only after fresh archive
and part hashes match its own verified remote delivery. **Eight real local Git
reconstruction/admission cases and three cleanup cases passed**. The initial
index-placement fixture failed with `Retired or extra archive parts survived`;
that failure and its correction are retained separately.

One fresh snapshot-and-ledger attempt runs as the service account under its
original OS unit because the older snapshot exceeded the unchanged **one-hour
migration freshness gate**. That unit owns the temporary pause of all three
backup timers; its `ExecStopPost` hook restores them on exit. The new upgrade
guard's **04:28:28** observation records **no migration actions and zero extra
captures requested by the guard**. Fresh delivery, performance, migration 036
and installed vault-auditor acceptance remain **pending**; the last verified live
service version is **4.46.44**. Original publication failures and full
cache-maintenance, post-upgrade and guarded-host acceptance remain open.

Separately, [v4.46.48](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.48)
was published at **03:46:47 UTC**. The
[website run](https://github.com/Perseusxrltd/mnemion/actions/runs/40814041922) and
[public auto-update rehearsal](https://github.com/Perseusxrltd/mnemion/actions/runs/40814044656)
completed successfully. The public release lists these installer file sizes;
they measure download files and do not establish this host's upgrade:

| Platform | Installer bytes |
| --- | ---: |
| Windows ARM64 / x64 | 219,961,051 / 225,876,955 |
| macOS ARM64 / x64 | 263,513,315 / 271,010,727 |
| Linux, four installers | 242,965,156–270,242,847 |

All **66 requirement states remain unchanged**. Issues **44, 47 and 48 remain
open**. **V08 is Building**, with telemetry collection unavailable; neither
the destination nor route is configured.

## Retained evidence

These SHA-256 values bind private operational receipts without publishing their
paths, host identifiers, contents or credentials. Receipt labels distinguish the
initial observation, index repair, ownership repair and uploader follow-up;
in-progress observations are evidence only for their recorded state.

| Receipt | SHA-256 |
| --- | --- |
| `initial-host-status.json` | `5d2e38d319d5cf821f0cf6b11624e009fc146da682af4ead88db61121f32f8b9` |
| `scheduled-backup-baseline.json` | `ab94b217ae7bbbeb8796f24a53e6906c5850ab6a585baabb245a347e78c88014` |
| `progress.json` | `cc1c091be4afc63112a7f14a2ea2f432fc18455634bbcc0fc1e67d599bf76f0a` |
| `failed-scheduled-backup.json` | `ca7740bd8b53a448d614a2007ea0c9bd36e46bea67b69eb86887ada88c49c4d8` |
| `snapshot-failure-details.private.json` | `57e28cc9e5cce6000a489f032739b44a1cfdac0b4fa3949490f77b68c9fbbb89` |
| `cache-connectivity-without-midx.json` | `b4a315e4e7134064d9e69fe2ef0035f30fa5e533a6759fb7b9014b3e3425dd99` |
| `candidate.json` | `ad1e26052c07b6ccfc9ea621b7fcceb6f035731afa8170874e3f187eea6a64c9` |
| `qualification.json` | `64ffe1551c80f5a1f1725d3b6e93cfb25b0e0152121019ca41901d677cc2c61d` |
| `outcome.json` (production repair) | `8b5aab703337e0c001360eb5df39f07e89430cc55b7f4a25fdfa561d9e85d837` |
| `progress.json` (after repair) | `51f5fd06750ea2febe113d467edb2a10f96394f223f2a87235914788d51b3dbd` |
| `outcome.json` (ownership repair) | `f4fb6cd4c7f7214bdd271acf856ed79f366b14a27a4474099e5ce55f85ce8795` |
| `qualification.json` (initial uploader fixture) | `854127f4e428f9c6a0f9ccfba1ea05ea48c37ea562ad68478ebe5dc7dc826c15` |
| `index-placement-correction.json` | `39374a58533f1016e51f6e29db495bd00f6a619c6c2b33b4792a27a5bd121638` |
| `qualification-corrected.json` | `5ed9639ee62b24239915388033506cf2b67a16d975772302b4baeb7295ecd057` |
| `cleanup-qualification.json` | `eeae3c2ad1c3960da8c893aca6825a59c888a51d7dab2db2d1b6e82069710359` |
| `launched.json` (fresh-backup unit) | `badcd86002671bf4371c5db440ea33554025492a7089d152de94b96fdd4c5af7` |
| `progress.json` (fresh-backup guard) | `7f93ae39d9d6f108e3e147b5f60b1f6137548c0da29f7f8574cfebbcfd4153e2` |
| `delivery-observation.json` (fresh-backup unit) | `1d27f90d26d9db98daeda3756bbd9485b638281bf4c6923b1b64d9e4e0b584a5` |
