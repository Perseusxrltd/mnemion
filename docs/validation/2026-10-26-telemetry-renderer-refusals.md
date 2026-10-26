# Renderer telemetry refusal hints

**Source checkpoint, 26 October 2026.** Focused checks and the later compiled
CI app journeys passed for bounded renderer refusal hints. **Resource acceptance
remains false.** The stopped local probes and two failed CI attempts are retained
below. V08 remains Building and production collection/destination/route stay
false/null/null. The last verified public release is 4.46.6; see
[automatic release status](../RELEASE_STATUS.md) for availability.

## Source behavior

The [snapshot reader](../../studio/frontend/src/workspace/telemetry-refusals.ts)
can reuse a native `null` refusal for the same reviewed workflow for **at most
one second from the original request's monotonic start**. It never caches a
positive policy decision or permission stamp. A slow reply cannot start a new
one-second window, and clock reversal invalidates reuse. At most 128 workflow
slots are stored; unknown or additional scopes receive fresh reads.

The [app policy bridge](../../studio/frontend/src/workspace/telemetry-policy.ts)
clears hints before configuration and again when that request finishes. An
epoch prevents an older reply from restoring a cleared hint. A new enable
from another process can still lose optional observations for up to one second;
this bounded omission is deliberate. It cannot authorize collection. Status,
admitted observations, reservations and final handoffs retain their fresh
policy and storage checks. This change adds no positive browser policy cache.

The shared [workflow wrapper](../../studio/electron/telemetry-workflow.ts)
returns immediately on a synchronous refusal, avoiding an unnecessary Promise
and deferred workflow creation. Hints expire on subsequent work; there is no
timer or idle polling for this cache. These source changes do not establish a
measured CPU or RAM improvement.

## Focused checks and incomplete probes

| Source selection | Result | Duration |
| --- | --- | --- |
| Frontend | 97 passed, zero failures/skips | 7.4507 s |
| Selected desktop checks | 39 passed, two Windows-only skips; 41 total | 22.4842 s |

Frontend and Electron source builds passed. The tests cover scoped expiry,
fresh positive reads, immediate configuration invalidation, late replies,
clock reversal, bounded scope storage and synchronous refusal. They do not
qualify an installed app or the full resource limits.

The refusal batch's **r1 development attempt** was deliberately stopped with
`SIGINT` at **01:03:58 UTC** because host memory was limited. The partial
evidence is retained and is not a completed functional or resource result.
Cleanup verified isolated-profile removal, collector shutdown, certificate
cleanup and unchanged production disclosure.

At **01:10:05 UTC**, the **r2 compiled-probe guard** refused before launch:
available host memory was **1,063,481,344 bytes**, below its **1 GiB
(1,073,741,824-byte)** admission floor. Its fixed reason was
`insufficient_initial_host_memory`. This is an admission refusal, not an app
resource measurement or an out-of-memory crash.

Following these local refusals, the harness moved to a compiled multi-entry UI
and static server on a clean CI runner. The completed CI journey is recorded
below. The [earlier renderer journey](2026-10-26-telemetry-renderer.md) remains
historical evidence for its own source; its measurements do not qualify this
optimization.

| Retained evidence | SHA-256 |
| --- | --- |
| Frontend tests | `5199b8284bb9fef698aa4bc1b3ea46148c546a9604a80dbf1cdfc5bc16fff75f` |
| Desktop tests | `9c4edd84e506cf624bdf606fb27cc18a6b053c24035841d9423f584fe8737427` |
| Frontend build | `ff1ae244d0f21e0ce381e55e1b5a2411f67e548ad9b97c322cbee6751b39f13c` |
| Electron build | `bf78e1c53f7172ce6d0c04a02110416cbca757522bc9bb920a149779ef2f2d8f` |
| r1 stop request | `f0897b6a6be8aca4994d7a5e8b59370130295b6f3da9e904f8e6c0668fbee139` |
| r1 cleanup | `1dfdad0691c70f0fcdaad9a0e56f94675038eaccb5de8e0393914569586d75a1` |
| r2 pre-launch guard | `60804755ba6b294f1c6ecbff8dd84edf31b51ba6225997b1308aff9d3b3a4c10` |

The **2 MiB added RSS and 0.5% of one core** targets remain unchanged and
unaccepted. Installed-platform, whole-wire, production ingress/privacy and
complete V08 acceptance remain open. All 66 requirement texts and states are
preserved.

## First compiled CI observation

[Run 40253331957](https://github.com/Perseusxrltd/mnemion/actions/runs/40253331957)
checked out source `b1232c760b2179f953dfac110b86b45af5a497e4`. The compiled
frontend built successfully, then the harness stopped before launching Electron:
its shared-module verifier traversed only static imports, while the app loads
workspace and privacy routes lazily. All owned fixtures were removed, the
collector stopped and production disclosure was unchanged. This run provides no
app-journey or resource acceptance.

The verifier now traverses both static and lazy imports. It still requires one
copy of each policy/client module, reachable from both the app and measurement
entry, and reports fixed module/chunk details if the check fails. The original
failed build log and cleanup remain retained; the later completed CI result is
recorded below.

## Clean-runner executable preparation

[Run 40254401380](https://github.com/Perseusxrltd/mnemion/actions/runs/40254401380)
used source `8a81ce68f0060cb06693cb44c0f381e907911cd6`. Compilation and the
shared-module checks passed. Electron then could not launch because its native
executable had not been downloaded. The installed Electron 44.9.3 package has
an explicit installer command and no automatic postinstall script. Cleanup
again removed the owned profiles and stopped the fixture collector.

The diagnostic workflow now explicitly installs the locked Electron runtime.
The harness also checks for its executable before constructing the database or
collector fixtures. No collection or resource pass is inferred from either
failed CI attempt.

Pushes limited to these six explicitly listed diagnostic files and documentation
now leave the product's native/service queues free. Runtime changes, release
workflows, unknown files, unavailable Git history, pull requests and actual
release/manual validation retain the full checks. Five real-Git selection tests
and the existing website-content checks passed: **28 tests in 3.37 seconds**.
This changes check selection, not the release acceptance gates.

## Completed compiled CI journey — 26 October

[Run 40255365121](https://github.com/Perseusxrltd/mnemion/actions/runs/40255365121)
completed successfully for source
`2d43b1940da913f8a315b7c9bbfe99d470b2038c`. Its workload receipt is dated
**01:45:45 UTC**. All three compiled source-app journeys passed on **Linux x64,
Electron 44.9.3 / Node 24.22.0**. The app was not packaged or installed.

Each variant used actual onboarding, the shared renderer SDK, sandboxed preload,
native session handle and IPC, with **128 real save/fetch/lexical-search cycles**
against disposable API/PostgreSQL fixtures. Each recorded **387/387 successful
requests**, including three onboarding/UI requests, with saved and recalled
results verified. Memory operations were scripted renderer SDK calls. Compiled
module checks confirmed that the app and probe shared their policy/client
modules; the three copied source inventories were identical.

| Variant | Accepted local telemetry writes | Accepted TLS reports | Spent reservation |
| --- | --- | --- | --- |
| Unavailable | 0 | 0 | 0 |
| Opted out | 0 | 0 | 0 |
| Enabled fixture | 66 | 1, four body bytes | One, 65,536 bytes |

The enabled lease was cleared, its database was **24 KiB**, and fixture content
was absent from its queue. No page errors, forbidden collector metadata, model
calls or published aggregates were recorded. Cleanup verified all four recorded
conditions: isolated profiles removed, collector stopped, temporary certificate
profile removed and production disclosure unchanged. Only the isolated fixture
enabled collection.

The analyzer binds the exact workload receipt. These **enabled minus unavailable
differences in RSS growth** are descriptive measurements, not absolute app RSS:

| Electron process | Difference in ending RSS growth | Difference in sampled-peak RSS growth |
| --- | --- | --- |
| Browser/main | +2,793,472 bytes | +3,186,688 bytes |

Both main-process differences exceed the unchanged **2 MiB** target. Across
Electron processes present at both boundaries, CPU was **2,050 ms enabled versus
1,880 ms unavailable**: **+170 ms**, or **0.224% of one core** over the unavailable
variant's **75,769 ms** interval. This single sequential comparison does not
isolate causal telemetry overhead or qualify the **0.5%** CPU target. Different
source/build conditions also prevent treating the earlier development run as a
controlled before/after performance comparison.

Ending and sampled-peak growth remain separate quantities; RSS sums can count
shared pages more than once. The **100 ms** external sampler can miss short-lived
helpers. The workload includes connection and cold work, with no forced garbage
collection or idle padding. `resource_acceptance` remains **false** in both the
workload and analysis. Stable whole-feature resources, installed-platform,
whole-wire, production ingress/privacy and complete V08 acceptance remain open.

| Original CI artifact | SHA-256 |
| --- | --- |
| Source identity | `50e3fcfef233f11c68f0b5ad54512899d7a3fa781452621aeb0fd02f1adf12bd` |
| Workload receipt | `a72444ab53b14d79b159e37e2bc25988ac9f540a3a10455cb43af987215b5469` |
| Derived summary | `d49b6bdf43ec3285bfd4495bdf7236bb3983749206df3fd54aaad96858913c39` |
| Cleanup | `1dfdad0691c70f0fcdaad9a0e56f94675038eaccb5de8e0393914569586d75a1` |
| Each copied source inventory | `b2bf2c58080078916a490728ac60b0b43fa384b193cc8d860b610dd8e211b976` |
