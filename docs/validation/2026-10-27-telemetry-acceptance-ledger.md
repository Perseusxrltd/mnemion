# V08 acceptance ledger — 27 October 2026

Reviewed source: `1b57752f79b4d232a5c5eca1995f1d3f07d50090`. **V08 remains
Building**; collection/destination/route remain **false/null/null**, with release
CAs empty. The [66 requirements](../PRODUCT_REQUIREMENTS.md) and
[canonical acceptance contract](../implementation/anonymous-product-telemetry.md#required-acceptance-evidence)
are unchanged. This ledger reconciles evidence; it does not replace requirements
or qualify one platform from another platform's result.

“Implemented” means present in source. “Scoped evidence” applies only to the
linked source, fixture and behavior. Every item in the last column remains
required for full acceptance.

| Area | Implemented | Scoped evidence | Still required |
| --- | --- | --- | --- |
| Workflow coverage | [Catalog and action preview](../implementation/anonymous-product-telemetry-catalog.md): 94 categories, 93 mapped; `update.verify` remains independently unmeasured, distinct from download/staging. Seven interfaces feed six checked owner categories; 632 rows are mapped, excluded or delegated. | [MCP follow-up](2026-10-27-telemetry-mcp-interfaces.md): 57 source/compatibility passes; both MCP interfaces now contribute independent registry evidence. Existing map tests and original failures remain retained. | Reconcile actual call sites, autonomous work and unlisted interfaces. Authentication or a host preference cannot authorize unowned remote-client telemetry. Zero unmeasured declaration rows is not complete runtime coverage. |
| Choice, review and persistence | Offline privacy controls, restrictive company policy, shared native/Python state, browser-local state, exact inspection, approval and discard. [Company-path correction](2026-10-27-telemetry-company-path.md) denies invalid ancestors and failed reads after stat. | [4.46.22 installed controls](2026-10-26-telemetry-installed-review.md) qualify eight telemetry fields on six targets. Later compiled [Linux app](2026-10-26-telemetry-app-review.md) and [browser](2026-10-26-telemetry-browser-admission.md) journeys passed nine and ten review checks. | Final installed app/agent/headless journeys on all six targets: disclosure, company precedence, unreadable state, restart/update, opt-out and empty re-enable. Complete web owner/cancellation/storage-loss qualification; its temporary certificate exception does not qualify production trust. |
| Delivery and reliability | [Shared budgets and cancellation](../implementation/anonymous-product-telemetry-budget.md), opportunistic owners, bounded queues and native/Python/browser transports. [Explicit native/Python trust](2026-10-26-telemetry-scoped-trust.md) retains hostname verification. | Source and isolated TLS checks; the compiled app/browser journeys each delivered one approved four-byte report matching inspection. The [five-case Python loopback measurement](2026-10-27-telemetry-loopback-wire.md) counted segmented IPv4/TCP/TLS traffic with two agreeing counters and no retained raw packets. | Sentinel checks across body, headers, URLs, queues and ingress; real-memory offline/metered, DNS/TLS/error, suspension and saturation journeys; final-send opt-out across owners/processes. Substantiate total wire cost, retry bounds and tail latency, including the 256 KiB rolling-day wire ceiling. |
| Resources and sensors | Bounded storage/owners, pressure/network admission and allocation corrections. | [Original 4.46.32 resource diagnostic](2026-10-27-telemetry-metadata-allocation-results.md): six functional cases and cleanup passed; resource qualification failed. Earlier sensor/refusal and allocator outcomes remain retained. | Meet **2 MiB added RSS per participating process** and **0.5% of one core** over representative work; qualify supported sensors, other process roles and tails. Profiled samples and component counts establish no causal savings. No new resource measurement or budget change is selected. |
| Collector, ingress and retention | [Bounded collector and publisher](../implementation/anonymous-product-telemetry-collector.md), metadata removal and fixed aggregate retention. | Isolated collector checks plus the [read-only provider review](2026-10-26-telemetry-ingress-review.md). That review found no production collector/listener and established only a free TLS candidate. | Qualify the actual endpoint and certificate rotation, firewall/proxy/CDN/WAF/error/monitoring paths and backups. Ten logging targets, weekly/four-rotation UFW retention and a persistent journal remain unqualified. Hostinger's public policy/DPA do not verify this VPS's traffic or snapshot settings. |
| Anonymity and useful aggregates | [Wire-v2/report-v3 selection rules](2026-10-26-telemetry-review-selection.md): randomized automatic categories, fixed manual body, bounded contributions and suppression. | Codec/selection checks support their stated conditional bounds. Manual reports contribute only to coarse volume; they establish no categorical, participation or network-anonymity guarantee. | Architecture/privacy and utility evidence for linkage, rare/coincident cohorts, repeated contributions, auxiliary information, suppression and difference attacks. Counts must remain sampled usage, not unique people or devices; no identifying workaround is permitted. |
| Final release | Normal source, native, artifact-verification and public release gates. | [4.46.29 publication](2026-10-27-release-scan-boundary.md) verified 38 unchanged original assets. The [later source follow-up](2026-10-27-telemetry-mcp-interfaces.md#release-qualification-follow-up) passed 30 CI-scope checks and 40 actual Windows x64 storage checks. | Qualify the final implementation on Linux, Windows and macOS x64/ARM64 plus web, including supported restart/update and public distribution. Source-component tests do not qualify installed delivery, Windows ARM64 or provider/resource/privacy acceptance. |

## Retained failed resource result

Run **40416923461** matched **2,075 source inputs per case**. Enabled main
matched maxima were **9,261,056 / 2,936,832 bytes**; ending matched-phase
differences were **9,261,056 / 1,593,344 bytes**. Both maxima exceed 2 MiB.
The first enabled renderer comparison is ambiguous; both orders and every
available role remain in the original report. CPU is descriptive profiled
evidence, not qualification. The unchanged **2 MiB / 0.5%** resource gate has
not passed; no causal regression or production-only overhead is inferred.
The [evidence index](telemetry-evidence-index.md) retains all earlier failures,
rejected experiments and scoped passes. No receipt is superseded by this ledger.

## Release checkpoint and final proof

At this review, the public release is **4.46.29**. Original native run
**40426432624** for 4.46.33 retains both Windows Unicode-fixture failures;
the 4.46.34 correction is on main at
`e18b495cdf554f682a4a2be0f1f2498e9d934fc4`. Its release driver waits for source
CI **40430021395**; native 4.46.34 has not been dispatched at this checkpoint.
The 4.46.33 native run completed with the two retained Windows failures.
These are dated observations. The generated
[release-status document](../RELEASE_STATUS.md) owns current availability.

Full acceptance still requires the canonical six evidence groups and complete
native/web target journeys: actual outbound sentinel proof, persistent policy,
opt-out during interruption, resource/reliability limits, deployed-ingress
privacy, and aggregate attack/utility evidence. Final receipts must bind the
reviewed implementation and published artifacts.
