# Mac credential fixture compilation — 1 November 2026

[Run 41346487519](https://github.com/Perseusxrltd/mnemion/actions/runs/41346487519),
attempt 1, compiled and linked the credential helper, parent and identity
diagnostic on both Mac architectures at source
`4c76ecac17771d424b8fe21ecae898696dbcc710`. All six compiler/linker invocations
returned zero. The workflow completed at **20:22:40 UTC**.

| Architecture | Runner | Job | Original receipt |
| --- | --- | --- | --- |
| Intel x86_64 | macos-15-intel | [124967295110](https://github.com/Perseusxrltd/mnemion/actions/runs/41346487519/job/124967295110) | [Receipt](2026-11-01-macos-keychain-compile/x86_64/receipt.txt) |
| ARM64 | macos-26 | [124967295431](https://github.com/Perseusxrltd/mnemion/actions/runs/41346487519/job/124967295431) | [Receipt](2026-11-01-macos-keychain-compile/arm64/receipt.txt) |

This qualifies compilation and linkage only. **No fixture binary ran.** The
workflow invoked neither `codesign` nor the `security` tool, changed no
Keychain, and did not use Electron. Generated headers contained explicit
compile-only placeholders. The linked programs were removed by the build
script; uploaded artifacts contain compiler logs, receipts and bundle plists.
The macOS 13.0 deployment flag is a build setting, not execution evidence on
that OS version.

The sealed-store guard, interaction bracket and durable-creation implementation
were linked but unexecuted. `fixture_store_cases.c` was neither linked into
this lane nor run. Its boolean UI/marker cases do not exercise the real
wrappers, filesystem durability, locking or process restart.

The next fixture must drive those actual guard functions with injected API
results and real private-file operations under an external bounded owner.
Real throwaway-Keychain operation, signing and certificate measurements,
frozen-helper parent A/B assembly, installed restart/update and the affected
user's approval journey remain separate work. This compilation does not
establish cross-update Keychain trust or Chromium/Electron interoperability.
[Issue 50](https://github.com/Perseusxrltd/mnemion/issues/50) remains open; the
[existing acceptance requirements](2026-10-29-macos-keychain.md) are unchanged.

The [receipt index](2026-11-01-macos-keychain-compile/receipt-index.json) binds the
retained artifact hashes and verbatim diagnostic files to this run. No test
replay or new execution was used to prepare this report.

A later ARM64 compilation and the first injected-fixture run are recorded in
the [2 November native ownership progress](2026-11-02-native-ownership-progress.md).
They do not change this page: no fixture binary ran in run 41346487519, and
issue 50 stays open.
