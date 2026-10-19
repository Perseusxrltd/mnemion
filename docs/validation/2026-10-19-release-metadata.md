# Delayed GitHub release job metadata

On 19 October 2026, release build `39279191287` (4.19.0, source
`7ca31a878c46ab61ea73d2712ee925f5c99260a8`) completed successfully, including
installed-hosting receipts for all six platform/architecture targets. GitHub's
job endpoint continued reporting Windows ARM64 as in progress after its runner
had finished. Verification `39286168514` correctly withheld publication before
downloading assets because the workflow and job results disagreed.

Once GitHub reported actual completed/success job results, the unchanged strict
resolver passed. Only the failed verification was retried. Verification and
publication succeeded; 4.19.0 was published at `2026-10-19T16:51:51Z`. Website
metadata synchronization `39289148212` passed. Public desktop update rehearsal
`39289153363` was still running at this observation; consult the generated
release ledger for its result. Frozen release source and binaries were unchanged.

The verifier now accepts an explicit wait of at most 1,200 seconds for delayed
job metadata, with 15-second polling. Normal callers still default to no wait.
The source commit and run attempt cannot change during a wait. Wrong repository,
workflow or event, changed source, and failed/cancelled/skipped/timed-out gates
fail immediately. Actual completed/success results remain mandatory for every
job; finished runner steps and uploaded artifacts are not alternative evidence.
Asset downloads, signature checks and publication retain their existing guards.

Validation: `service_tests/test_artifact_verification.py` and
`service_tests/test_release_automation.py` passed **66 tests** in 0.76 seconds.
The cases cover delayed/missing job listings, expiry with no downloaded bytes or
receipt, terminal failures, changing source/attempt/repository, fixed wait bounds
and the existing asset/source/publication checks. Ruff lint and format passed.
This is a release automation change; no desktop version bump or replacement
build is needed.
