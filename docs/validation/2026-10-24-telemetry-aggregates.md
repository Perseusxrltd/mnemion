# Product telemetry catalog and local aggregates: source checks

**24 October 2026; V08 remains Building.** The fixed catalog, Python/TypeScript
encoders, bounded native/browser queues and catalog preview passed the source
checks below. Workflow hooks, sender and collector are absent. The disclosure
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
store. Removed/replaced/restored-store generation and final sender cancellation
remain future full-feature checks.

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
