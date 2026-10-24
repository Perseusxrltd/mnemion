# Product telemetry catalog and local aggregates: source checks

**Initial catalog checkpoint, 24 October 2026; V08 remains Building.** The fixed catalog, Python/TypeScript
encoders, bounded native/browser queues and catalog preview passed the source
checks below. At that checkpoint, workflow hooks, sender and collector were absent. The disclosure
still has `collection_available: false` and `destination: null`; recording is
suppressed before storage access and no product collection is active.

The [version 1 catalog](../../mnemion/product_telemetry/catalog.json) contains
**94 workflows in 15 families**, four surfaces, 11 workflow metrics, four resource
metrics and seven ownership/privacy exclusions. Its SHA-256 is
`cd9108b5c25fd0ab7f96490638340ebe873dd38e4fd6e636065103fa8f2e9141`.
The [catalog and ownership documentation](../implementation/anonymous-product-telemetry-catalog.md)
records the fixed buckets and remaining instrumentation decisions.

| Saved check | Result and scope |
| --- | --- |
| Python | **28 passed**: 18 aggregate cases including parametrization, plus ten existing policy checks. |
| Browser/codec | **11 passed**, including exact Python/TypeScript coordinate and bucket parity. |
| Native bridge/operator | **12 passed**; these are source bridge checks, not installed native release qualification. |
| App builds | Frontend production and Electron builds passed. |
| Built-browser catalog journey | **Nine checks passed**: all 15 families, 94 operations and seven exclusions visible; truthful empty outbound preview; offline clearing of the new queue format; opt-out after reload; usable small-screen layout; only local static requests. |

The browser journey made no workspace API, production memory or cloud-model
calls. It inspected catalog/choice behavior; product workflows were unwired at
that initial checkpoint.
Raw private logs are retained separately. Their SHA-256 digests bind the results:

| Evidence | SHA-256 |
| --- | --- |
| Python result | `1bdaec69db471d915aa720e3bc17af9cd2e7f23f8bf1a3fb6dbab624fe6f4c07` |
| Browser/codec result | `16c06caa99b04cfb75312ae28f90cce763ff14cd977d0937babd6a1d6b971b7d` |
| Bridge/operator result | `bbbb656f61d40b3b79fc9a0fde15c2c721aae00c8d643244aa81da8db6d260b0` |
| Built-browser journey | `fb49cc77faa08f44663bd45cbe1307e1784137257fafde514137689c02293e9a` |

Local accounting allows 64 observations per workflow/surface/day and 24 per
resource metric/day, with at most 16 cells per observation and a daily cell
count capped at 255. **Explicit choice clears contribution accounting.** These
are local queue bounds, not distinct-user counts or a global anonymity budget.
**Expiry prunes on activity** and is filtered from preview; no background idle-time
deletion is established. Revision checks fence older work within the existing
store. At this initial checkpoint, store-generation fencing and final sender
cancellation remained future checks; the generation follow-up below records
the later bounded correction.

The [earlier privacy-control qualification](2026-10-24-telemetry-controls.md)
retains its browser failures, inspected continuations and container CI failures.
No fresh package build has qualified this later catalog batch; actual container
verification of the source/context corrections is still pending at this
checkpoint. The isolated 4.46.6 dependency-security release excludes this work.

No all-six-native acceptance, production emission, measured full-feature
CPU/RAM/wire overhead, anonymous ingress or collector/output privacy acceptance
is established. The [full V08 contract](../implementation/anonymous-product-telemetry.md)
and every other requirement retain their scope and states. The seven measurement
exclusions preserve privacy; they do not abandon connectors or roadmap outcomes.

## Store-generation follow-up — 24 October 2026

Native SQLite and browser preferences now retain a private random
`store_generation`. Enabling compares `expected_generation` and
`expected_revision` with current state; aggregate writes compare the same pair
captured by the originating work. After deletion/recreation, a new generation
rejects old writes and stale enables even when revision numbers repeat. An
explicit opt-out remains allowed with stale input and invalidates older work.

Supported legacy preferences preserve explicit opt-out. Reading missing/legacy
state does not silently create a generation or authorize collection; a missing
generation requires fresh disclosure before an enabled preference is effective.
An explicit supported choice upgrades the local store and clears pending data.
The token appears only in private policy/status control. It never enters
measurement cells, the decoded local aggregate list or an outbound payload and
must never be used as an analytics identity.

The corrected Python selection passed **29 checks**; the browser/codec selection
passed **12**, including existing coordinate/bucket parity. Frontend and Electron
builds both exited successfully. The original Python attempt remains
**one failed, 28 passed**: a misplaced test assertion referenced another test's
variable and raised `NameError`. The corrected test placement produced the
passing run; this was a test error, not a discovered runtime failure.

| Follow-up evidence | SHA-256 |
| --- | --- |
| Original Python test failure | `30a0a81cde87ea0b099d210626774a9b8abe2d6fa19f3ece72b2d5f895830b72` |
| Corrected Python checks | `f1fce7097cd74f289453d8a07c8996659972c75c1bc8ff54b49a7e4b620ededa` |
| Browser/codec checks | `9f8533994380ae8bd82779974460abf1d10abdf74390b60b45488cdc532ca969` |

The actual built-Chromium generation journey subsequently **passed 11 checks**:
stale UI enablement was refused after recreation at the same revision; legacy
opt-out survived reload and explicit migration; damaged generation failed closed;
the private token was not presented as a measurement; controls fit a **390-pixel**
viewport. Requests stayed local and static, with no workspace, collector,
production memory or cloud-model calls. The first runner started before browser
open completed, so **no UI action ran**. Waiting for open and running the identical
journey produced the pass; the original runner failure remains preserved.
Cleanup stopped only the verified fixture process, changed no production process,
and browser close completed.

| Built-browser generation evidence | SHA-256 |
| --- | --- |
| Original pre-open runner failure | `ffc7c3861836647ff0aafdf9b4a40c89309a570408d8b2c108cc684ea13a7ab0` |
| Passed 11-check journey | `2ebaab601fa28ac3831d1d6c9654ef4ed63c0d58e85ab05473951e90fbeed195` |
| Verified fixture cleanup | `b5016549b978ef8484d0d20e625653ffdcc106702073e3586993294e0d3e0e9e` |

These are local source checks. They do not protect against an unobservable
whole-machine snapshot rollback restoring the old token and choice together.
No workflow hooks, sender, collector or active collection are accepted by this
follow-up; final sender cancellation, resource/privacy qualification and native
release acceptance remain open. V08 stays **Building**.

## Owned headless control follow-up — 24 October 2026

Source now adds optional measurement at `mnemion-control call`. The version 1
[control-origin map](../../mnemion/product_telemetry/control-origins.json) covers
all **161 API operations**: **82 mapped actions and 79 exclusions** across five
documented reasons. Its SHA-256 is
`5482267dab262234d00f7591fea63c3da9defe391250ccdb2d46110e4f9e40de`.
Native privacy `schema` exposes this map as `owned_control_coverage`.

Only fixed librarian/embedding selector values and reviewed numeric primitives
reach the workflow encoder. The hook captures local generation/revision and
cannot change the ordinary call's result if optional measurement fails. Generic
SDK and remote MCP calls never own measurements. Keyed writes require the
server's `X-Mnemion-Idempotency: new`; replayed, missing/legacy and unknown
receipts contribute neither submission nor outcome. Async work remains
`accepted`, and payload-byte counts make no wire-throughput claim. The server
metadata is request-local and requires no database migration.

The original focused selection recorded **50 passed, one failed**. Its contract
test treated a referenced input schema as inline properties and raised
`KeyError`. The corrected focused contract check **passed once**, after resolving
the schema reference; the original failed run remains preserved. These are
separate saved runs. CLI ownership cases used local policy/queues with synthetic
API responses. A concurrent receipt test also used the actual HTTP service and
disposable PostgreSQL to distinguish the new write from its replay without
leaking state into a later request. The latest native bridge selection
also recorded **12 passed, zero skipped**. Frontend/Electron build evidence is
from the earlier generation checkpoint.

After the final schema exposure and import changes, the complete focused Python
selection passed **51 tests in 15.39 seconds**. A fresh private wheel then passed
an isolated import and offline control journey: every tested module came from
the wheel, all 161 operation classifications were available, opt-out and its
private generation persisted, and no collection or network work was activated.
This wheel is a source validation artifact, separate from the published 4.46.6
package; it does not establish native platform acceptance.

| Owned-control evidence | SHA-256 |
| --- | --- |
| Original selection, including contract-test failure | `1383e7ceb8c9dfe9fea6ea387807a2f45847ca1f63ca7dbdffc404d816ecc320` |
| Corrected focused contract check | `f0a26259c64fcacbb2157c5d37928dbfa090dd0f8b1e463556c55ded9c4d0245` |
| Latest native bridge checks | `ef0a8c310289cd7b3cdebc2d431250e233de33506b7b56906309e0697bc28d2d` |
| Final 51-test selection | `d2e085fac288dbb7db55f88616136fd8f962181583380b6212450e8b224445c7` |
| Private wheel acceptance receipt | `d3caf249ebf69dfde343acc974be73bb3959a5b466eb86fc4b15733fa8108170` |

At that headless checkpoint, desktop/browser, stdio and background hooks remained
pending. Collection remains unavailable; native/all-platform acceptance, the
sender/collector and measured resource/privacy qualification are still open.
This source progress does not complete V08 or change any other requirement's state.

## Private native store and owned UI follow-up — 24 October 2026

The current source adds [NativeTelemetryStore](../../studio/electron/telemetry-store.ts),
which uses `node:sqlite` to share the existing private policy/aggregate database
with Python. Windows explicit initialization and read checks use private
permissions; the app's [MSVC-compiled helper](../../studio/electron/native/telemetry-private-store.c)
only inspects owner/DACL state. It does not read memory content, repair permissions
or create settings. Missing, linked, publicly readable and otherwise unsafe
stores are refused. Busy writes drop the optional observation without a retry.

The shared [TypeScript workflow](../../studio/electron/telemetry-workflow.ts)
copies the private generation/revision, finishes once and passes validated
submission/outcome primitives to a bounded write. The
[desktop-origin map](../../mnemion/product_telemetry/desktop-origins.json) contains
**43 eligible actions and 29 exclusions**. Native operator execution and selected
trusted IPC actions have distinct fixed surfaces; cached replies and generic
remote host requests do not own a fresh use. The
[Studio-only wrapper](../../studio/frontend/src/workspace/measured-client.ts)
selects **64 methods and explicitly excludes 66**. Generic SDK calls retain only
weak response-bound `new`/`replayed` metadata and start no analytics. Polling,
uncertain/replayed keyed writes, privacy controls and unowned continuation
transports remain excluded. These are source coverage maps, not complete
instrumentation or release acceptance.

The following original results cover the earlier private-store implementation:

| Preliminary saved check | Result and scope |
| --- | --- |
| Python policy/aggregate | **32 passed, two Windows skips**, in 4.18 seconds. |
| Local native store/bridge | **Ten passed, one Windows-only skip**. |
| First Windows attempt | MSVC compilation completed, then Node could not discover the test on a UNC path; **no tests ran**. This original failure is retained. |
| Windows continuation | **Nine passed, zero skips** on native Windows **Node 25.2.1 / Python 3.13.11**. The runner copied source fixtures into a local temporary directory and removed them afterward. This was not an Electron/package run. |

The Windows cases exercised a shared bounded database, opt-out against pending
work and later re-enable, store recreation and caller-stamp mutation, company
restrictions, shared daily caps and expiry, immediate drop under another writer,
unsafe/missing stores and refusal of public read access without repair.

| Preliminary evidence | SHA-256 |
| --- | --- |
| Python checks | `69aa1bf113a41ce7d1c550a6830aa72ebad54d49af26f9bcb2d09f86ab70ee1b` |
| Local native store/bridge checks | `da659db36a32057e22b7d438e827efa32f24ddb6311458197ef9f391af9f0979` |
| Original Windows discovery failure | `474d42886fe9bb541bfdeaeafac9f310e5b2dbe612cce34d6e4e0d350348e196` |
| Windows continuation | `6a1964bd7048a1b200779c83bac9740992148c8f6463cad86956951c549a8447` |

**The batching and desktop/Studio hook changes postdate those preliminary
receipts.** The later targeted checks are recorded separately:

| Later source check | Result and limit |
| --- | --- |
| Final Python policy/aggregate | **32 passed, two Windows-only skips**, in 4.72 seconds after a formatting-only correction; Ruff check passed. |
| Studio/browser policy and client | **24 passed**, zero skips. |
| Desktop classification and helper packaging guards | **Six passed**. Includes the helper's executable path outside ASAR and unpack configuration; this is a source/configuration check, not an installed package run. |
| Actual Windows store | **11 passed, zero skips**, using the Visual Studio-built x64 helper, Node 25.2.1 and Python 3.13.11. Includes protection against a directory exposing new SQLite journal files; no packaged-app acceptance is inferred. |
| Earlier actual Electron 44.9.3 store run | **Eight passed, one Windows skip** at an earlier test stage. This does not qualify the later full selection or an installed app. |
| Final actual Electron 44.9.3 / Node 24.22.0 selection | **27 passed, two Windows-only skips** out of 29, in **6.17 seconds**, across privacy bridge, native operator, helper packaging-path guards and final native store checks. This supersedes the earlier Electron selection for source coverage. |
| Final Electron build | Passed; this is a source build, not installed all-six qualification. |
| Copied built-Chromium workflow journey | **19 checks passed**, including three real UI search submissions against intercepted synthetic workspace responses, no polling measurements and opt-out during an outstanding request. |

The browser fixture changed exactly one disclosure literal in one copied built
asset to enable local counters with an `example.invalid` destination. Its
recorded hashes match both the copied fixture and unchanged original build.
Actual source/dist disclosure remains `collection_available: false` and
`destination: null`; there is no sender. The journey confirmed numeric-only
aggregates with no private query, key, address or space, a readable private
preview, and no queue resurrection when a held response arrived after opt-out
in another tab. Search still worked after opting out. All traffic stayed on the
isolated fixture; there were **zero outbound collection requests, production
memory calls/writes or cloud-model calls**.

The original browser runner timed out waiting for the desktop-only **Join a
workspace** control. That failure is retained; the continuation used the actual
browser connection controls, without claiming a product fix. Cleanup at
**03:24:03 UTC** confirmed browser closure and stopped only the verified fixture
server, with no production state change.

| Later evidence | SHA-256 |
| --- | --- |
| Final Python checks | `eec261d6d981c6689f1e5faf06d4f8b1cff01296e94a3c561cf2dd849cc0819b` |
| Studio/browser checks | `c0f9acef742a434325ee9bda34e0210325d65dc13f93e2846af2909e0bc4375c` |
| Desktop source guards | `8676faad29adeed76ca2d99286f3de89cc8d9b056ab13c935856fcfc22403bc2` |
| Final actual Windows store checks | `c48e9bff8a1719be69ddbb1ec286c12bc7e7487fe91f8e5a94685df30d56fd69` |
| Earlier Electron store checks | `efab902c78de493d088bc823aefba59abdfb6b0254d1f4c61b61b88a8e0c67b2` |
| Final combined Electron checks | `b8eec04f9c183ced1464765c23c200dfa7d15ffd8106f68c326ed8a4f0122993` |
| Final Electron build | `873b841c25f2b8da83857d248087de185ea22e1986b5fb6eb43f96e70e00896b` |
| Original browser control-selection failure | `a5fe382b97c08692e43beb01de28f0e5e93740e8a478074620327e04c20fd8af` |
| Copied fixture definition | `5e1dc70a0b05cfb95932eaaade381600e40dfff355d94c0f5e53b5b5ce45582f` |
| Passed 19-check browser journey | `03486497802f26364fc9f8120a25495b62e984585d14c56d49480b2df34eaab8` |
| Verified fixture cleanup | `c3dc09dfe4012ef6dd4265421a0ae6576b2ea6044e0ea306bd0232c23b3adf85` |

The saved **71-file source input inventory** records input digest
`fc8d9228b0e3b0e11e760ec5a0832867487fa0bb4f2a5c9dbcb2fc2bf7caa89a`;
the inventory file itself has SHA-256
`8ddf2b0b3e9cd8f559cb456dec9fe5ce4a21f9f02d9ad4fbc54e5ff2f4ae8982`.
It binds the source checkpoint, not a published or installed telemetry artifact.

An exploratory Linux Electron 44.9.3 component measurement completed **32
workflows** with **3,784,704 bytes (3.61 MiB) added RSS**, **301,556 added heap
bytes**, **99.536 CPU milliseconds** and a **16 KiB database**. Its SHA-256 is
`6e2f9cc56a53194674de7434e7155d45277ebf1e1ba5cfc0d0e11968861d6f9f`.
**The RSS result exceeds the contract's proposed 2 MiB ceiling.** It is not a
resource pass; the ceiling is unchanged. This component-only observation cannot
establish whole-app or all-platform overhead, and the heap/database figures do
not substitute for RSS. Optimization and full resource qualification remain open.

At that desktop/Studio checkpoint, remaining owners included browser
sign-in/connect, the legacy UI, local stdio-MCP and background jobs.
No packaged telemetry, all-six-native, sender/collector,
wire-resource or anonymity acceptance is established. Production collection
remains unavailable, and full V08 completion remains pending.
The fully accepted security-only 4.46.6 release excludes this unreleased telemetry
work. V08 remains **Building**; all 66 requirement texts and other states are
unchanged.

## Browser/legacy UI and local stdio follow-up — 24 October 2026

The [UI-origin map](../../mnemion/product_telemetry/ui-origins.json) adds five
browser connection actions and classifies all **29 legacy Studio methods:
11 selected and 18 excluded**. The [UI wrapper](../../studio/frontend/src/workspace/measurement-action.ts)
skips desktop connection actions already owned by IPC, handles company sign-in
cancellation from its abort signal and reads only declared boolean result flags.
Unknown flags discard the measurement; callback inputs/results and exception
text do not enter the encoder. Automatic queries and external-app handoffs stay
excluded.

The [MCP-origin map](../../mnemion/product_telemetry/mcp-origins.json) classifies
**29 maintained gateway paths**, including two compatibility path labels, and
**48 legacy stdio tools, 33 selected**. Only explicitly configured local stdio
uses the OS-account policy. HTTP never inherits that choice, even when a server
holds a stdio key. Aliases delegate to one inner owner, and keyed operations
retain fresh-receipt gating. Imported handlers and caller JSON cannot assert
local ownership. These path counts are not counts of exposed public tools or
proof of full workflow qualification.

The local `mnemion_telemetry` tool provides offline `status`, `schema`, `preview`
and `configure` through the existing private policy. It is absent from ordinary
HTTP discovery; HTTP invocation is refused even on a stdio-configured server.
No privacy-control use generates telemetry. The existing schema version and
`collection_available: false` / `destination: null` gate remain unchanged.

| Initial source evidence | Result | SHA-256 |
| --- | --- | --- |
| MCP checks | **19 passed**, in 5.28 seconds | `56cffaa94062852571d35a32cf2ae25075ce393933e2c308993a97db147f2166` |
| UI/client checks | **30 passed**, zero skips | `68411618b47df35397ba5ff5c1e593395d8035220d16cc1e0296034cd4ab3913` |
| UI-origin map | Five browser actions; 29 legacy methods | `14c90fe2558cfa4f39e82360be6c8ddbae401def3cb25e17bb49b4639ece0c9e` |
| MCP-origin map | 29 gateway paths; 48 legacy tools | `b1ad28ef355bd11c8196cf5760263ddb54ce77b39c48ba819db07fe0e6477783` |

After schema exposure and the observer-import correction, the Python MCP
selection passed **20 tests in 4.26 seconds**. Local schema now returns
`owned_origin_coverage` with desktop, Studio, UI and MCP maps, retaining the
existing CLI map. The added import-failure regression verifies exactly one
original action and no optional measurement; it does not retry a completed
action. The **30 UI tests** above remain the recorded UI selection. The initial
frontend build stopped at `TS2339` in the measurement wrapper; the corrected
TypeScript/Vite build passed. Both build results are preserved.

The actual copied built-Chromium journey **passed 14 checks**: key connection,
password sign-in, logout/disconnect, two legacy searches, readable numeric
preview and cross-tab opt-out fencing a held reply. Private query, password,
token, principal, address and workspace values stayed out of the local queue.
There were no page errors or non-fixture requests. Only the copied disclosure
enabled counters at `example.invalid`; recorded hashes match the unchanged
source build and copied fixture. The API was a fake loopback service, with no
production memory or model calls.

The actual MCP `ClientSession` and maintained CLI over stdin/stdout **passed
22 checks**. Initialization disclosed local controls, schema exposed all four
ownership maps, and one alias invocation made one fake workspace request and
one submission without a second SDK count. Private request/response fields
stayed out of aggregates. After the fake workspace shut down, local opt-out
still succeeded and cleared all queued cells. Only the isolated test process
enabled counters; no sender or production collection was activated. Browser
cleanup separately verified closure and exactly one fixture server stopped,
with no production state change.

| Later UI/MCP evidence | SHA-256 |
| --- | --- |
| Final 20-test MCP selection | `911a6bef9b4ac3609fcdff31d496b15d9ecfad52fbc2127f8738a1f129b80374` |
| Original TypeScript build failure | `7f1f95b40bdbc86197eaa3c64ad681b5c652437fd6f4ae1c24dd37443482a061` |
| Corrected TypeScript/Vite build | `59d09a33eeb3e26efe9f9b742119e8518cd04644544a70e890db77ecbbf62d40` |
| Copied browser fixture definition | `4dc1a23f8b13e978b98ac1fdd7e687e3cb2d22c87d741e42c60cd267d9ef6cef` |
| Passed 14-check browser journey | `b749cd3b48ed41bc2020759fb43a5b286791068d32e9239c4ee5891b837911fb` |
| Passed 22-check stdio journey | `9e80f5eaed9ba7fad56e3bd338910a44ad8ce80f42ce99e01db97fbdb39d8896` |
| Verified browser cleanup | `ad75ad5857bdee2924848cad257bc2d13fa3c0fc0037b0b247c2dd0ca8335e2c` |

A later exploratory Electron phase diagnostic recorded **3,424,256 bytes
(3.27 MiB)** total added RSS, including a **1,802,240-byte** rise between
construction and the first SQLite snapshot/load. Its SHA-256 is
`bfe71fa01ac22892b3eb239d7fda0fbc69f7673440564bb2eb1e815653199049`.
This is a component diagnostic, not resource acceptance or a replacement for
the original **3.61 MiB versus 2 MiB** gap. The ceiling is unchanged.

These receipts do not establish final source inventory, integration or a future
CI result. Background/updater owners, resource optimization, remaining workflow
qualification, sender/collector, final-send cancellation, anonymity and
all-platform release acceptance remain open. V08 stays **Building**, with no
other requirement text or state changed.

The prior batch's container CI failure is also retained: the Docker allowlist
excluded `telemetry-workflow.ts`, so the container build could not copy it. The
original log SHA-256 is
`acfd40e13525b3f2417e8735659701b069be5d2bd5a769c7cff4564476537906`.
The one-line [allowlist correction](https://github.com/Perseusxrltd/mnemion/commit/e7d5db06)
was integrated at `1325f457eafa71682fb9e30a0a751b5e6fa9718c`.
At **03:41 UTC**, [CI 40058889975](https://github.com/Perseusxrltd/mnemion/actions/runs/40058889975)
had **eight of 12 jobs passed**, including both container jobs, with no failures.
That dated observation does not establish completion of the entire CI run or
qualify this later UI/MCP source batch.
