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

One fresh snapshot-and-ledger attempt ran as the service account under its
original OS unit because the older snapshot exceeded the unchanged **one-hour
migration freshness gate**. That unit owned the temporary pause of all three
backup timers and their `ExecStopPost` restoration. The new upgrade
guard's **04:28:28** observation records **no migration actions and zero extra
captures requested by the guard**.

The installed isolated-index helper above completed snapshot capture at
**04:48:15** and ledger capture at **04:50:28**, both with **exit 0**. Git add
succeeded, but **Git push timed out at 05:07:49** after the unchanged
**600-second limit**. The independent GitHub ref still matched the previous
**03:15:59** delivery. All three backup timers were active again at the
**05:16:04** observation. The original guard stopped at **05:08:28** with an
empty action list and no replayed mutations; no new off-host delivery or host
migration was verified.

A separate **publish-only unit** started at **05:17:29**, retaining the same
captured archives and helper. Its **Nice=0 / I/O priority=4** matched
`mnemion-backup@snapshot.service`; the earlier isolated unit inherited Nice=10.
It requested publication at **05:18:46**, with **zero new captures** and the
unchanged **600-second Git limit**. Repack failed at **05:20:40**: the optional
multi-pack bitmap could not obtain full object closure (`could not write
multi-pack bitmap`). This attempt made **no push**. The preceding maintenance
job also failed on its 600-second command limit (**05:08:30–05:18:36**).

All three backup timers were restored active. The new guard stopped at
**05:23:02** with **zero actions**. A read-only check as the actual service
account ran `git fsck --connectivity-only --no-dangling` with
`core.multiPackIndex=false` and `pack.useBitmaps=false` and exited **0**.
Ordinary object connectivity passes; this does not qualify every byte,
performance or a new off-host delivery. The last verified delivery remained
**03:15:59** at the **05:29:24** observation. A separate publisher omitting
optional multi-pack/bitmap work from publication was being prepared, with
installation still pending. The priority change does not establish a cause or
a performance improvement.

The **05:31:42 ordinary-Git candidate qualification failed its bandwidth gate**.
First-publication reconstruction and publication with unusable optional metadata
passed, but unchanged ciphertext was included in the incremental pack. The
candidate was **not installed**. At that checkpoint, the live helper remained
`ac7de7ac749be2aec13ed9b2bf4ba63c5152d795831322ea0713becbe3cff810`.
Local graph probes retained these results:

| Synthetic graph or walk | Pack objects | Pack bytes |
| --- | ---: | ---: |
| Unrelated roots | 5 | 256,403 |
| Shared empty parent | 5 | 256,463 |
| Previous commit as parent | 3 | 394 |
| Parentless commit with identical remote staging tree | 5 | 256,412 |
| Sparse walk enabled / disabled | 5 each | 256,433 each |

The unrelated-root and shared-empty-parent walks included the unchanged blob;
the previous-parent walk excluded it. These synthetic comparisons do not qualify
a production graph change or bandwidth acceptance.

The first anchored candidate then **failed legacy transition** at **06:01:41**,
after eight cases passed: existing ciphertext was retransmitted. The retained
nested-path probe isolates sparse negative-tree traversal: bridge packs were
**377,942–377,947 bytes** with sparse walking, versus **795–800 bytes** without it.

At **06:06:10**, the corrected candidate passed **14 real local Git cases** with
**zero production mutations**. It uses bounded, parentless ciphertext-chunk
anchors and disables sparse negative-tree traversal. Checks cover exact-byte
reconstruction, a **5,973-byte unchanged pack**, legacy transition packs of
**10,011 then 8,073 bytes**, concurrent remote-head refusal without a completion
receipt, retirement and separate cache maintenance. Candidate SHA-256:
`1a666bb6f2e585a1dca201200014f1ed42096673795f7681a0e23e9bb42af1b8`.
The qualified helper was installed at **06:17:50**, with **zero new captures**
requested. The original unit completed successfully at **06:30:27**, publication
exit **0**. At **06:39:44** it was inactive and all three timers were active again.
Archive inventory was unchanged, service-account cache ownership was verified,
and the receipt reports **zero shared index locks and zero memory-service restarts**.

The publisher recorded delivery at **06:30:05**: **1,125,836,193 ciphertext bytes**,
**55 anchors**, **1,125,874,858 new Git-object bytes**, **one push**, no legacy bridge,
and **448.479 seconds for push plus readback**. At **06:43:14**, an independent
GitHub account check confirmed that delivery commit was readable and its manifest
matched every local ciphertext SHA-256 and size: **three archives, two retained
snapshots and 55 commit parents**. This is commit/manifest verification; archive
payloads were **not downloaded or restored**. The result does not establish
snapshot freshness, general performance or a host upgrade.

The normal scheduled follow-up completed at **06:33:11** and its current GitHub
ref was independently matched at **06:46:07**. It reused **54 parts** and
**1,125,247,039 bytes of unchanged ciphertext**, with **610,519 new Git-object
bytes** and **8.744 seconds for push plus readback**. This verifies the actual
incremental path after timer restoration. A separate fresh-backup unit has now
been launched; its new snapshot, independent verification and migration remain
pending.

Snapshot freshness, performance, migration 036 and installed vault-auditor acceptance
remain **pending**; the last verified live service version is **4.46.44**.
Original publication failures and full cache-maintenance, post-upgrade and
guarded-host acceptance remain open.

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

Subsequently, [v4.46.49](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.49)
became public with **38 assets**. Its
[public update rehearsal](https://github.com/Perseusxrltd/mnemion/actions/runs/40820128156)
passed all six desktop targets;
[documentation CI](https://github.com/Perseusxrltd/mnemion/actions/runs/40820612659)
and [website synchronization](https://github.com/Perseusxrltd/mnemion/actions/runs/40820612636)
also passed. These release checks do not establish the shared host's migration.
The **06:13:42** download measurement covered eight 4.46.49 installers: Windows
ARM64/x64 files were **219,971,156 / 225,888,882 bytes**; the largest installer
was **270,997,730 bytes**. All eight were below **400 MiB (419,430,400 bytes)**.

The **4.46.50 Linux x64** native
[backup-resume gate](https://github.com/Perseusxrltd/mnemion/actions/runs/40815491489/job/123273331148)
failed with `local:backup-status`: “Backup settings could not be read safely.
Existing recovery files were retained.” Its cause is not established.
The original release run finished **failed at 05:54:35** and was not retried.
The separate [4.46.51 backup-reader hotfix](2026-10-29-backup-read-snapshot.md)
passed [source CI](https://github.com/Perseusxrltd/mnemion/actions/runs/40826012101);
its [native release run](https://github.com/Perseusxrltd/mnemion/actions/runs/40829255129)
is still running at this checkpoint. A separate
[Windows fixture correction](2026-10-29-backup-read-windows.md) retains that
original candidate and leaves its application runtime unchanged.
**v4.46.49 remains the latest verified public release.**

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
| `outcome.json` (isolated-index transfer) | `2bc4063165c68c3caab1f07a791c9df8740ec32706bf20de699ecb8c1ef11598` |
| Stopped guard receipt, 05:08:28 UTC | `88f5da335b620dde0433daf8f3c76ddf48e2e43d2e3b21c7dfe13a655ebb51a1` |
| `expected.json` (publish-only plan) | `1cb0f34516287eb0cc3bf96ed8cb1130ec8f2946c194c2771c79d6993773282f` |
| `launch-intent.json` (publish-only plan) | `8853f3cb4b10627f280899521cd5830d15e2e3734d7e1bd5c00f978f000b9846` |
| `outcome.json` (publish-only failure) | `f5ddba823ac043eb5374d8504eaeedc150f56b5de25df2bfeed3679985e3996b` |
| `progress.json` (after publish-only failure) | `f80e5a574dc7f808334b86566895a0c6f350c07c34ba96a39c68fb2da0588407` |
| Stopped guard receipt, 05:23:02 UTC | `fbef84bf8d6762f91f705496d30b09a8081d8c6e038d6e8794937c96fc7e045c` |
| `original-installed-evidence.json` (4.46.50 Linux x64) | `3d979843edbd928af5337ff039680727777cf16b1e919f94a671254789e244c4` |
| `original-job.log` (4.46.50 Linux x64) | `183b9a6ed5d8a566af0d81263f1c144edca366b9786cd9d718cdbce1507829c6` |
| `candidate.json` (undeployed ordinary-Git candidate) | `da0c72a2d1b75c6be0b50a4b4ad10532e5e3dedfc9b3b82a3078fdebb23c4b3e` |
| `qualification.json` (ordinary-Git bandwidth failure) | `c244e42e2b86daa6b90ff8d21d780386e66e99a2fa3a2ac00a0f14a7a6f816cb` |
| `graph-probe/result.json` | `a40daabe585903ed8c434068a345ca801721f51c8c2d84323a6d3bfd790013cb` |
| `graph-probe/identical-tree-result.json` | `7053249495043bd962319b7af63121f6e68eb812fa2d21a2b5fba8c336a479f7` |
| `graph-probe/sparse-walk-result.json` | `50d8a6ed3e155d242540ab4778561620d6a4eec4a2b5e3db9a78e7d1abc033d2` |
| `qualification.json` (first anchored candidate failure) | `c9d43b7b2a8c743a75175114b87d88141db6294f21b714cb2572405baea5747e` |
| `legacy-nested-path-result.json` | `ed3f776586febf3b2cb0bdef163506943ca4fd6dc23bfba562fd53fa703ed07c` |
| `qualification.json` (corrected anchored candidate) | `27c24b97343fbc9820587caf303d390c081591f5d4f65c23ebfa9c97ab7e498c` |
| `published-44649-installer-sizes.json` | `ed8635e6bfdecb11bf5f782258e1e5b32dce94e1863f79d28b6d99530d294a4c` |
| `062106Z-original-unit-observation.json` | `377c9df1f4df9a0607d09741410dd0df5e7c3f02600816e325b97039e4878af0` |
| `063944Z-original-unit-observation.json` | `daf7c84db6a42b3c6e47776ca00d8dc664925d0d23ceb4c6a269e3cbfa41835e` |
| `independent-delivery.json` (commit and manifest) | `1617f8ae4aa0bd55d40dfeda74332580a0599e9c3486c0b498937ea3e38d744b` |

| `scheduled-followup-delivery.json` | `97bc998dd592873fa7dfe7cda495542405d4c4eecaea206a610eba9be81835fc` |
