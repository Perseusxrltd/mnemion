# 4.46.5 two-custodian host-control acceptance

**Accepted 23 October 2026 at 23:52:34 UTC** on the shared Linux host, using
published source
[`8f022bd73ee364d681214a1b60421770c061e7e9`](https://github.com/Perseusxrltd/mnemion/commit/8f022bd73ee364d681214a1b60421770c061e7e9).
The [accepted Windows/shared-host update](2026-10-23-4465-live-acceptance.md)
was the prerequisite. This is separate evidence for the complete two-custodian
host-control journey.

The two original permanent custodians, protected keys and existing OS controller
authority were retained from the
[earlier host installation](2026-10-23-independent-host-adoption.md).
Adoption, OS installation and enrollment were not repeated.

| Stage | Accepted observation |
| --- | --- |
| Windows stop | The Windows custodian's approved operation stopped the original memory service. Both custodians could inspect it without the memory API. |
| Durable stop | By **21:38:21 UTC**, the stop had survived an OS memory-manager restart and **two real scheduled watchdog ticks**. The independent controller remained available. |
| Inspected stopped state | Fresh independent native-agent and Windows observations retained the same stop and permanent custodians, with no memory API requests. No start had previously been requested. |
| Native-agent start | The planned start was issued once and succeeded at **23:46:27 UTC**. It was not a replay of an earlier start. |
| Final readiness | A fresh native OS observation passed at **23:48:16 UTC**, bound to that same start operation. |
| Final clients and connection | Both custodians retained their roles; the same saved human login, bookmarks and preferences were restored. |
| Retained memory and access | The unchanged **15-request** comparison passed, retaining all three identities, spaces, roles, exact sampled memory versions/content hashes, MCP discovery and recorded deletion. |

The journey recorded **zero memory-content writes and zero cloud model calls**.
Final completion submitted **zero additional service actions**. The original
stop and the separately completed planned start were retained; no stop, start
or enrollment was replayed. The watchdog observations came from the real
schedule.

## Preserved local interruption

After the successful manager restart and scheduled watchdog observations, a
local `git rev-parse HEAD` inspection exceeded its **10-second** bound before
the helper made a remote read. This interrupted verification before the planned
start. It was not a failed watchdog observation or a failed service start.

The original failure remains preserved. Fresh stopped-state reads then confirmed
the same authority and stopped service, and the planned native start was
performed once. The final completion only inspected the resulting readiness,
clients, restored connection and retained data.

## Evidence and limits

| Retained evidence | SHA-256 |
| --- | --- |
| Final custody acceptance receipt | `b61abcb833051412b091a02c7c03f3f4002981114ec107340453c8ab8cfcbcfa` |
| Original local verifier failure log | `6521f20d701165663704b367b58cebdb0502acbb5249af7e36fe89993297fb08` |
| Saved acceptance-gate verification | `be8ee5642fe2d9c5a07eea1836544fc23f95a39279179f47ac0cc1a0644afdd2` |

The final receipt binds the retained installation, original operations,
scheduled ticks, fresh client/OS observations and exact memory comparison.
Its **238 original-file hashes**, five completion-evidence hashes and five
retained-installation hashes match their saved files. The saved gate verification
accepted **14 required evidence files**, retained the earlier
[4.46.3 acceptance](2026-10-23-4463-custody-acceptance.md), and rejected four
invalid-evidence cases: unknown failure, wrong stop, changed original hash and
wrong source. These are evidence checks, not additional host journeys.

**Fresh native backup delivery and independent restore remain unaccepted at
this checkpoint.** The subsequent backup/restore sequence is separate work.
The [original failed/unconfirmed backup](2026-10-23-backup-transfer-diagnostics.md)
is preserved. This journey establishes retained OS authority; it does not
establish new adoption, whole-machine boot, custody on separate physical devices,
provider wake or controller-authority escrow.

All [66 requirement texts and states](../PRODUCT_REQUIREMENTS.md) are unchanged.
The [completion audit](../implementation/completion-audit.md) retains broader
pending work; this report closes no issue or publisher review.
[V08 product telemetry](../implementation/anonymous-product-telemetry.md) remains
Planned and inactive.
