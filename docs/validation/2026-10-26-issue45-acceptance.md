# Issue #45 deployment acceptance

[Issue #45](https://github.com/Perseusxrltd/mnemion/issues/45) closed on
**26 October 2026 at 01:21:46 UTC**, following the
[public evidence comment](https://github.com/Perseusxrltd/mnemion/issues/45#issuecomment-6406128595).
The five original criteria have dated acceptance evidence. Original stopped
drivers, failed comparisons, backup failures and their inspected continuations
remain preserved.

| Original criterion | Accepted evidence |
| --- | --- |
| Finish and independently verify the fresh encrypted pre-migration snapshot. | Independent pre-migration Git delivery passed on 20 October before the guarded 4.37 upgrade. The later [4.45 migration](2026-10-22-4450-live-acceptance.md) independently verified a fresh encrypted snapshot and ledger at **22 October 19:53:04 UTC**, before its 19:53:07 start. |
| Inspect the stopped driver, then follow the existing guarded upgrade procedure without replaying an uncertain action. | Inspection established that the earlier stop preceded the upgrade command and that no upgrade journal existed. The official 4.37 upgrade completed at **20 October 12:00:00 UTC**. The [later 4.45 continuation](2026-10-22-4450-live-acceptance.md) retained the original stopped comparison and reconciled independently authorized role changes without replaying the upgrade. The [guarded procedure](../service/managed-upgrades.md) remains documented. |
| Verify actual host/client versions, preserved identities, outstanding synthetic cleanup, and the bounded acceptance lab; retain the original failed receipt. | [Actual 4.46.6 paired acceptance](2026-10-24-electron-security-4466.md) passed at **24 October 02:15:05 UTC**: both versions 4.46.6, three identities and exact sampled evidence retained, protected login/settings preserved, **45 isolated requests**, zero pending cleanup, production-memory writes or cloud-model calls. |
| Verify a fresh post-upgrade backup and update the installation runbook from observed receipts. | Independent post-migration backup delivery passed for 4.37 and 4.45. [Native backup creation and separate custodian verification](2026-10-24-4465-backup-acceptance.md) passed at **24 October 00:01:45 UTC** for **409,217,303 encrypted bytes**; independent isolated restore passed at **00:15:23 UTC**. The [company-host runbook](../guides/company-host-control.md) records the supported procedure and limits. |
| Record the paused local publisher explicitly and track its separate security-review/restart prerequisite; a healthy Mnemion API must not imply end-to-end freshness of local notes. | The [issue plan](../implementation/github-issues.md) and operator runbook explicitly retain the deliberate PC publisher pause and independent guard/QC prerequisite. Closing #45 neither resumes that publisher nor establishes publication of newer local notes. |

A **26 October 01:20 UTC read-only check** returned service version **4.46.6**
from public health and installed Windows Studio version **4.46.6** from its
registry entry. The Windows app was not running and was not started for this
check. This confirms the recorded installation versions; the actual app journey
remains the dated 24 October acceptance. Its guarded Windows restart does not
establish unattended idle restart.

The [4.43 contention cycle](2026-10-21-443-acceptance.md) also passed **39/39
requests**, including two semantic queries overlapping indexing and complete
cleanup. This is bounded operation-overlap evidence; representative fleet/load
and provider acceptance remain open. The separate Grok Bot cloud-client issue
[#44](https://github.com/Perseusxrltd/mnemion/issues/44), broader recovery/resource
work and installed acceptance of the
[scheduled-backup capture correction](2026-10-25-host-backup-capture.md) remain
open. Its latest independent manifest contains a 24 October full snapshot and
25 October ledger, both captured on 4.46.6; it does not establish a new 25 October
full snapshot.

All **66 requirement texts and states remain unchanged**. V08 remains Building,
with production collection unavailable and destination/route unset.

## Original evidence digests

| Evidence | SHA-256 |
| --- | --- |
| Verified issue closure receipt | `e98d718830766d1d6f738a5f6fb1b87c93c43023cebc2dfaf521b6a1053a4f5b` |
| Posted evidence comment text | `3dfde271470298eac4b95549ad472fd82a2bf9288eb41dbae44b81929fde42d1` |
| Actual 4.46.6 paired acceptance | `271662275f09d1a0cf6d120b828fc8c9bdabb33d181bf1d03693f74a4066cf46` |
| Fresh native backup acceptance | `84e9e80b906b072f469ccc2f2f2549441672a21f1ce1873f8f8328bcf9c97c5e` |
| Independent isolated restore acceptance | `b4f2f7e457a81c9949ba444645ad8150cd5b069f4a2a38e63ce70bcfcf2c4ec5` |
