# Shared Codex capture acceptance

The source app completed a durable capture journey on **22 October 2026** using
recorded actual Codex 0.163.0 conversations and a separate PostgreSQL/API on the
VPS. App enrollment, native agent controls, disconnected intake, restarts,
delivery, access withdrawal and forgetting operated on the same enrolled source.
This is development acceptance; it does not publish L1 or establish installed
Windows/macOS/Linux acceptance.

The client and server used source
`38eb3021d517a193b47501f902b4595a49d44178`, with runtime input digest
`e360b1f9dd970820323c32613652b40382f1405e687fdc508963d08d84c5af09`.
The [public producer corpus](../../service_tests/fixtures/codex-0.163/README.md)
contains two files, 34,665 bytes and three user/assistant turns, including a
resumed conversation. Its manifest pins the actual producer bytes and first-turn
prefix. This journey replayed those files; it made no new model-provider calls.

| Stage | Observed result |
| --- | --- |
| Enroll through Studio | The user-facing folder selection, Detailed policy preview, retained-copy consent and mapped audience created the source. Native agent inspection returned the same policy and source identity. The device inbox key was separately protected by the OS store. |
| Disconnect the workspace | Complete selected records entered the encrypted local inbox while the relay was closed. An unfinished UTF-8 record remained visibly unaccepted; history before tracking stayed unknown. The selected prompts and replies were absent from the database ciphertext. |
| Restart and complete intake | Another app process retained the same protected keys, exact inbox bytes and pending observation. The resumed suffix and independent conversation completed local intake. Removing both producer files preserved already accepted evidence and reported both missing scopes. |
| Lose a committed reply | A real remote delivery committed before its reply was dropped. The client retained an unknown page and its identity. An independently authenticated reader whose mapping had been removed could not read the committed records. |
| Reconcile after another restart | The unknown receipt survived. The client read the existing receipt without reposting that page, then completed delivery. All six exposed user/assistant messages appeared in readable projections; raw records matched their original byte ranges and SHA-256 values. Environment frames remained outside readable projections. |
| Observe indexing separately | Delivery completed while vector work was held. The status distinguished lexical availability, waiting vectors and delivery completion. Enabling the isolated fixture worker allowed vector indexing to catch up. A further idle drain made no new delivery commits or memory revisions. |
| Forget and restore old files | Forgetting a resumed-file projection fenced its complete fragment family and reached the local inbox. Restoring the original producer bytes did not resurrect that family; the independent conversation remained readable. |
| Inspect and remove | After reopening the same OS application identity, Studio and the native agent showed the settled queue and forgetting counts. Opening **Capture coverage and history** exposed the unknown-history boundary. Native administrator removal retired the same grant and removed the local source. |

The isolated API used real PostgreSQL, permission checks, delivery receipts and
index jobs. Deterministic four-dimensional test vectors made index-state changes
observable; they provide no embedding-quality evidence. The production database
was never opened by this test service. Its CPU, memory and lifetime were bounded,
and the explicit final shutdown stopped PostgreSQL and its SSH forward. No
production memories were written and no paid model calls were made.

## Preserved failures and continuation

The original three-phase driver is still recorded as failed. Its data checks
completed, but the final UI assertion looked for rendered history text without
opening the existing collapsed details panel. A continuation inspected the
settled state instead of replaying capture, delivery or forgetting.

That first continuation also used a different private Electron application
name, selecting a different OS credential-store identity. Workspace restoration
correctly refused decryption. Restoring the original application name and
keyring allowed the final UI observation and first source-removal request to
complete. Neither failed receipt was overwritten or promoted into a pass.

The qualified source-journey receipt contains 28 distinct assertions across the
accepted phases and continuation. Private evidence is retained under
`2026-10-22-shared-capture-r2/`: `shared-source-acceptance.json`, the original
`process.receipt.json`, both continuation receipts, the opened-status screenshot
and `stop.receipt.json`. The earlier empty lab reached its lifetime limit after
the user interrupted client launch; its clean shutdown remains separate evidence.

The public [actual-corpus regressions](../../service_tests/test_codex_capture.py)
and [installed capture gate](../../studio/electron/native-capture-probe.ts)
remain in Git. Policy changes, archives, copied-device recovery, capacity and
headless operation have their own source and installed checks; this receipt does
not replace them. The
[complete six-platform qualification and remaining L1 gates](../research/2026-10-21-durable-capture-implementation.md#required-before-l1-can-be-released)
remain necessary. Broader providers, text redaction, organization migration and
L2–L7 stay on the full roadmap.
