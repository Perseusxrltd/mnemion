# Linux package scanner initialization recovery

**26 October 2026, 4.46.26 source follow-up.** Focused tests and one fresh local
pinned-scanner acquisition/scan passed. The original hosted-runner exception
remains undiagnosed, and native Linux release acceptance remains open.

## Original failure retained

The 4.46.24 [native run 40372679179](https://github.com/Perseusxrltd/mnemion/actions/runs/40372679179),
source `49c6459fc93b40773294b45f31f8098f6caff3e6`, failed generated-content scanner
initialization on [Linux x64 job 121750616694](https://github.com/Perseusxrltd/mnemion/actions/runs/40372679179/job/121750616694)
and [Linux ARM64 job 121750617104](https://github.com/Perseusxrltd/mnemion/actions/runs/40372679179/job/121750617104).
Both logs reported only “Secret scan could not complete; publication remains
blocked.” Their retained receipts have `passed: false`, no scanner identity and
no canary fields. The failed x64/ARM64 artifacts are 12674011414/12673444050.

The raw exception was suppressed. This does not prove a secret finding, a
specific HTTP status, DNS failure or archive-integrity error. A successful local
WSL fetch is a different network vantage and cannot diagnose those hosted jobs.
Their original logs and receipts remain unchanged.

## Narrow recovery and safe diagnostics

[Scanner acquisition](../../deploy/secret_scan.py) now permits **one additional
download attempt** for classified DNS, timeout, connection or incomplete-read
errors, or HTTP 429/500/502/503/504. This retries acquisition only. TLS errors,
unrecognized errors, changed digests, oversized content and scan findings cannot
use that retry. The existing pinned archive, 32 MiB download cap, private cache
permissions, executable checks, input verification and six canaries remain
mandatory. No scanner rule or content exclusion changed.

A 60-second monotonic download window is checked before and after chunks and
between attempts. Configured blocking I/O timeouts are capped at 30 seconds;
blocking DNS/OS behavior prevents promising a strict total wall-clock bound.
This window is separate from the actual scanner process timeout.

Failure receipts now identify fixed `snapshot`, `scanner_initialization`,
`scanner_canary`, `content_scan` or `input_verification` stages and a safe code.
Recognized download errors may include a bounded HTTP status and attempt count.
They do not serialize raw exception text, URLs, headers, paths, credentials or
matched content. An unsuccessful scan still blocks publication.

## Source validation

`scanner-recovery-qualification.json` and
`scanner-integrity-and-recovery-tests.log` record **37 focused tests passed,
zero failures**, with formatting/lint checks passing.

`source-qualification.json` and `generated-content-scan.json` record a real
**fresh empty-cache acquisition of pinned Gitleaks 8.30.1**, execution, **all six
canaries passed**, and **625 generated frontend/Electron files scanned with zero
findings**. The actual scan ran locally on WSL/Linux x64. Its canaries cover
archived keys, binary-first keys, annotation-adjacent keys, decoded metadata and
both public-FIPS adjacency cases. Size/digest/permission protections and scan
rules remained in place.

Pinned archive SHA-256:
`551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`.
Actual scan receipt SHA-256:
`e59d57f462b810fefa0ae04bff88d650e622880208ac9b9eb62333af3505d326`.
Rules SHA-256, unchanged from the failed receipts:
`7ce0fe949411fb06aa7bc332e14dcc2044ed6bd1d2db26d628012565be65e1aa`.

These checks establish the source recovery and diagnostic boundaries. They do
not reproduce the original hosted exception, prove a live transient retry was
needed, or qualify the next native Linux release. Existing successful targets
and failed evidence are preserved; no existing native run was replayed for this
local validation. Follow [release status](../RELEASE_STATUS.md) for real gates.

All 66 requirement states, V08 **Building/off**, privacy policy and resource
budgets remain unchanged. This release-tooling change does not activate telemetry.
