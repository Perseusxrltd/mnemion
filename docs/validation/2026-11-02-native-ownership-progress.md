# Native ownership progress — 2 November 2026

First original outcomes through 2026-11-01T23:57 UTC. This page records the original runs. Later source changes are outside those results. Original failures stay on record, with no unchanged native rerun.

Compilation only builds. An injected fixture runs real native processes and filesystem operations on the disposable runner. Its Security API outcomes are injected, and no real Keychain is accessed. Real host acceptance is a Windows owned root and census, a Mac Keychain with signing and approval, or Linux BPF admission with owned lifetime, accounting, and resource checks. Passing compilation, supervision, and cleanup do not yet qualify resource accounting or real credential recovery. All 66 requirement states are unchanged. V08 remains Building and production telemetry stays off. Isolated milestones, not a shipped resource budget, whole-lifetime CPU, RAM or network coverage, fleet statistics, or complete professional-product acceptance. See the [runtime efficiency contract](../implementation/runtime-efficiency.md).

## Public 4.46.64

Source [`23a3fc8684f573a93abc7b4f7168f159db90c2e4`](https://github.com/Perseusxrltd/mnemion/commit/23a3fc8684f573a93abc7b4f7168f159db90c2e4). All six public upgrade targets passed in [run 41360943307](https://github.com/Perseusxrltd/mnemion/actions/runs/41360943307). Website metadata passed in [run 41360940801](https://github.com/Perseusxrltd/mnemion/actions/runs/41360940801). The [release note](../releases/4.46.64.md) does not prove a complete product or actual user-device adoption.

## Windows — failed

Source [`98562ff2106fa1edcf5ef4e4d94d98ab4e3efe1f`](https://github.com/Perseusxrltd/mnemion/commit/98562ff2106fa1edcf5ef4e4d94d98ab4e3efe1f), [run 41362333780](https://github.com/Perseusxrltd/mnemion/actions/runs/41362333780), [`windows_etw_lifecycle.py`](../../deploy/windows_etw_lifecycle.py). Later review edits are not this run and are not qualified.

The run failed. Start, Open, Process, Stop and Close succeeded. Fixture evidence was 743 callbacks, 407 retained, and zero losses. Job, supervisor and ETW cleanup succeeded. Owned-root creation timestamp binding failed. Per-event versions were projected as one common version. The job reported 2 processes against 1. Root identity and census are unproven. No fitted clock tolerance, no acceptance of 2, and no change to production accounting or resource gates.

## Mac — compiled; injected fixture failed; host not run

ARM64 macos-26 owner and ordinary-helper compilation passed in [run 41362365778](https://github.com/Perseusxrltd/mnemion/actions/runs/41362365778). The [1 November compile-only report](2026-11-01-macos-keychain-compile.md) is unchanged.

Injected [run 41363656552](https://github.com/Perseusxrltd/mnemion/actions/runs/41363656552) ([`fixture_inject.c`](../../deploy/macos_keychain_proof/fixture_inject.c), [`FIXTURE_OWNER.md`](../../deploy/macos_keychain_proof/FIXTURE_OWNER.md)) then compiled its workers. The forbidden-symbol gate and first eight wrapper cases passed. Ninth, copy-foreign-store, correctly refused the foreign store, then failed: a stale exact-order expectation omitted mandatory bound-store path revalidation and stopped later cases. Replaced-entry and descendant owner checks and stall hygiene passed. Owner exit was 1; supervisor and owner cleanup completed. No native Security call ran. The correction must keep exact order and every security guard. A new runtime is still required and is not accepted. No Keychain, signing, login prompt, power loss, or [issue 50](https://github.com/Perseusxrltd/mnemion/issues/50) acceptance. [29 October requirements](2026-10-29-macos-keychain.md) stay open.

## Linux — compile and guard passed; admission failed

Source [`deac177a124bc4a9766418356eac881c53f76be2`](https://github.com/Perseusxrltd/mnemion/commit/deac177a124bc4a9766418356eac881c53f76be2), [`admission_guard.c`](../../deploy/linux_bpf_lifetime/admission_guard.c), [`BUILD.md`](../../deploy/linux_bpf_lifetime/BUILD.md).

Corrected compilation [run 41359379562](https://github.com/Perseusxrltd/mnemion/actions/runs/41359379562) passed on x64 and ARM64. The unprivileged guard [run 41359745800](https://github.com/Perseusxrltd/mnemion/actions/runs/41359745800) passed on both: child exit 0, cleanup confirmed 1, ownership unresolved 0, cgroup_evidence 0, bpf_evidence 0. Zero cgroup and BPF evidence is not a collector. Admission-only [run 41361356839](https://github.com/Perseusxrltd/mnemion/actions/runs/41361356839) failed on both at `btf__parse`, before prototype check, BPF load, attach, or the fixture. Kernel 6.8.0-1070-azure and libbpf-dev 1:0.5.0-1ubuntu22.04.1 were observed. Parse errors were discarded, so kernel, permission, and dependency are not a proven cause. Fixed diagnostics are in progress. Receipt consistency and cleanup passed. No supported resource collector.

## Remaining

Windows: supported process-generation binding and the unexplained census. Mac: a corrected injected suite, then the real Keychain, signing, and user-hardware flow. Linux: retain the parse cause, then BPF admission, owned lifetime, accounting, and resource checks. Power-loss recovery and full telemetry acceptance stay open where they already apply.
