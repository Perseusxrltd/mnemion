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
