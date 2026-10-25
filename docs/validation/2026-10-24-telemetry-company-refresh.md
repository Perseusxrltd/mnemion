# Browser telemetry company-policy refresh

**Unreleased source checkpoint, 25 October 2026; V08 remains Building.** The source
adds a bounded company-restriction read before each already-reserved browser
report. The 24 October focused checks and the **25 October, 17:30:13 UTC actual
Chromium journey passed**. This is not production collection, installed
telemetry or release acceptance. The disclosure remains
`collection_available: false`, `destination: null`, and the release route address
is null. All 66 requirement texts and states are preserved.

## Source boundary

The [browser reader](../../studio/frontend/src/workspace/telemetry-company.ts)
requests `/studio/telemetry-policy` from the Studio page's own origin, not the
selected memory service. The [server handler](../../mnemion/service/studio_policy.py)
returns only fixed restrictions without account, session or workspace lookups.
Reading privacy status does not perform the request. The inactive disclosure
prevents an attempt in this build.

| Boundary | Current source |
| --- | --- |
| Request | One same-origin GET after spending a reservation; credentials omitted, no referrer, cache disabled, no redirect or keepalive. HTTPS is required outside trusted loopback fixtures. |
| Response | HTTP 200 at the exact URL, JSON, `Cache-Control: no-store`, absent/zero `Age` and a declared 1–1,024-byte body. A fixed buffer permits at most eight read steps, including completion, and requires the exact declared length. |
| Shape and choice | Only fixed state, enabled flag and allowed metric groups. Restrictions intersect with earlier observations in page memory; a response cannot override opt-out or acknowledge disclosure. Relaxing a restriction requires reload. |
| Timing and spending | The policy read and report share the original five-second lifetime. The report handoff must occur less than one second after the check started. Refusal discards the report without a refund or another selected view. |
| Fences | Local policy, pressure and the lease are checked before the policy GET and again before the report POST. Short operations from the same owner are serialized; network waits do not hold the privacy Web Lock. |

The [sender](../../studio/frontend/src/workspace/telemetry-transport.ts) retains
active cancellation across both requests. The
[delivery coordinator](../../studio/frontend/src/workspace/telemetry-delivery.ts)
clears an invalidated body immediately while sharing awaited matching-lease
cleanup with the finalizer. Local cancellation does not fabricate an unreadable
company policy. This fixes the initial source regression in which invalidation
discarded the cleanup token before durable lease removal completed.

The one-second condition is freshness from check start, not a separate GET
timeout. The final fence uses local choice and the last observed restriction;
it cannot atomically order a remote policy change after the GET with sending.
The extra request's traffic and both endpoints' ingress logs remain part of the
unqualified full delivery path.

## Source and isolated-browser evidence

The source checks below ran on 24 October; the actual browser journey, final
build and cleanup completed on 25 October. Earlier
[application-owner](2026-10-24-telemetry-app-owners.md) and
[client-transport](2026-10-24-telemetry-client-transports.md) receipts keep their
original scope and do not qualify this new refresh path.

| Check | Observed result |
| --- | --- |
| First browser source run | **76 passed, 14 failed**; exposed stale lease cleanup on company invalidation. Original failure retained. |
| Corrected browser source run | **90 passed**, no failures or skips, in 8.428 seconds, after awaiting shared cancellation cleanup and separating local cancellation from company-policy refusal. |
| Python route/policy checks | **25 passed in 26.20 seconds**, including real disposable PostgreSQL route checks. |
| Frontend type checks and final build | Passed; the final TypeScript/Vite build completed in **2.30 seconds**. |
| Ruff | Passed. Only the route test file was subsequently formatted; its receipt proves an unchanged Python AST and binds both file hashes. Production source was unchanged after the 25 Python passes. |
| Actual Chromium 155.0.8059.12 journey | **20 assertions passed at 17:30:13 UTC on 25 October**: seven actual policy GETs, one accepted four-byte TLS report, one real CORS preflight and two policy disconnects. |
| Fixture cleanup | At **17:31:41 UTC**, all seven contexts and the owned browser were closed; UI and TLS servers stopped, the temporary certificate profile was removed, and zero aggregates were published. |

The journey used the actual React controls, normal observation owner and real
`product_telemetry_policy` response function. The full service API route was
covered separately by the 25 Python checks. All **17 source inputs** still
matched the fixture-build inventory. Only the isolated fixture enabled its
in-memory disclosure; production remains false/null. There was no request
interception, production-memory operation or cloud-model call.

Disabled, narrowed-group, unreadable and slow policy responses prevented
collector contact while retaining spending and clearing the lease. Relaxing
policy did not widen the current page; reload observed the relaxation without a
refund. Cross-tab opt-out and synthetic CPU pressure each disconnected an active
policy request. Heap observations were real; CPU admission was synthetic and
certificate trust was limited to the temporary test CA. Neither endpoint
received seeded cookies, credentials or referrers. Browser/network metadata
still reach ingress; this does not establish production anonymity.

The original private server launch failed to import the telemetry package until
its source import path was supplied. That failure remains preserved. A missing
logo in the private fixture also produced an HTTP 500 resource-console error;
there were no uncaught JavaScript exceptions. Copying the actual logo produced
a byte-identical HTTP 200 response at **17:30:55 UTC**, without replaying the
policy journey. Neither fixture correction changed product code.

SHA-256 provenance of the original local logs; raw logs are not published:

| Evidence | SHA-256 |
| --- | --- |
| Original browser source failure | `6cd641a6d6b39fc7c7238c425ddf5bc8d071a69450fbd42b238c1af6b8ca9ce0` |
| Corrected browser source checks | `05ea9af047dda1324da6ec0e1a7a2bafe5f0f2cf603b7fb2ae0f9bdc201c0e53` |
| Python route/policy checks | `6fbf400b950857ca14f753d95fcd58e99308464aced621fe8159f582496fd101` |
| Successful frontend type-check log (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| Actual browser journey receipt | `0113e6a9f1be800f851df12d1676d8726f6a02557338aa6093cad3b05c0682a6` |
| Receipt-bound browser journey log | `129066a202562f805547dc33f8d7ab751fbd664f7fc326b9814e6207b5581a61` |
| Seventeen-input fixture inventory | `4591dc613dc1e7d52a0b55ed4b8c9c40d81dfdaa00080fec21b37cfaca7afccd` |
| Browser/context cleanup receipt | `52c69a442cb82312744fab5edfced6fa0ebd45a07ae83d3a69041261c06c8cea` |
| Server shutdown, final counts and profile cleanup receipt | `793c4cf609ebcf46c70509177177ec47988703c825719bd96a21f821fd4faa8b` |
| Original server import failure | `47cb71fb3c82561f4c92b1c9a5ad8e436a276a6db70ed05761e0009a7f6dd206` |
| Fixture logo recovery receipt | `53d240820879d508ff738a46c579e6ca7deb01172160352daa3ce43c6452f732` |
| Test-only formatting/AST receipt | `09a947d1035ceb06e03369cfcce203aa580ff23ef6eec62331add0cbe474ca06` |
| Final frontend build | `df0c88d6511dd35e9aad5b2a47294bf6247610ed6168a0ea62d6424e4ff9883b` |
| Final Ruff check | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |

## Remaining acceptance

The [full V08 contract](../implementation/anonymous-product-telemetry.md) is
unchanged. Unknown native metering still needs a declaration; browser sensor
availability is not actual sensor qualification. Full workflow/owner coverage,
whole-wire measurement, the **2 MiB added RSS / 0.5% CPU** resource limits and
all-platform installed/release acceptance remain open. No endpoint is selected.
Both the policy route and collector require production ingress, proxy/access/trace
log and metadata privacy review; response headers alone do not prevent logging.
The earlier cold-memory gaps remain evidence, not a reason to relax the target.
No production analytics, public anonymous-ingress or completed V08 claim follows
from these source checks.
