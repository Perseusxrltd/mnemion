# Probe staging — phase helper — 29 October 2026

Run 40965218896, source `da8e97bc362c90427f690bd4f970e5f3a710c9a6`, failed
before its first app journey. `r1-unavailable.log` records:

`Error [ERR_MODULE_NOT_FOUND]: Cannot find module '/tmp/mnemion-owned-renderer-bp0omsir/source/studio/electron/phase-memory.mjs' imported from .../studio/electron/probe-telemetry-renderer.mjs`

The controller imports `./phase-memory.mjs`. Staging copied the controller to
`app/probe-telemetry-renderer.mjs` and did not copy the helper beside it. The
same static import runs in ordinary diagnostic mode. `cleanup.json` is all
true: isolated profiles removed, collector stopped, certificate profile
removed, and production disclosure unchanged. No completed memory or resource
measurement exists. This failure stays failed. It is not a resource saving.

Staging now copies `phase-memory.mjs` next to the relocated controller. Dist
paths, the app entry, guards, case order, workload, budgets and privacy
controls are unchanged.

Focused check, pinned interpreter
`/home/jorqu/.local/state/mnemion-release/2026-10-10/release-venv/bin/python`
and Node v22.22.0 at `/usr/bin/node`:

```text
python -m pytest tests/test_telemetry_probe_staging.py -q --tb=short
1 passed in 8.52s
```

The check stages the real controller and helper, runs Node with
`MNEMION_STUDIO_USER_DATA` removed, and reaches `Disposable renderer profile
required` instead of `ERR_MODULE_NOT_FOUND`. It does not launch Electron, a
model, a browser, a network request, or a real profile. Ruff 0.15.11 format
and check passed on the changed Python.

V08 remains Building. Production collection, destination, and route stay
false/null/null. The 2 MiB and 0.5 percent gates stay unaccepted. All 66
requirements remain. This does not qualify the diagnostic or an installed
release.

## Canonical helper correction — 30 October 2026

Main Product checks run
[41036810767](https://github.com/Perseusxrltd/mnemion/actions/runs/41036810767),
source `46d4f730149ed639a975b7c0456e620837a32cd1`, failed the same existing
staging regression in legacy job `123999607506`. The newly shared
`canonical-memory-cycles.mjs` import used `../` after relocation and resolved
outside the disposable application directory. The original completed-job log
is retained; no workflow or application run was repeated to diagnose it.

Grok correction `f547aae63ffdded4364fd0825cb7e54afc59d9f0` uses the controller's
actual relocated layout: `./canonical-memory-cycles.mjs`, copied alongside
`phase-memory.mjs` inside the owned application directory. The profile guard,
test, workload and installed drivers remain unchanged. Astra reviewed the
actual callers, imported the two-file change, and ran only the original
Linux staging regression. It passed in 2.982 seconds of recorded wall time,
reaching the disposable-profile refusal without loading Electron.

Private evidence is under
`telemetry-owned-resources/controller-staging-ci/verification/`; the original
CI failure is under
`telemetry-installed-delivery/combined-privacy-resources/ci-legacy-failure/`.
The separately running Windows ARM64 installed diagnostic `41036977655`
remains bound to its original source and was not restarted. This correction
does not qualify installed resource overhead or fleet collection. The current
[8 MiB/0.5% engineering budget](../implementation/telemetry-resource-budget-2026-10-30.md)
is unchanged, and all older failures retain their original criteria.
