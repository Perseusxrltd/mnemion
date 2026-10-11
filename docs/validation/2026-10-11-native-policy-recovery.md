# Native RAM-policy recovery validation — 2026-10-11

This slice adds recovery of a damaged or missing local RAM policy through Studio
and the fixed local operator command. It does not claim complete packaged native
hosting or database backup restoration.

## Behavior and safety

- Status retains workspace identity/resources and returns `memory_recovery` even
  for malformed JSON. It does not expose damaged bytes or invent a saved budget.
- An established workspace with missing policy no longer silently recreates the
  original settings. New model admission stays paused and a stopped engine
  requires explicit repair before restart.
- `local memory-repair` and the app require an opaque token for the inspected
  workspace and file identity/content. Changed damage, a replaced file, another
  workspace's missing-policy token, or an already-valid restored policy refuses
  stale repair. Normal revision checks remain in place for valid policy changes.
- Exact bounded damaged bytes are preserved in private storage before atomic
  replacement; failed preservation/replacement retains the original. Cleanup of
  old diagnostic copies follows successful publication. It never touches memory
  records or the database.
- Unsafe, unreadable and larger-than-256-KiB records report a storage-access
  remedy with no repair token. Ownership, linked-file and redirected-path
  protections remain required. This boundary needs an OS/operator storage fix.
- Electron serializes repair with stop/update operations. Policy damage refreshes
  status even when the engine retains its previous revision. A stopped workspace
  remains stopped after repair until **Resume local workspace** is selected.
- The installer agent's requested Windows ARM disclosure is included beneath
  local setup: native app/model, PostgreSQL via Windows x64 compatibility.

## Executed checks

Linux, capped at 1 GiB RAM / no swap / 150% CPU:

```text
python -m pytest client_tests/test_local_memory.py client_tests/test_local_state.py client_tests/test_private_output.py service_tests/test_memory_policy_recovery.py service_tests/test_local_readiness.py service_tests/test_memory_budget.py -q --tb=short
```

Result: **46 passed, 4 platform-specific skips, 13.51 seconds**. This includes
actual CLI subprocess status/repair/conflict responses, monitor pause and
post-repair adoption, plus the existing database-backed retrieval/readiness
regressions. Deterministic embedding fixtures do not establish model quality or
native inference readiness.

Native Windows Python 3.13 on local NTFS:

```text
python -m pytest client_tests/test_local_memory.py -q --tb=short
```

Result: **16 passed, 3.61 seconds**. The test process used an isolated temporary
Pydantic dependency target; no global Python environment changed. Both the
repaired policy and preserved damage copy passed actual Windows ACL assertions.
Fingerprints remained stable across private directory checks. This is not a
Windows installer or Windows ARM test; the native matrix retains those gates.

`npm test` in `studio/electron`: **57 passed**, including ten lifecycle tests
covering repair/startup exclusion, stale repair, shutdown waiting for a repair,
and detection of damage without a revision change. Electron and production
frontend builds passed with the 1 GiB cap; ruff and `git diff --check` passed.

## Browser evidence

Playwright CLI exercised the production frontend with an explicit fixture
for the desktop bridge. The browser checks established:

- Malformed-policy recovery is reachable from the local welcome flow and from
  **Setup & this device** while connected. Both offer explicit resume on the
  same page after repair; the normal settings reflect the repaired 640 MiB
  budget in the connected-page check.
- An invalid budget cannot submit. A changed token disables repair until refresh.
- Refresh retains the chosen 512 MiB budget and submits the current token.
- Successful repair of a stopped workspace exposes Resume without implicit start.
- At a 360-pixel viewport, content width remains 360 pixels; controls are readable.
- Inaccessible storage offers explanation and refresh, without a repair button.

Local screenshots and repeatable browser fixture scripts are retained under
`output/playwright/` in the isolated validation worktree; generated files are not
part of the product. The bridge is simulated in these UI checks. The Python CLI,
file operations, native Windows ACL checks and admission tests above exercise the
real implementations separately.

The native installer agent independently reviewed the policy/atomic-repair diff
and found no blocking issue. Full packaged onboarding, backup recovery, local
port/data-folder editing and the rest of the roadmap remain separate work.
