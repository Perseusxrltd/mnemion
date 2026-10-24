# 4.46.5 fresh company-host backup acceptance

**Accepted 24 October 2026 at 00:01:45 UTC.** The installed Windows host-control
client created a fresh encrypted backup, and a separate native-agent custodian
independently verified its remote contents. Both used published
[`8f022bd73ee364d681214a1b60421770c061e7e9`](https://github.com/Perseusxrltd/mnemion/commit/8f022bd73ee364d681214a1b60421770c061e7e9)
after the [actual paired update](2026-10-23-4465-live-acceptance.md) and
[retained-custodian lifecycle](2026-10-23-4465-custody-acceptance.md) passed.

| Observation | Result |
| --- | --- |
| Fresh snapshot | Captured at **23:55:36 UTC on 23 October**. |
| Later access/deletion ledger | Captured at **23:58:18 UTC**. |
| Delivery and readback | Verified at **23:59:22 UTC**. |
| Separate custodian verification | Completed at **00:01:38 UTC on 24 October** against the same encrypted files. |
| Encrypted input | **409,217,303 bytes**: a 408,647,661-byte host package and 569,642-byte ledger, with matching complete-file digests. |
| Client visibility | Both existing custodians saw the same verified backup. |
| Retained configuration | Service policy, backup destination, credentials and configured transfer window were unchanged during this journey. |

The saved acceptance receipt has SHA-256
`84e9e80b906b072f469ccc2f2f2549441672a21f1ce1873f8f8328bcf9c97c5e`.
It binds the original create and verify operations, their prerequisite evidence,
and the final client observations. The journey recorded zero memory-content
writes and zero cloud model calls. The earlier
[failed/unconfirmed backup](2026-10-23-backup-transfer-diagnostics.md) remains
preserved; this acceptance belongs to the new completed operation.

## Independent restore checkpoint

An independent reader subsequently retrieved and verified those exact encrypted
files through its own existing GitHub access, without connecting to the producer
host. The signed public 4.46.5 package and matching native database runtime were
also verified locally.

The first restore runner stopped at **00:02:10 UTC** because it invoked the legacy
`mnemion` command instead of the installed `mnemion-service` recovery entry point.
The argument parser exited before backup inspection or restoration; no recovery
workspace was created. The original failure and completed retrieval remain
preserved. A corrected private runner is continuing only the uncompleted local
inspection/restore stage, reusing the verified runtime and encrypted files.
**Independent restore is not yet accepted at this checkpoint.**

Backup verification does not establish controller-authority escrow, whole-machine
recovery, custody on separate physical devices or activation of a replacement
service. The live workspace remains separate from the unselected recovery copy.
All [66 requirements](../PRODUCT_REQUIREMENTS.md), open deployment issues and the
deliberately paused note publisher retain their existing states.
[V08 anonymous product telemetry](../implementation/anonymous-product-telemetry.md)
remains Planned and inactive.
