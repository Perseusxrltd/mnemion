# Product telemetry delivery components: source validation

**24 October 2026; unreleased source, V08 Building.** The
[delivery design](../implementation/anonymous-product-telemetry-delivery.md)
documents the component format and its limits. This checkpoint adds no sender,
persistent shared privacy/wire budget, installed integration, qualified ingress
or production collection. The [earlier local controls/aggregate evidence](2026-10-24-telemetry-aggregates.md)
and resource gaps remain unchanged.

The [source format](../../mnemion/product_telemetry/wire-v1.json) has **23 weighted
permitted views, 280 category values and 400 signed accumulator coordinates**.
Each report contains one randomized category representation in **four body
bytes**, excluding transport overhead. True-sign probability is **3/4**, with
conditional per-report **ε = ln(3)**; participation, policy and lifetime privacy
are not established.

| Source check | Result and scope |
| --- | --- |
| Initial Python | **25 passed**, in 1.66 seconds: full support/likelihood ratio over every view/category, expected estimator mean, permitted sampling, malformed input rejection, bounded accumulator erasure, closed-week output and in-process ASGI privacy boundaries. |
| Expanded Python selection | **47 passed**, in 4.89 seconds across wire, private publication and MCP checks. The final rerun after a test-only lambda lint correction passed **47 in 4.52 seconds**. |
| Node/TypeScript | **Six passed**, zero skips: exhaustive packet parity with Python, sampling parity, invalid input rejection, exact body preview and bounded unbiased CSPRNG draws. |
| Actual Electron 44.9.3 / Node 24.22.0 | **Six passed**, zero skips, for the codec selection. This is runtime evidence, not installed-package acceptance. |
| Actual plain-loopback HTTP journey | **12 checks passed** for the isolated codec, collector and private publisher. |

The initial ASGI checks used an in-process test client. The later journey used a
separate real HTTP server and private publisher, accepting **4,096 Python-encoded
reports plus one Node-encoded report**, each with a four-byte body. The Python
traffic took **6.329 seconds**, a journey observation rather than resource or
throughput acceptance. The closed report was immutable; later requests did not
replace it. Raw metadata was absent from stored output and the server log stayed
empty on success/error paths. Expiry erased the stored summary without another qualifying
window. Graceful lifespan completion erased volatile state, the process exited
zero and the temporary profile was removed. Production memory and cloud-model
calls were both **zero**, and product collection stayed unavailable.

Two earlier fixture failures remain preserved: missing source `PYTHONPATH`
stopped the driver before fixture creation/networking; a later driver incorrectly
expected exit zero after `SIGTERM`. The installed Uvicorn re-raises the signal
after graceful shutdown, and that first exit value was not captured. Only the
private fixture was corrected to request shutdown and inspect lifespan/erasure;
the original empty log and failed attempt remain retained.

This qualifies an isolated **plain HTTP codec/collector/publisher journey**. It
does not qualify a product sender, TLS/proxy/provider logging, production ingress,
all-platform behavior or resources. A four-byte body is not four bytes of network
traffic. The frontend build passed; full resource qualification remains pending.

A separate actual **Linux headless-app resource diagnostic** used Electron
44.9.3 / Node 24.22.0 after `client-ready`, completing **32 encodings of full
512-cell synthetic queues**. It measured **11.784 ms elapsed, 19.804 ms process
CPU and 126,328 additional retained JavaScript heap bytes**. Process CPU may
include concurrent work; it is not isolated codec CPU attribution. Net RSS fell
**405,504 bytes**, which is runtime/GC variation, not a memory-saving result or
proof of zero overhead. This probe made no sender/network, production-memory or
model calls. It does not qualify the unchanged **2 MiB added-RSS** or **0.5% of
one core** limits, replace the prior cold-memory gaps, or establish whole-app and
all-platform resource acceptance.

The saved utility study used **18 synthetic cases × 96 trials** at report counts
128, 256, 1,024, 4,096, 16,384 and 65,536 per view. Simultaneous interval coverage
was **95/96** for dominant outcomes at 128 reports and many rare features at
1,024; it was **96/96** in the other 16 cases. This is not a 100% coverage claim.
Cases below 4,096 are statistical diagnostics; the source output gate would
suppress those views regardless of their simulated interval result.

| Reports in one view | Conservative simultaneous half-width | Mean publishable categories in the many-rare-features case |
| --- | --- | --- |
| 4,096 | **13.495 percentage points** | **0** |
| 16,384 | 6.747 percentage points | 0.021 |
| 65,536 | 3.374 percentage points | 0.146 |

Rare features therefore remain mostly unavailable even at the largest simulated
size. The results assume independent, conforming reports; they do not count
distinct contributors or qualify adversarial submissions. Small deployments
cannot be promised precise fine-grained statistics at the proposed cadence.

The source emits only fixed closed-week reports with coarse count ranges and
rare-cell suppression. Daily/seven-per-week attempt and wire reservations remain
**unenforced proposals**. The new
[private SQLite publisher](../../mnemion/product_telemetry/publication.py) accepts
only validated, immutable closed-week JSON: **eight weekly rows, 64 KiB per report
and a 1 MiB database cap**, with no upsert or partial publication. Startup, reads
and publication prune expired windows; the active collector also invokes expiry
at week boundaries even without a qualifying new result. The source and isolated
HTTP checks cover these boundaries; deployed retention is not yet qualified.
Sender integration, budgets, TLS/provider/privacy and resource evidence,
production restart and backup-retention qualification, full utility qualification
and all-platform release remain open. All 66 requirement texts and states are
unchanged.

| Original evidence | SHA-256 |
| --- | --- |
| Version 1 format | `6901c93466c980b5ab27087e92f06eb515db21d04b95dc4a51844f460b3d8269` |
| Initial Python checks | `596df15679a6dd33a82c37670de940bdd0be74ac9ae3f97f71529d3d302f7d6a` |
| Expanded Python wire/publication/MCP checks | `beaa004a8b8a6e79420a650b42442a4d67057ed17c74e2e412052ab5c3b1084e` |
| Final Python wire/publication/MCP rerun | `145074d8116ab370491c07c9acee3b688a9ec67c953e10b8c45dac749cf9ce50` |
| Initial Node checks | `7cb04252d3f0bf09e394fa7204f667878dcfd793ef6bb9e1525c9fee377a55fd` |
| Actual Electron codec checks | `bbf50799abf5a7bfa644d82af4d0e88a39fc62e46642fc4d1271b5b02bfa0ba1` |
| Completed loopback HTTP journey | `ed6bb6b6813665e3e4748be1170acf7850ec65a372eb8e9e67f5967f5bfbf98e` |
| Graceful lifespan/volatile-erasure receipt | `12d58e4dc1d966099e634b981db4c9411be47318ca1a4cfda27a49f4c6c46361` |
| Original fixture-failure record | `07febf09182f2c128806297b9ec08134e2e8155a94f94a37e6451f93aebb2bee` |
| Headless-app codec resource diagnostic | `83744d1fdfc0b3fdb6e97686c1edeaf3128bde9f7ee41491f0a80b3723096054` |
| Synthetic utility results | `4608912e4766f44cebd3e613b0ae58b96be25fbccbae37f05aecebef3142618c` |
| Saved primary-source review | `4f6500f62261e638d18ccd31e078f718532d9dcf118cfdecf9420f0ad29435db` |
