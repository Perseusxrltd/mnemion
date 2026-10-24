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
calls. It inspected catalog/choice behavior; product workflows remain unwired.
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

Collection remains unavailable. Desktop/browser, stdio and background hooks,
native/all-platform acceptance, the sender/collector and measured
resource/privacy qualification remain pending. This source progress does not
complete V08 or change any other requirement's state.
