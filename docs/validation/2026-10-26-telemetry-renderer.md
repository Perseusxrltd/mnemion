# Telemetry renderer and IPC source journey

**Source validation, 26 October 2026, 00:04:19 UTC.** All three functional
variants passed in the real development app: collection unavailable, explicitly
opted out, and enabled in the isolated fixture. **Resource acceptance remains
false.** V08 remains Building; production collection/destination/route stay
false/null/null. This is not an installed-platform or release qualification.

## Functional scope

The [Python runner](../../deploy/probe_telemetry_renderer.py) launches the
[Electron probe](../../studio/electron/scripts/probe-telemetry-renderer.mjs)
with the actual application, sandboxed preload, native session handle, default
renderer measurement wrapper and IPC. The runtime was **Electron 44.9.3 /
Node 24.22.0, Linux x64**, with renderer Node integration disabled.

Each variant completed real onboarding through the workspace connection form,
then **128 save/fetch/lexical-recall cycles** through the renderer SDK: **384
memory requests plus three onboarding/UI requests, all 387 successful**. Each
saved memory was fetched unchanged and found by lexical recall. These were
scripted SDK calls in the renderer, not individual UI clicks for each memory.
The disposable API and PostgreSQL used a four-dimensional protocol fixture;
there were no model calls or production memory operations.

| Variant | Accepted local telemetry writes | Accepted TLS reports | Spent reservation |
| --- | --- | --- | --- |
| Unavailable | 0 | 0 | 0 |
| Opted out | 0 | 0 | 0 |
| Enabled fixture | 66 | 1, with a four-byte body | One, 65,536 bytes |

The enabled lease was cleared and its private database was **24 KiB**. Fixture
content and the workspace key were absent from the retained queue. No page
errors or forbidden collector metadata were recorded. All three copied input
inventories were byte-identical, with **2,046 entries**, before the explicit
fixture configuration. Only disposable copies received an enabled disclosure,
loopback destination and unmetered declaration. Actual policy, pressure checks,
storage and transport remained in the exercised path. No aggregate was
published, and the production disclosure was unchanged.

## Resource observations

The [read-only analyzer](../../deploy/report_telemetry_renderer.py) binds the
original receipt and compares Electron processes present at both measurement
boundaries. The three runs were sequential observations, not stable estimates
of additional telemetry cost.

| Variant | Elapsed time (ms) | Electron process CPU (ms) | CPU difference from unavailable (ms) |
| --- | --- | --- | --- |
| Unavailable | 90,988 | 4,850 | — |
| Opted out | 85,186 | 5,390 | +540 |
| Enabled | 87,500 | 5,890 | +1,040 |

The descriptive enabled difference is **1,040 / 90,988 × 100 = 1.143% of one
core** over the unavailable baseline interval; the opted-out comparison is
0.593%. These comparisons do not isolate telemetry CPU from runtime variation.
They do not qualify the unchanged **0.5% of one core** target.

The following values are **enabled minus unavailable differences in growth**,
in bytes, from the analyzer. Ending growth and sampled-peak growth are separate
quantities; neither is a stable per-process estimate of telemetry overhead.

| Electron process type | Difference in ending RSS growth | Difference in sampled-peak RSS growth |
| --- | --- | --- |
| Browser/main | +1,560,576 | +3,174,400 |
| GPU | −278,528 | −12,288 |
| Utility/network | +557,056 | 0 |
| Tab/renderer | +6,533,120 | +2,170,880 |

The Electron table uses recorded work milestones, not continuously measured
peaks. Working-set/RSS sums can count shared pages more than once. A separate
**100 ms process-tree sampler** included observed helper descendants: seven,
eight and seven processes across the respective variants. It can miss
short-lived helpers, so sampled helper CPU is incomplete and is not included
in the Electron CPU comparison above. Negative differences are run variation,
not demonstrated memory savings. The interval includes connection and cold
work, with no forced garbage collection or idle padding; it is not a complete
startup-cost measurement. The **2 MiB added RSS** target is unchanged and
unaccepted. Favorable individual samples do not close either resource target.

## Preserved harness failures and provenance

R1 timed out waiting for the welcome heading without recording the selected
URL or DOM; its precise cause remains unassigned. R3 definitively selected
DevTools during app-window selection. R2 attempted a direct module import
outside Vite's serving allowlist. R4 checked an incorrect native-handle prefix.
These are retained probe failures, not established product bugs. R5 selected the owned app origin,
used a normal Vite export module and checked the actual native-handle schema.
The successful fixture closed the app/collector and removed isolated profiles
and certificate material; cleanup passed.

| Retained evidence | SHA-256 |
| --- | --- |
| R5 functional receipt | `7de9d729c3ab25ee5a15ae563e27f07f63a6df494b74f35b5f356e9f1787da75` |
| Derived resource analysis | `3597106a4c760f4ec7321afebbd71f91e2df97fdc64eb2c493036869f3311ee5` |
| R5 cleanup | `1dfdad0691c70f0fcdaad9a0e56f94675038eaccb5de8e0393914569586d75a1` |
| Each of the three input inventories | `5cd8d89f8f89533deb791d354403731558080674a880ee73cf712edddff0239f` |
| R1 probe log | `0053a3447166dd0d27f1ff38651d06493ede461c2dd7d0e7d6d258526086db98` |
| R2 probe log | `2ec9b608dc3bd06de9b69fc4aa56fe15123d38f6b7bf0c80e770ed99c12f4a23` |
| R3 probe log | `d89cff85677ab5fb70c853f27439a76ac15cdfb1803ea57db7e7ea9e2d99bb6c` |
| R4 probe log | `f29a11a4254acc43d827b0e516659910c36709eb4c31555fa5173b06927117c3` |

Earlier [memory-workload](2026-10-25-telemetry-memory-profile.md) and
[denial-I/O](2026-10-25-telemetry-denial-io.md) observations keep their original
scope. Installed native/web journeys, stable whole-feature resources,
whole-wire costs, production ingress/privacy and complete V08 acceptance remain
open. All 66 requirement texts and states are preserved.
