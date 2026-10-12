# RAM budgets and local resource controls

## Idle model cleanup in 4.1.1

Source 4.1.1 adds automatic release of local embedding sessions
after **300 seconds without inference** in each API or indexing-worker process.
Native release acceptance remains pending; this is not in published 4.1.0.
Active and queued calculations are protected by the same inference gate used
for memory-budget changes. Model files, fingerprints, indexes and canonical
memories stay on disk. The next semantic request reloads the approved model;
this can add cold-start latency. Keyword retrieval needs no loaded model.

Host operators can set `MNEMION_MODEL_IDLE_SECONDS` to **10–86400** before
starting a service, or **0** to retain warm models. Five minutes is the default.
**Insights & evaluations → Models & resources** reports the current API process's setting,
loaded-model count, idle releases and cleanup retries. The same values appear
in the optional `model_cache` object from `GET /v1/insights/runtime` for authorized
organization administrators and agents. Earlier servers omit that object.

This lowers retained idle memory; it does not combine separate API/worker
allocations or establish a whole-host RAM cap. Native RAM admission and its
live controls below remain separate. Real RSS measurements and native release
acceptance must precede claims about the amount of memory reclaimed.

## Native local budgets

These controls require the native local engine in **4.0.11 or later**; they are
not included in the earlier 4.0.10 desktop client. They apply to a workspace hosted
by the native engine on this computer; connecting to a company workspace does
not give a client control over the company's host. See the remaining
[complete app setup requirements](../implementation/app-onboarding.md).

## Choose a budget in the app

Local workspace creation recommends a CPU model and **Automatic** RAM management
using this environment's measured resources. After setup, open **Setup & this
device → RAM on this computer**. Choose Automatic or enter a manual budget of at
least **256 MiB**, then select **Apply RAM budget**. Changes take effect in the
running engine within a few seconds and survive a restart.

Automatic mode starts with one quarter of the memory available to the operating
environment, capped at 4 GiB. It leaves system headroom and reduces the target if
other software needs that memory. Linux container and parent cgroup limits are
included when available. Manual mode is also bounded by the measured hardware
headroom; requesting more than this computer can provide does not allocate it.

The current target, measured use and engine/database/desktop breakdown appear
above the settings. The small chart contains samples from the current page
session. It is not a retained performance history. If a local agent changes the
policy, the page refreshes its revision. Unsaved edits stay intact; use **Use
current settings** before applying when another session has changed the budget.

## What happens under pressure

Mnemion reduces indexing batches, releases idle embedding models, and pauses new
model work as capacity becomes insufficient. An active calculation completes
before its model can be unloaded. Accepted memory writes and keyword retrieval
remain available; hybrid retrieval can fall back to keyword search. A request
that requires semantic inference reports `inference_memory_budget` when the
required capacity is unavailable. Deferred background work resumes when the
budget allows it without spending its normal failure retry allowance.

The initial model allowance is conservative: E5 small starts at a 1 GiB
minimum, while the smaller English BGE profile starts at 512 MiB; measured desktop
use is added to that allowance. These are starting thresholds, not promises of
identical usage on every OS, processor or document batch. A 256 MiB budget can
keep model work paused. Stored memories are retained.

The budget is **cooperative**, not reserved RAM or a hard process limit. RSS can
temporarily exceed the target while a native call finishes. The displayed total
adds resident memory for the engine, its identified database process tree and
the desktop; shared pages can be counted more than once. Missing measurements
pause new model work. External model servers have their own memory limits and
are not controlled by these settings.

## Local agent operations

Host agents running as the same operating-system account can use the fixed
local operator commands. Ordinary API keys and MCP membership do not grant this
host access. Read the workspace data-folder location in **Setup & this device →
Local storage & agent controls**; use that value as `DATA_FOLDER` below.

```text
mnemion-service local status --root DATA_FOLDER
```

The JSON `status` event includes `memory_policy.settings`, its revision and a
recent `memory` sample when a matching live process exists. If the policy needs
repair, `memory_policy` is `null` and `memory_recovery` explains the problem.
The status remains available before the engine starts. It does not return the
owner's API credential or damaged file content. Inspect the revision before
changing a valid policy.

Run the following command and send one JSON object through standard input:

```text
mnemion-service local memory --root DATA_FOLDER
```

```json
{"mode":"manual","limit_mib":1536,"expected_revision":"REVISION_FROM_STATUS"}
```

Return to automatic mode using the new revision:

```json
{"mode":"auto","limit_mib":null,"expected_revision":"REVISION_FROM_STATUS"}
```

The revision check prevents an agent from overwriting a newer change. A
successful `memory_policy` response contains the saved policy and
`apply_within_seconds`. The operator writes it atomically in the private
`resource-policy` directory. Do not edit the live JSON file in place or place
the database in a cloud-synchronized vault.

Organization administrators can observe the typed `memory_budget` field in
`GET /v1/insights/runtime`; it is `null` when this API process does not have a
native budget controller. This endpoint does not change the host policy.

## Recovery and remaining validation

A missing or damaged policy retains the running engine's last accepted limit
and pauses new model work. A stopped workspace cannot resume until its policy
is repaired; it never silently resets a missing manual budget to automatic.
Memories remain in place. An interrupted first setup that saved its workspace
configuration before its initial policy uses the same explicit repair flow.

In the app, open the local workspace from the welcome screen, or open
**Setup & this device** while connected. **Repair your RAM budget** explains the
problem. Choose Automatic or a manual limit and select **Repair and save RAM
budget**. A running engine adopts the new revision within a few seconds;
otherwise select **Resume local workspace**. Saving the file does not claim
that model work has already resumed: hardware pressure and model limits still
apply. If another session changes the policy, use **Refresh RAM policy** and
review the current state before retrying. Your chosen replacement budget stays
in the form while you refresh.

A host agent first reads `local status` and takes its opaque
`memory_recovery.repair_token`. It then runs:

```text
mnemion-service local memory-repair --root DATA_FOLDER
```

Send one JSON object through standard input:

```json
{"mode":"manual","limit_mib":512,"repair_token":"TOKEN_FROM_MEMORY_RECOVERY"}
```

Repair requires a token for the current damage. The token binds the inspected workspace, exact bounded
bytes and file identity; different damage, a replaced file, or a valid restored
policy rejects an old repair request with `memory_policy_changed`. A missing
policy has its own recovery token. Normal `local memory` writes cannot bypass
repair. A successful repair returns the usual `memory_policy` event with the
new revision and `apply_within_seconds`; read live status to confirm adoption.

Before replacing corrupt bytes, Mnemion durably preserves their exact contents
in the private `resource-policy/recovery` folder. Successful repairs retain the
latest eight damage copies, up to 256 KiB each; failed cleanup can retain more.
These are diagnostic policy copies, not memory backups. A failed preservation
or atomic replacement retains the original policy and keeps admission paused.
The operation never moves or replaces the database.

For a linked, foreign/shared, unreadable, redirected or oversized policy file,
status returns `memory_policy_inaccessible` and a null repair token. The app
shows the storage remedy and a refresh control, without offering an unsafe
replacement. Correct the OS storage access or use the host operator to retain
an oversized file outside the live policy path, then refresh and choose a new
budget. The supported in-app corruption repair is bounded to 256 KiB, the
policy record limit; it does not take ownership of foreign files or resolve
unsafe links. Never delete the workspace to repair a RAM setting.

Local Linux validation has exercised lower/raise/restart behavior with the real
compiled engine, database and embedding model. The [RAM-policy recovery checks](../validation/2026-10-11-native-policy-recovery.md)
also exercise real Windows private-file permissions. The desktop lifecycle tests cover
concurrent saves and repairs, interrupted startup and cancelled shutdown. The
operator regression tests cover malformed bytes, missing files, stale tokens,
private retention, failed replacement and live pause/adoption. Published
[4.0.12 installed setup, model save/search and reopen](../validation/2026-10-11-v412-release.md)
passed on Windows, macOS and Linux, each on x64 and ARM64. This evidence does not
cover every RAM-policy failure on every OS. Broader hardware measurements,
historical fleet metrics and an optional OS-enforced limit remain open.
