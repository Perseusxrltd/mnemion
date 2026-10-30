# CPU sampling boundary and macOS ARM admission follow-up

30 October 2026. Grok's source correction `def55b96` was adopted as `cbce7719`;
formatting with unchanged Python AST produced reviewed source `35613f45`.
V08 remains Building. All 66 requirements are unchanged. Production collection
stays off, hosting is unresolved and no fleet statistics are qualified.

Predecessor main `d8dc8a4a` passed
[CI 41087208753, attempt 2](https://github.com/Perseusxrltd/mnemion/actions/runs/41087208753/attempts/2).
Its initial macOS ARM hosted-runner capacity cancellation remains retained.
That CI result applies to the predecessor; this correction's evidence follows.

## Reproduced defect and correction

A bounded probe exercised the compiled admission helper with real CPU counters,
timers and monotonic time on Node 22.22.0/Linux x64. Network and thermal inputs
were isolated. Of 16 trials, one reached the post-wait check at 249.659417 ms
after requesting a 250 ms delay. The cache suppressed a fresh CPU sample:
`prepare` returned true with only one CPU counter read, while `cpu_unobserved`
persisted through reservation at 249.753258 ms. The owned timer was cleared.
This establishes a Node/Linux timing defect, not the original Mac cause or
Electron runtime qualification.

In the [original R3 run](2026-10-30-telemetry-resource-r3.md), macOS ARM's enabled
case completed 128 cycles with hosting ready, root exit zero and zero telemetry
attempts or reports. Its admission reason was not retained; that failure
remains unresolved.

The correction takes one fresh CPU sample after the existing prepare wait.
Ordinary reads remain cached. Counter validity, CPU/memory/network/thermal
gates, the wait and the owner's rate limit remain unchanged; no polling is
added. The attribution wrapper forwards the fresh-read argument.

An explicitly opted-in packaged resource probe can now retain one allowlisted
first-attempt outcome and optional guard. `MNEMION_TELEMETRY_RESOURCE_ADMISSION=1`
is required; normal launches leave it off. Unknown or malformed evidence stays
unknown, extra fields are discarded, and no telemetry wire fields change.
Instrumented runs cannot qualify the resource comparison.

## Scoped validation

On `35613f45`, one real Linux desktop build passed in 21.153 seconds using the
project compiler, native network build and normal staging. The staged helper
matches its source and all three compiled consumers import it. All 2,388
source inputs remained unchanged during the checks.

- 37 Node checks passed, including the deterministic early-timer regression:
  valid advancing counters admit work with two reads; unchanged or invalid
  counters remain constrained; the next ordinary read stays cached.
- 14 Python resource-boundary and controller-staging checks passed in 3.61
  seconds. Three receipt cases survived the actual JavaScript/Python projection.
  A complete-case fixture supplied the uninstrumented positive control; adding
  the diagnostic to any of its six case positions refused qualification.
- The original Windows worker passed three source Node checks and three pure
  Python checks. Its normal pytest invocation could not load `chromadb` from
  the shared test configuration; the pure helper checks used `--noconftest`.
  A repeated passing invocation is retained and is not counted again.

Follow-up source `4cfbf7d5` adds the `admission_diagnostic` boolean input to
the manual Installed telemetry delivery workflow. It defaults to false and
applies only to its resource-comparison step. Linux's delegated desktop
launcher now forwards the explicit `1`; absent, empty or other values stay
off without rejecting the normal launch. The generic service allowlist and
target selection are unchanged.

Three focused launch/workflow checks passed in 1.56 seconds. Parsing the actual
workflow confirmed the default and step boundary. All 226 desktop/shared/client
source files still matched the real build's inputs, so that build was reused.
For a targeted Mac diagnostic, select `targets=macos-26`,
`resource_comparison=true` and `admission_diagnostic=true`. Its retained outcome
is diagnostic evidence only; it cannot qualify the overhead comparison.

No installed matrix was replayed. Native coverage and the unchanged
[8 MiB/0.5% allowances](../implementation/telemetry-resource-budget-2026-10-30.md)
remain open. The existing [whole-product F06/R04 contract](../implementation/runtime-efficiency.md)
continues without a new milestone or performance qualification. Public hosting,
collector operation and useful fleet statistics need separate acceptance.
