# Telemetry storage adapter prototype — 26 October 2026

A private Linux x64 prototype evaluates operation-scoped ownership of a SQLite
library while retaining the existing shared database and telemetry policy logic.
It follows the [storage follow-up decision](2026-10-26-telemetry-storage-followup.md).
**No product runtime changed, and no RSS/CPU improvement is established.** V08
remains **Building**, all 66 requirement texts and states are unchanged, and
production collection/destination/route remain **false/null/null**.

## Experiment and lifecycle

The declared plan used source `ab19e5e072935d7251dd0e64d0129e207cc8366b` and one
private C/Node-API adapter loading the existing system SQLite library by its
resolved absolute path. That dependency is an experiment, not a shipping choice.
The adapter exposes bounded primitive results and fixed errors. Its Linux
lifetime checks observed the library mapping present during a connection and
absent after closure, followed by a successful reopen. Mapping absence does not
measure resident-memory savings or establish a universal process-memory bound.

The first binding selection recorded four passes and one failure: a null handle
produced the wrong error type. Corrected v2 passed all five binding checks.
Subsequent lifecycle review found that `sqlite3_close` alone was insufficient
before unloading the runtime. V3 closes the connection, calls `sqlite3_shutdown`,
then unloads the library; uncertain cleanup retains ownership. V3 compiled
successfully with C source SHA-256
`5209d5b858215f7d8bdbfa3eb1237116fcaa7f1c7fbdc8a5cd60eb4ef3a9198c`.

The [official SQLite initialization/shutdown contract](https://sqlite.org/c3ref/initialize.html)
requires `sqlite3_shutdown` to run on a single thread, after all connections are
closed and other SQLite resources are deallocated. A shipping adapter therefore
needs an exclusively owned runtime and complete worker/lifecycle review; it must
not shut down an arbitrary system library potentially shared by other consumers.

## Functional evidence and retained fixture failure

The qualification uses private copies of the current compiled
[NativeTelemetryStore](../../studio/electron/telemetry-store.ts) and
[delivery implementation](../../studio/electron/telemetry-delivery.ts), redirecting
only the SQLite import and relocating fixture paths. The surrounding ownership,
permission, policy/company, generation/revision, contribution, spending and final
handoff code remains intact. Tests cover Python-compatible shared SQLite state,
commit/rollback, read-only behavior, query bounds, foreign/closed handles and
nonwaiting refusal behind a Python writer, alongside the existing privacy and
delivery cases.

| Retained stage | Result |
| --- | --- |
| Original v1 bindings | 4 passed / 1 failed; null-handle error type, 506.315 ms. |
| Corrected v2 bindings | 5 passed / 0 failed, 500.891 ms; predates the shutdown correction. |
| V3 compilation | Exit 0 after the required shutdown-before-unload change. |
| V3 staged store/delivery selection | 41 total: **38 passed, 2 Windows-only skips, 1 fixture failure**, 19.302 s. |
| Isolated corrected review-scope case | **1 passed, 0 failures or skips**, 1.628 s; only the staged wire-v2 file URL changed. |

The staged failure occurred before the company-scope handoff assertion: the
fixture had not relocated its relative wire-v2 JSON URL. Its original failed
receipt remains retained. Only that failed case was rerun after correcting the
staged URL. Together with the unchanged original results, this establishes
**39 functional passes and 2 Windows-only skips across the two runs**; the
original selection remains a failed run.
These are component/functional checks, not a renderer resource benchmark,
installed native-matrix acceptance or production telemetry qualification.

## Decision and remaining gates

The prototype does not replace `node:sqlite` in the product. Any shipping adapter
must pin and package a reviewed, exclusively owned SQLite runtime for all six
targets; system-library availability is insufficient. Remaining work includes
complete API/worker/finalizer/error-path review, Python compatibility, native
artifact and supply-chain validation, licensing/security-update ownership and
actual platform qualification. Preserve the shared private database, fresh
permission/policy checks, nonwaiting coordination and existing desktop lifetime;
no new daemon, required local memory engine or positive permission cache is selected.

No renderer benchmark, collector activation or resource-budget revision was
performed. The **2 MiB added RSS per participating process / 0.5% of one core**
gates remain unchanged and unaccepted, alongside full wire, privacy and utility
qualification.

Separately, all six 4.46.15 native jobs failed: four Linux/macOS package verifiers
required obsolete wire-v1, and both Windows npm jobs reached ten minutes.
Subsequent [release-guard checks](2026-10-26-telemetry-release-guards.md) reproduced
native watcher/handoff contention and qualified a source correction plus the
active-resource fix. These checks do not adopt this adapter. 4.46.16 remains
held before dispatch; its source CI passed. Public availability remains 4.46.13
at this checkpoint; see [release status](../RELEASE_STATUS.md) for later gates.

## Original SHA-256 evidence

| Retained evidence | SHA-256 |
| --- | --- |
| Declared plan | `6eacaf94b92300ea980f95c90dff8abd04932920f02eec38ed90bd730aabeb1b` |
| Original v1 binding result | `ffa26729a96eb27c866241bda35c6e1ee162112d96734afde5778f72d553acdd` |
| Corrected v2 binding result | `d4b5978fef65248f7b4e7a5e35b49ea1d6d834a1a66d2acfd079787f9f6fd1fd` |
| V2 lifecycle review | `e91dd0d8d89020a211f9fc1d1447c6ff3cb8cc7e3487cd48094cd9e365164b4e` |
| V3 compiled private binary | `bd957429f4b4ad79fa5320ad6ef8fdb47a3733350205ec9d4909b6d017f89c33` |
| Initial staged input manifest | `04aef2652078d00f902bf8702f67462c1c354069969006d6bd5f84ac10bd7726` |
| Original staged functional selection | `49b8e78bc0d16feb703b3eded341d789da380b04f449827c7458a6d364d9a9d6` |
| Isolated rerun and exact fixture-change receipt | `78e47087958f19947c2f2f24cab8c985fbb03027e51e3bec2b692917440f80aa` |
| Isolated passing test log | `3d6b7c3728d466402cb36f5d53a1204db1638c6da362f642f9427249eb2520b0` |
| Saved official SQLite document | `5419ec459d7f4608621e8312e5766c1650efff5eeaba9e698b4c320d87176f88` |
