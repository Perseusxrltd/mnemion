# Four independent MCP clients — 29 October 2026

Four separately initialized HTTP/MCP clients completed lexical searches on the
live **4.46.40** service in **50–62 seconds**. This records slow responses under
the conditions below. After-upgrade acceptance remains pending; both
[field reports](../implementation/multi-agent-field-readiness.md), issues 47 and
48, remain open.

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

This lexical-only baseline does not qualify default hybrid search, cross-user
authorization, source-expiry changes or the reporter's complete accessible
corpus. It did not reproduce `generation_changed` or `database_unavailable`.
The host upgrade is still in progress at this checkpoint. After-upgrade client
measurements and the reported error, latency and hybrid acceptance remain open;
there is no measured post-upgrade speedup here. Current release availability is
tracked separately in [release status](../RELEASE_STATUS.md).

The probe made no memory writes, settings changes or model calls and initiated
no upgrade. Retained evidence contains timing, fixed errors and counts, without
memory contents, private identifiers, host addresses or credentials. Runtime,
requirements and release metadata are unchanged by this report.

The following private receipts are retained; their SHA-256 values bind the
observations and original failure without publishing private access details.

| Receipt basename | SHA-256 |
| --- | --- |
| `baseline-44640-two-streams.json` | `0724a43777fa1f1e0656fac203abae4e6f788578c0f3b817040d35dfef21e582` |
| `baseline-host-environment.json` | `5211e20c4bdc24cc500b1762df5660886be4c605b38361edf3f55bf0ea085c6b` |
| `fixture-correction.json` | `df9d788e77c233ab3cd76ccc9518023bf601f6e21282c48cdba8fd5a2749f283` |
| `baseline-44640-during-snapshot.json` | `49c4e3e33574b4de0f726afe467dea0676cdcfe9922f8832e499625128f5c167` |
