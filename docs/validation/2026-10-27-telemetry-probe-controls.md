# Native controls in telemetry app diagnostics — 27 October 2026

Commit `d56d578f7c9791fc43c64cc8178dca255682dc5d` changes four diagnostic/test
files. It requires genuine native privacy-control evidence alongside memory
workload results. Original Linux source-app run **40470335733 failed** because
the new validator incorrectly required disclosure acknowledgement after opt-out.
The retained work and later validator correction are described separately below;
product policy, resource limits and the failed workflow remain unchanged.

## Retained omission

The ordinary renderer fixture previously supplied an absent engine; only the
separate review journey used the real source kernel. Available builds could
therefore load privacy setup without proving that `telemetry.status` succeeded.
Memory API success alone did not verify this control.

The original report regression failed with **DID NOT RAISE ValueError** when
native setup evidence was missing: one failed case, with 32 deselected.
Separately, the actual compiled control returned no reply and reported
`source_helper_unavailable`. That reproduction launched no app, made no network
request and removed its disposable profile. The original checks and
`original-control-failure.json` remain retained.

This establishes a diagnostic acceptance gap, not a causal explanation for
earlier RSS observations. The [previous resource results](2026-10-27-telemetry-resource-roles.md),
including their overages and original limitations, remain unchanged.

## Required control evidence

The [runner](../../deploy/probe_telemetry_renderer.py) now uses the real copied
source CLI through the normal private-stdin bridge in every disposable mode.
It explicitly limits this diagnostic to Linux; it does not replace or qualify
an installed engine.

The [app probe](../../studio/electron/scripts/probe-telemetry-renderer.mjs)
observes normal `telemetry.status` calls without substituting replies or
changing consent. It retains at most 16 fixed status summaries, counts failed
and unfinished calls, and flags overflow. A generation-validity boolean is
recorded, not the local generation value. Existing measurement phases and cold
work remain; there is no added warmup, forced GC or pre-sample wait.

The [report verifier](../../deploy/report_telemetry_renderer.py) independently
requires:

| Declared fixture case | Required native setup result |
| --- | --- |
| Collection unavailable | Zero setup-control calls. |
| Opted out | At least one completed reply confirming user/effective disabled, reason `user_disabled` and disclosure acknowledgement **false**. |
| Enabled | At least one completed reply confirming user/effective enabled, reason `enabled` and disclosure acknowledgement **true**. |

Available-case replies must also confirm collection availability, ready storage,
the fixture's unmetered setting and a valid generation. These are the corrected
expectations: the initial validator wrongly required acknowledgement in both cases.
Counts must match replies exactly; missing, failed, unfinished, overflowing or
inconsistent evidence rejects the journey. Failure counters and completed
memory work remain available for inspection. Older receipts without this proof
remain readable with `setup_controls_verified=false`; no control acceptance is
invented for them.

## Checks and retained workflow failure

The initial stage passed **33 report tests in 1.34 seconds**, SDK and Electron
builds, and **19 separate private control assertions**. These remain historical
results from before the opt-out expectation was corrected. The private qualifier
also re-read six older results without adding native-control or resource
acceptance. Its initial import failure occurred before checks or app execution;
using the reviewed checkout corrected that fixture context.

The first background launcher omitted the explicit GitHub credential helper and
stopped at Git push with exit 128, before any workflow dispatch. Authorization
was already present. The corrected launcher dispatched only after verifying
that the original attempt had not dispatched. The failed launch is retained.

Original run **40470335733**, at the exact source above, completed **128 memory
cycles and 387/387 successful API requests in each of three cases**; cleanup
was verified. The ordinary journey is separate from allocation attribution and
counterbalanced resource qualification. Its actual native replies were:

| Case | Completed status calls | Failed / in flight | User/effective enabled | Disclosure acknowledged | Isolated collector reports |
| --- | ---: | --- | --- | --- | --- |
| Unavailable | 0 | 0 / 0 | No reply required | No reply required | 0 |
| Opted out | 1 | 0 / 0 | false / false | false | 0 |
| Enabled | 1 | 0 / 0 | true / true | true | One four-byte synthetic report |

Unavailable and opted-out cases also recorded zero telemetry writes. Opt-out
was correct: [policy.configure](../../mnemion/product_telemetry/policy.py#L518)
deliberately clears `disclosure_version` to zero on disable. The new diagnostic
expectation contradicted that policy. The original opted-out receipt retains
`setup_controls_verified=false` and `journey_completed=false`; the GitHub
workflow conclusion remains **failure**.

A regression using the real policy reproduced the validator rejection. After
correcting the expected acknowledgement, the complete
[report test selection](../../tests/test_telemetry_renderer_report.py) passed
**35 tests in 2.93 seconds**, and Ruff passed. The 35-test selection supersedes
the earlier 33 for the current validator. The private qualifier's expectation
was corrected too. No app rerun occurred and no original receipt was rewritten.

Independent retained-evidence analysis is complete. It verified the original
archive, **2,130 source inputs per case**, raw/native replies against the combined
receipt, cleanup and all recorded API successes. The corrected validators
confirm all three control states. Four additional private mutation assertions
reject retained acknowledgement after opt-out, absent acknowledgement while
enabled, effectively-enabled opt-out and an invalid generation. This limited
control reassessment leaves `qualified_full_workflow=false` and
`resource_acceptance=false`; the original workflow and opt-out journey flags
remain failed/false.

The original archive remains retained with SHA-256
`27f11cb4240485af73c7e659cbbb7fc7963c7d7b29982a0588fd90c9df3de359`.
The separate retained-controls assessment has SHA-256
`c5e2fcb89ca0ee4e35e0115452af0fe6f4cc9c5f7f00cb563a2c0284a73fa75b`;
its corrected summary is a new analysis artifact, not a rewritten original.

Source checks and builds do not qualify all-platform installed behavior,
resources or the full privacy path. The **2 MiB added RSS / 0.5% of one core**
ceilings remain unchanged, with no resource saving established. All 66
requirements and their states remain; V08 is **Building**, production
collection/destination/route remain **false/null/null**, and release CAs are
empty. The [canonical acceptance contract](../implementation/anonymous-product-telemetry.md#required-acceptance-evidence)
retains the remaining work.
