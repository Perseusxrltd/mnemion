# Native onboarding and RAM readiness review

Reviewed the native runtime branch based on `3f3a37d`, against U01, U02, R02 and
R03 in [the product requirements](../PRODUCT_REQUIREMENTS.md) and the
[complete app onboarding contract](../implementation/app-onboarding.md).
This is development evidence, not a claim that native hosting is included in a
published installer. Windows private-directory work and hosted OAuth have
separate owners and are outside this review.

## Fixed in this review

- The Docker frontend build omitted the new shared onboarding types. Both Linux
  container jobs failed with TS2307 for `studio/shared/local-workspace.d.ts`.
  The build context now includes that exact declaration file and the Dockerfile
  copies it. The frontend production build passes locally; the actual container
  build still requires its CI rerun.
- A resumed workspace waited until the indexing queue became empty before
  opening, then failed after 30 seconds if the backlog persisted. Worker startup
  now establishes liveness independently of queue length; a worker failure or
  stop during verification still prevents a successful readiness event.
- A previous `readiness.json` suppressed all future retrieval checks, while new
  successful model/index flags were written from RAM admission alone. Every
  restart now runs actual keyword retrieval and attempts semantic retrieval when
  admitted. Inference is recorded only after a successful semantic response;
  index evidence requires a returned semantic hit. An empty workspace is valid
  and does not acquire a fabricated index result or a recreated welcome note.
- The first low-budget setup searched for “assistants” while its welcome text
  contains “assistant”. Literal keyword retrieval returned no welcome memory.
  The verification query now uses exact words in the unchanged welcome content.

Nine focused startup tests pass with real PostgreSQL and service handlers. One
test runs the actual loopback service while the worker continuously reports busy;
another checks that a failed worker cannot pass readiness. The model is a
deterministic protocol fixture, so these tests do not replace native model,
packaged installer, or platform walkthroughs. Test execution was limited to a
1 GiB Linux scope. `ruff` also passes.

## Remaining concrete blockers

| Priority | Finding and current source | Required completion evidence |
| --- | --- | --- |
| Before native release | `studio/electron/service-bridge.ts` expects bundled `engine` and `postgresql` resources. The desktop resource builder and `package.json` only package the client, frontend and notices. | An installed app must provision verified native engine/database resources and complete setup without Python, PostgreSQL, a compiler or terminal. Run on every offered OS/architecture. |
| Before recovery claims | Corrupt `resource-policy/memory.json` makes `local_memory.policy()` fail; both `inspect()` and `configure()` require that read. The app cannot load RAM settings or replace the damaged policy through its controls. | Expose retained status and an explicit private operator repair that preserves the damaged record and prior cap. Rehearse repair through UI and CLI while the engine is running and stopped. Do not silently reset to automatic. |
| Before complete onboarding claims | A saved service-port conflict tells the user to change the workspace port, but `LocalSetup` only shows the port field before configuration exists. Configured workspaces only offer resume. | A stopped-workspace port change must check availability, preserve credentials/data, update the saved connection and complete reconnect through the app. |
| Before complete onboarding claims | `service-bridge.ts` fixes the data root; `LocalSetup` displays it without a location picker. “Free disk” is checked only at creation and there is no app move flow. | Let the user choose a safe local destination and move/recover through verified separate staging without putting a live database in synced storage. Rehearse insufficient disk and an interrupted move. |
| Before complete recovery claims | `Setup.tsx` links to recovery documentation; no native backup destination, schedule, backup verification, restore selection or activation flow is registered in the local operator bridge. Revoked/missing owner credentials also stop startup with a recovery instruction and no app repair path. | Create, inspect and restore a backup into a separate destination, reconcile access/deletion state, recover operator access without reviving revoked keys, then switch through the app while retaining the prior workspace. |
| Before complete source setup claims | The local service starts API, embedding worker, evaluations and librarian orchestration. It does not start a connector runner. Setup links to the source configuration page but cannot install/authorize/start a required source worker. | A fresh local app connects a selected provider/folder, previews scope, starts its worker, shows a real first sync and resumes after restart without a terminal. |
| Before RAM/evaluation claims | `EvaluationRunner.run_once()` gates only the first job claim on RAM. A budget change between cases can unload a model; `_step()` then fails the run as `model_not_ready`, and a retrieval budget error can become a failed result instead of a resumable resource pause. | A live budget reduction must expose an intentional evaluation pause/defer state without inventing retrieval-quality failures; preserve or explicitly account for lease/time budgets and resume safely. |

Native RAM admission remains a cooperative working budget, not an operating-system
reservation or byte-exact hard limit. UI claims and minimum hardware requirements
must use measured engine, database and desktop use across the shipped platforms.
The passing focused tests do not close the blockers in this table.
