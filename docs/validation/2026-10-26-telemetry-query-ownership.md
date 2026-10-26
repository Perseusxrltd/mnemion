# Telemetry transaction metadata and dependency ownership

**26 October 2026. Source audit at `2d48ace846f346a95b2a57559dc95affdbc42e91`.**
Dependency splitting is **not selected as the resource fix at this checkpoint**.
There is real source coupling between producers and review/delivery code, but
no demonstrated RSS saving against the existing **2 MiB enabled-minus-unavailable
gate per participating process**. Reducing common startup imports does not by
itself reduce that difference. The 0.5% CPU ceiling is also unchanged.

The dependency section is a read-only source audit. Its pinned references bind
the baseline, while the transaction change and checked comparison below cover
the later source. Neither is installed or full resource qualification.

## Inspected dependency boundaries

| Source at the pinned commit | Finding and implication |
| --- | --- |
| [service-bridge.ts:26](https://github.com/Perseusxrltd/mnemion/blob/2d48ace846f346a95b2a57559dc95affdbc42e91/studio/electron/service-bridge.ts#L26), `telemetryStore()` at line 329 | Store, activity and condition classes are static imports. The first selected action constructs one `DesktopTelemetryActivity` and its catalog before the workflow's availability check. The desktop's unavailable and enabled paths share these imports; a split would not remove a demonstrated enabled-only allocation. |
| [telemetry-workflow.ts:23](https://github.com/Perseusxrltd/mnemion/blob/2d48ace846f346a95b2a57559dc95affdbc42e91/studio/electron/telemetry-workflow.ts#L23) | The workflow module has only type imports and returns before a snapshot when unavailable. It is already a small producer interface; its concrete store supplies the larger dependency graph. |
| [telemetry-store.ts:2](https://github.com/Perseusxrltd/mnemion/blob/2d48ace846f346a95b2a57559dc95affdbc42e91/studio/electron/telemetry-store.ts#L2), `open()` at 133 and `maintainReview()` at 191 | Review parsing/lifetime/clock code is imported eagerly, but `node:sqlite` loads only after private-store checks. Producer writes maintain staged-report invalidation inside their transaction; review-clock reads occur only when a staged report needs checking. Moving imports cannot discard that authority/expiry maintenance. |
| [telemetry-activity.ts:2](https://github.com/Perseusxrltd/mnemion/blob/2d48ace846f346a95b2a57559dc95affdbc42e91/studio/electron/telemetry-activity.ts#L2), [telemetry-delivery.ts:90](https://github.com/Perseusxrltd/mnemion/blob/2d48ace846f346a95b2a57559dc95affdbc42e91/studio/electron/telemetry-delivery.ts#L90) | Activity extends delivery, which extends the store. Delivery/wire classes load eagerly, while the wire encoder is constructed on demand and transport is dynamically imported only for sending. Offers follow committed observations or explicit approval; there is no new idle owner. |
| [telemetry-network.ts:9](https://github.com/Perseusxrltd/mnemion/blob/2d48ace846f346a95b2a57559dc95affdbc42e91/studio/electron/telemetry-network.ts#L9) | The native binding loads on a probe/clock call, not from importing its wrapper. Conditions also use this module, so isolating review imports alone would not remove the condition dependency. |
| [telemetry-policy.ts:1](https://github.com/Perseusxrltd/mnemion/blob/2d48ace846f346a95b2a57559dc95affdbc42e91/studio/frontend/src/workspace/telemetry-policy.ts#L1) | The browser producer store shares source imports and construction with budget, review and delivery. Coverage metadata is separately loaded on demand. This establishes source coupling, not a measured compiled-bundle or renderer RSS saving. |
| [workflow.py:90](https://github.com/Perseusxrltd/mnemion/blob/2d48ace846f346a95b2a57559dc95affdbc42e91/mnemion/product_telemetry/workflow.py#L90), [policy.py:375](https://github.com/Perseusxrltd/mnemion/blob/2d48ace846f346a95b2a57559dc95affdbc42e91/mnemion/product_telemetry/policy.py#L375) | Python returns before policy status when collection is unavailable. An eligible producer calls full `policy.status()`, which imports `delivery.budget_status`, reads delivery state and brings in wire/review modules. This is a genuine producer-to-reporting dependency, but it is a different process from the recorded desktop-main excess. Splitting it has no quantified RSS benefit and must preserve malformed-store refusal and fresh policy authority. |

The retained renderer probe also imports the actual activity class before its
`before_workspace_connect` baseline
([probe-telemetry-renderer.mjs:60](https://github.com/Perseusxrltd/mnemion/blob/2d48ace846f346a95b2a57559dc95affdbc42e91/studio/electron/scripts/probe-telemetry-renderer.mjs#L60)).
Its common import window is not a removable enabled-only cost. Deferring common
code until an enabled delivery could lower the unavailable baseline while
leaving the enabled path's eventual work, rather than improving the measured
difference. Source size, module count and import timing cannot be converted into
RSS savings from these records.

## Retained decisions and limits

The initial [storage ownership review](https://github.com/Perseusxrltd/mnemion/blob/2d48ace846f346a95b2a57559dc95affdbc42e91/docs/validation/2026-10-26-telemetry-storage-ownership.md)
still accurately describes the on-demand desktop owner, lazy SQLite/transport,
fresh connections and shared authority. Its dependency-split question is now
resolved as **not justified for this gate**, without rewriting that historical
checkpoint. Its common-import and first-open windows were overlapping diagnostics,
not causal attribution to SQLite or an optional import.

The later [storage follow-up](https://github.com/Perseusxrltd/mnemion/blob/2d48ace846f346a95b2a57559dc95affdbc42e91/docs/validation/2026-10-26-telemetry-storage-followup.md)
retains both enabled main matched maxima, **3,121,152 / 3,235,840 bytes**, and
endings, **2,125,824 / 2,207,744 bytes**, all above 2 MiB. Its six original
outcomes, other-process results and source/measurement limitations stand; no
newer source is thereby qualified.

The [first private adapter](https://github.com/Perseusxrltd/mnemion/blob/2d48ace846f346a95b2a57559dc95affdbc42e91/docs/validation/2026-10-26-telemetry-storage-adapter.md)
remains unadopted. The [pinned SQLite experiment](https://github.com/Perseusxrltd/mnemion/blob/2d48ace846f346a95b2a57559dc95affdbc42e91/docs/validation/2026-10-26-telemetry-private-sqlite.md)
remains rejected: its missing first slot prevented full counterbalance; lower
endings accompanied higher sampled peaks and CPU in the retained observations.
Functional compatibility and library unmapping established no resource pass.
This review proposes no further benchmark, binding replacement or budget change.

## Bounded recommendation and separate selected work

Keep the existing desktop owner and shared private SQLite. Preserve fresh
file/ACL and replacement checks, one nonwaiting process-wide handle through
actual close, current policy/company reads, revision/generation fences,
staged-review invalidation, durable spending and final handoff. Do not retain
positive consent, connections or statements across transactions, or move
ordinary measurements into a new Python subprocess or telemetry daemon.

## Checked transaction change

[NativeTelemetryStore](../../studio/electron/telemetry-store.ts) now reads format
version once, then selects the explicit preference fields, application ID and
journal mode together. The resulting format proof belongs only to the current
transaction. Review maintenance and delivery reuse it before the connection
closes; no row, statement or positive permission cache survives that transaction.
Cleanup-only cancellation still checks its own delivery format and never requires
consent to clear a lease.

Version 3/4 stores use the existing implicit `auto` connection mode. Version 5/6
stores require a valid explicit mode. Fixed `pragma_application_id()` and
`pragma_journal_mode()` function syntax refuses a same-name table attempting to
impersonate a pragma. Missing or invalid format, authority, generation, revision,
disclosure or choice remains a refusal. No schema migration, wire/catalog change,
new store, timing change or network request was introduced.

The Electron build passed in **12.632 seconds**. **67 Node checks passed with two
Windows-only skips** in **20.483 seconds**, covering store, delivery, transport
and activity ownership. Added checks cover each supported format with newer
columns/tables absent, malformed authority and lookalike pragma tables. Existing
checks retain Python opt-out/re-enable and recreation races, company restrictions,
review invalidation, nonwaiting ownership, TLS cancellation and handoff fences.
The Windows skips require their normal platform gate; Linux is not a substitute.

One deterministic comparison used the retained compiled 4.46.22 baseline and
changed compiled store, in that fixed order, for **32 accepted workflow pairs
per variant**. Node **22.22.0 / Linux x64** counted JavaScript statement wrappers
and rows returned by `get`/`all` at the actual SQLite boundary:

| Boundary | Baseline | Changed source |
| --- | ---: | ---: |
| Prepared statement wrappers | 608 | 384 |
| Returned query rows | 571 | 347 |
| Metadata statement wrappers / returned rows | 352 / 352 | 128 / 128 |
| Opened / closed connections | 64 / 64 | 64 / 64 |
| Maximum simultaneous connections | 1 | 1 |
| Accepted workflow pairs | 32 | 32 |

The final queue and contribution budget were exactly equal. The disposable
fixture was removed; no network or model call occurred. This demonstrates **224
fewer statement wrappers and returned query rows**, not fewer internal SQLite
operations or a measured RSS/CPU saving. It excludes `run` result objects, native
allocator behavior and installed Electron behavior. There was no resource
benchmark, forced GC, warm-up, idle padding, budget change or collector activation.
The resource gate remains open.

This checked source follows frozen 4.46.22 and is queued for the next coherent
release batch. It does not change that release's frozen inputs.

## Original SHA-256 evidence

| Evidence | SHA-256 |
| --- | --- |
| Declared plan | `14776873e9b02fcdfec0be68af827de762aaf6429b425d891545ac80732a8297` |
| Focused build and checks | `077a6aff830ef64a1765da81dab5dc2453e7138083cd332ff39a14fd9f1b40fe` |
| Fixed object comparison | `ee8e4c6cb5cfca8f588cb77576921e5e331d14ae7bc0a01240d1ecb402846d30` |

## Release context

The release owner independently verified that v4.46.19 public upgrades
[run 40344852373](https://github.com/Perseusxrltd/mnemion/actions/runs/40344852373)
passed all six targets plus select/reconcile at **15:14:34 UTC on 26 October**.
The 4.46.22 gates remain live and it is not published at this checkpoint. These
release facts do not qualify the telemetry resource gate. V08 stays **Building**;
collection/destination/route remain **false/null/null**, and all 66 requirement
texts and the existing resource/privacy/platform obligations remain intact.
