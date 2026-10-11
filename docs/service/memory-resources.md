# RAM budgets and local resource controls

The native local-host implementation is being validated. It is not included in
the published 4.0.10 desktop client. These controls apply to a workspace hosted
by the native engine on this computer; connecting to a company workspace does
not give a client control over the company's host. See the remaining
[installation gates](../implementation/app-onboarding.md).

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
recent `memory` sample when a matching live process exists. It does not return
the owner's API credential. Inspect the revision before changing a policy.

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
and pauses new model work. Preserve the private directory and restore a
verified policy backup; automated damaged-policy recovery in the app remains
open work. Never delete the workspace to repair a RAM setting.

Local Linux validation has exercised lower/raise/restart behavior with the real
compiled engine, database and embedding model. The desktop lifecycle tests cover
concurrent saves, interrupted startup and cancelled shutdown. Packaged native
hosting on every supported platform, historical fleet measurements and an
optional OS-enforced limit remain separate acceptance gates.
