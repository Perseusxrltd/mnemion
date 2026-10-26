# Native telemetry handoff and release-resource guards — 26 October 2026

Source corrections address a native telemetry watcher competing with its own
final handoff and a package verifier requiring the retired wire format. Linux
and actual Windows x64 component checks passed. **Normal six-target release
qualification remains pending.** V08 remains Building; collection/destination/route
stay **false/null/null**, with all 66 requirement texts and states unchanged.

## Preserved release failures

[4.46.15 run 40293480655](https://github.com/Perseusxrltd/mnemion/actions/runs/40293480655)
ended in failure across all six native jobs:

| Targets | Recorded failure |
| --- | --- |
| Linux x64/ARM64 and macOS x64/ARM64 | Package verification required obsolete `telemetry-wire-v1.json`, while the builder supplied wire v2. |
| Windows x64/ARM64 | Native npm tests reached their ten-minute timeout. |

The original logs remain retained. 4.46.16 was held **before start or dispatch**
and remains frozen; its [source CI 40293301106](https://github.com/Perseusxrltd/mnemion/actions/runs/40293301106)
subsequently passed. At this checkpoint, public availability remains 4.46.13;
see [generated release status](../RELEASE_STATUS.md) for later qualification.

## Reproduced handoff contention

A local Windows x64 test using Node **25.2.1**, Python **3.13.11** and the actual
compiled ACL helper reproduced a first send returning `suppressed` instead of
`delivered`. That failed run and its successful cleanup are preserved. A separate
Linux regression held the actual SQLite read slot and reproduced the same refusal.

The active `watch()` policy read and `guardedWrite()` competed for the single
nonwaiting storage slot while asynchronous Windows permission checking yielded.
The [native sender](../../studio/electron/telemetry-transport.ts) now stops and
drains its own watcher before the mandatory fresh handoff check, then resumes
watching after a successful handoff. The original five-second socket deadline
and owner cancellation remain active during that transition. Fresh policy and
opt-out checks, one database handle, spent allowance and final lease/socket
cleanup remain required; no positive-consent cache or extra storage connection
is introduced. The [standalone watcher's](../../studio/electron/telemetry-delivery.ts)
default cancellation behavior is unchanged.

The [TLS fixtures](../../studio/electron/scripts/test-telemetry-transport.mjs)
now race expected peer arrival against delivery completion and a finite timeout.
A suppressed operation therefore reports its outcome instead of leaving the
fixture awaiting a peer indefinitely. The delayed-read regression also verifies
that Python opt-out during the read still prevents the final handoff.

## Active package resources

The sender, builder and verifier share one
[active wire-resource definition](../../studio/electron/telemetry-resources.ts).
The [resource copier](../../studio/electron/scripts/telemetry-resources.mjs)
supplies the current format and removes retired wire files during incremental
builds. The [packaged-resource verifier](../../studio/electron/scripts/verify-resources.mjs)
uses the same definition. The checks still reject a missing active resource;
an old wire file cannot satisfy the gate.

## Scoped validation

| Check | Result |
| --- | --- |
| Linux source selection | **37 passed, zero skips**: 17 transport, 17 delivery/privacy and three clean-resource packaging cases. |
| Windows x64 transport selection | **17 passed, zero failures/cancellations/skips**, TAP duration **25.561 s**; actual compiled ACL helper, Node 25.2.1/Python 3.13.11, cleanup verified. |
| Electron build | Passed, exit 0. |

The Windows deadline case observed peer TCP closure **9.607 ms after the real
deadline**, without relaxing its bound. These are recorded component outcomes,
not installed Windows ARM or other native-platform acceptance, a renderer
benchmark, stable resource evidence or production collection qualification.

The candidate also carries forward the
[host-intake ownership change](2026-10-26-telemetry-host-requests.md), whose
unchanged earlier evidence comprises 47 Python and 17 Node checks. The separate
[SQLite adapter feasibility study](2026-10-26-telemetry-storage-adapter.md) retains
39 functional passes and two Windows-only skips; that prototype is not an adopted
backend or evidence of RSS savings. The **2 MiB / 0.5%** resource gates and full
coverage, wire, privacy and utility acceptance remain open.

## Original SHA-256 evidence

| Retained evidence | SHA-256 |
| --- | --- |
| Original Windows failure and cleanup receipt | `46d32eb80993364ad52e6444399d72b3ea81a84e3d23d87a01e73c3f7c66a9fd` |
| Original Windows failure log | `26eb420bf6f33a5cd794035caba9672ac2c76b0562f735f907e7e1c90cf6b97f` |
| Original held-read reproduction receipt | `90d34a61a0355a56ee038e4eb589b76b8c81faafd0cde65d7a6e42bb094a6737` |
| Original held-read failure log | `af3a179d1b1a16d1400f3c5e800627e960278dbace41a116f94f0fc0a981c848` |
| Passing Linux selection | `00a6016bed640a0c5a5124743e00aa9d89cc26511af5a5c408fa48080c3d4e61` |
| Passing Windows receipt and input hashes | `0e48c8ffaeaee52f536cf13d643cff59f53b3614ea79a06b5e610600c411d30c` |
| Passing Windows test log | `95a22658fd95b9d9938cd713cdbf1d0d7a4f53e3f229af3b92550c0a84226fb4` |
| Electron build receipt | `1bc9bda50a79b3904207345ae84a895d3466ce308d23b6445f07cafada615bb9` |
