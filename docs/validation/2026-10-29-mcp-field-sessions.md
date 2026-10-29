# Four independent MCP clients — 29 October 2026

Four separately initialized HTTP/MCP clients completed lexical searches in
**11.02–15.35 seconds** after the actual host upgrade to **4.46.44**, compared
with **50.04–62.42 seconds** on 4.46.40. This is one uncontrolled comparison under
the conditions below; both [field reports](../implementation/multi-agent-field-readiness.md),
issues 47 and 48, remain open.

## Corrected baseline

The run completed at **00:51:27.832 UTC**. Four separately created HTTP transports
and initialized MCP clients used **one normal principal**, query `mnemion`,
`all_accessible: true`, lexical mode and `limit: 3`. The search starts were
spread over **0.000238 seconds**. Server session identifiers were not exposed by
the installed SDK and were not collected; this verifies independent client
contexts, not four distinct principals or server-issued session IDs.

| Client | Search elapsed, seconds | Hits | Warnings |
| --- | ---: | ---: | ---: |
| 1 | 50.042197 | 3 | 2 |
| 2 | 62.420967 | 3 | 2 |
| 3 | 58.079476 | 3 | 2 |
| 4 | 51.404192 | 3 | 2 |

All four outcomes were `success` with `match_status: matched`. One request
exceeded 60 seconds. The receipt's `passed: true` means all four fixture searches
completed; it does not establish performance acceptance.

All clients reported package 4.46.40. A separate host sample at
**00:51:30.435 UTC**, about 2.6 seconds after completion, also verified 4.46.40.
It recorded **one logical CPU**, a **14.09 one-minute load average**, and an
active snapshot operation (`activating` / `start`). This is contextual evidence
sampled just after the requests, not simultaneous per-request profiling or proof
that the snapshot caused the latency.

## After-upgrade comparison

The actual **4.46.40 → 4.46.44** host-upgrade phase finished at
**01:37:32.269488 UTC**, reporting `upgraded`, exit code 0 and a ready service.
The existing one-shot comparison completed at **01:38:04.178972 UTC**. It used
four new, separately created HTTP transports and initialized MCP clients with
the same normal principal, query `mnemion`, `all_accessible: true`, lexical mode
and `limit: 3`. Every client reported package **4.46.44**; search starts were
spread over **0.000362 seconds**.

| Client | Search elapsed, seconds | Hits | Warnings |
| --- | ---: | ---: | ---: |
| 1 | 12.186958 | 3 | 2 |
| 2 | 11.019534 | 3 | 2 |
| 3 | 15.348521 | 3 | 2 |
| 4 | 12.249132 | 3 | 2 |

All four outcomes were `success` with `match_status: matched`, and each request
finished within 60 seconds. The mean across each group of four was
**55.486708 seconds before** and **12.701036 seconds after**: an observed
**42.785672-second decrease, or 77.1% lower mean**. These descriptive results
do not isolate the upgrade's effect. Request parameters matched, but background
work, host load and cache state were not controlled; the receipts contain no
paired per-request load profile.

The comparison request at **01:37:36.571011 UTC** records one read-only run,
no automatic retry and `post_backup_complete: false`. Post-upgrade backup was
still pending for this probe. These client results do not establish completed
backup or full guarded-upgrade acceptance.

## Original fixture failure retained

The original attempt completed at **00:49:06.333 UTC** with four initialized
clients but **zero search requests**. The private fixture indexed a nonexistent
third transport-tuple element after initialization. The installed SDK yields
only `read_stream, write_stream`. All four recorded `client_error` with
`ExceptionGroup`; the original failed receipt remains retained.

The correction removed that session-ID assumption and recorded separately owned
HTTP transports and successful MCP initialization. No product fix is inferred
from this fixture correction, and the failed attempt is not a search-failure
reproduction.

## Scope and remaining acceptance

These lexical-only probes do not qualify default hybrid search, cross-user
authorization, source-expiry changes or the reporter's complete accessible
corpus. Neither reproduced `generation_changed` or `database_unavailable`.
The after-upgrade lexical comparison is now recorded, while the reported error,
full-scope latency and hybrid acceptance remain open. Current release
availability is tracked separately in [release status](../RELEASE_STATUS.md).

The probes made no memory writes, settings changes or model calls and did not
initiate the separate host upgrade. Retained probe evidence contains timing,
fixed errors and counts, without memory contents, private identifiers, host
addresses or credentials. Runtime,
requirements and release metadata are unchanged by this report.

The following private receipts are retained; their SHA-256 values bind the
observations and original failure without publishing private access details.

| Receipt basename | SHA-256 |
| --- | --- |
| `baseline-44640-two-streams.json` | `0724a43777fa1f1e0656fac203abae4e6f788578c0f3b817040d35dfef21e582` |
| `baseline-host-environment.json` | `5211e20c4bdc24cc500b1762df5660886be4c605b38361edf3f55bf0ea085c6b` |
| `fixture-correction.json` | `df9d788e77c233ab3cd76ccc9518023bf601f6e21282c48cdba8fd5a2749f283` |
| `baseline-44640-during-snapshot.json` | `49c4e3e33574b4de0f726afe467dea0676cdcfe9922f8832e499625128f5c167` |
| `after-44644.json` | `0cf5d2ef518f937afbc43fb0fc3cef39dee467b86f656a36f27fe3a8db0fea93` |
| `after-upgrade-request.json` | `9fa008f29cf8b163883019e1089c882d6e55c8c2b7bd41f593b2d8dbd85fa653` |
| `host-upgrade.receipt.json` | `ed805850b503df56f52ce4b271d885275f227683546586957e48250946bdc93b` |
