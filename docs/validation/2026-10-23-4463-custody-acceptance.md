# 4.46.3 two-custodian host-control acceptance

**Accepted 23 October 2026 at 16:25:34 UTC** on the canonical Linux host,
using published 4.46.3 source `56e29f2c58d746170fa64bab09e7da91589efeee`.
The two original permanent custodians and the existing controller installation
were retained. The preceding [Windows/shared-host paired acceptance](2026-10-23-4463-live-acceptance.md)
was the prerequisite; this is separate evidence for independent host control.

| Stage | Accepted observation |
| --- | --- |
| Retained authority | Two distinct permanent custodians kept their existing roles and protected profiles. Adoption, OS installation and enrollment were not repeated. |
| Windows stop | The Windows custodian's approved operation stopped the original memory service. |
| Control while memory was unavailable | Both custodians independently inspected the host through the native interface while the memory API was down. |
| Durable stop | Memory stayed deliberately stopped through an OS memory-manager restart and **two real scheduled watchdog ticks**. |
| Native-agent start | The second custodian started the original memory service. The final inspection used that original start request ID. |
| Final readiness and clients | A fresh OS read passed at **16:20:21 UTC**. Both clients retained their roles; the same saved human connection, bookmarks and preferences were restored. |
| Retained content and access | The unchanged **15-request** identity/access/content/MCP comparison passed, retaining exact sampled evidence. |

The accepted journey recorded **zero memory-content writes and zero cloud
model calls**. Completion submitted **zero additional service actions**; no
stop, start or enrollment was replayed. The two watchdog observations came from
the real schedule, not a simulated timer or two manual repair requests.

## Preserved observations and limits

An earlier final-state read had not yet established readiness. A later local
verifier import failure occurred before its API checks. Both failures remain
preserved. Read-only inspection subsequently confirmed the original start's
ready state; the verifier then completed with the corrected interpreter.
The inspected continuation did not reissue the service operations.

The original [4.46.1 first-stop failure](2026-10-23-independent-host-adoption.md)
also remains historical evidence. This accepted 4.46.3 journey does not relabel
that earlier failure as a pass.

The private final receipt is
`2026-10-23-company-host-custody-4463-r4/custodian-journey/receipt.json`, SHA-256
`16c4cd075560bb3153afb5eea2e08f5c88a3e455e71d004848518208d28e2f0d`.
It binds the retained installation, original operations, scheduled ticks,
final OS/client observations and unchanged content comparison. Private host,
operator and operation identifiers, keys and raw logs are excluded here.

**Fresh native backup delivery and independent production restore have not
passed at this checkpoint.** This journey does not establish whole-machine
boot, custody on separate physical devices, provider wake or independently
recoverable controller-authority escrow. Broader continuity remains in the
[completion audit](../implementation/completion-audit.md).

All [66 requirement texts and states](../PRODUCT_REQUIREMENTS.md) are unchanged;
no issue is closed by this report. The local-note publisher's separate pause
remains in force, and [V08 product telemetry](../implementation/anonymous-product-telemetry.md)
remains Planned and inactive.
