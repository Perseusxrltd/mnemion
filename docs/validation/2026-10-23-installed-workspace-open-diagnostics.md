# Installed workspace opening: failure diagnostics

**23 October 2026; source diagnostics, native acceptance pending.** The original
4.46.5 Windows ARM64 [job 120592908585](https://github.com/Perseusxrltd/mnemion/actions/runs/40002385734/job/120592908585)
failed in [run 40002385734](https://github.com/Perseusxrltd/mnemion/actions/runs/40002385734),
from frozen source `704650c91af3e6a300758d71d7ee72f29874a04b`.
This failed candidate is separate from the published 4.46.4 release and its
[native qualification](2026-10-23-4464-native-acceptance.md).

## Original failed candidate

Artifact `12524383122` records **`passed: false`**, `phase: create`,
`lastStage: startup-error` and `stage: installed-local-hosting`.
The log at **18:57:32 UTC** records a workspace-opening timeout. The probe had
completed its runtime-running wait and clicked **Open workspace**, then failed the existing
**180-second** workspace-open guard.

The original artifact does not distinguish authentication, a pending initial
read, UI selection or another cause. Its `startup-error` label alone does not
diagnose the failure. The failed attempt remains preserved.

The private job log has SHA-256
`c19af9f09ff9f8a34e4201edbebc12c29844bee4f64758ecff5613327c6572d7`.
The original artifact archive has SHA-256
`196f185ce3ff3ac4ddb4acff3a3361424de5a6333865fdbcea4f5b6951d9f527`;
its `installed-hosting-evidence.json` has SHA-256
`b57c659c36c1e913e19134eb623fb5d35c4f336e6814fd3ec75e67224d276e68`.
The dated `2026-10-23-backup-transfer-4465` evidence directory retains the
original JSON and private log; no raw error text or images are reproduced here.

## Bounded classifications for subsequent failures

The [source classifier](../../studio/electron/local-hosting-diagnostics.ts)
allows exactly eight enum fields: `route`, `view`, `localState`, `localSelected`,
`authenticated`, `identityMatches`, `openControl` and `error`. It rejects extra
or missing fields, invalid types/values and malformed or oversized reports.
Private UI error text becomes a fixed category such as `not_ready`, `access`,
`selection`, `file_access`, `timeout` or `other`.

After the unchanged workspace-open guard fails, the
[installed probe](../../studio/electron/local-hosting-probe.ts) attempts two
status reads, each capped at **two seconds**, and captures those classifications.
The [artifact writer](../../studio/electron/scripts/smoke-installed-hosting.mjs)
revalidates them before adding `workspaceOpen` to the failed evidence. This
field contains no credentials, paths, URLs, workspace names, contents or raw UI
error text. Ordinary diagnostic details remain private to the disposable runner.

This changes failure evidence only. It does not alter workspace-opening
behavior, the 180-second acceptance guard or retry policy, and it does not
retroactively determine the original failure's cause.

## Validation boundary

The Electron build and **three privacy/classification regression tests** passed.
The [tests](../../studio/electron/scripts/test-local-hosting-diagnostics.mjs)
distinguish authenticated initial-read failures from failed sign-in, reject
arbitrary renderer data and verify fixed classification without private text,
including through the renderer's function source.

These source checks do not establish a functional fix or a corrected native
pass. A subsequent 4.46.5 attempt with changed source needs its own native,
public-update and actual-deployment evidence. All
[66 requirement texts and states](../PRODUCT_REQUIREMENTS.md) remain unchanged,
and [V08 product telemetry](../implementation/anonymous-product-telemetry.md)
remains Planned and inactive.
