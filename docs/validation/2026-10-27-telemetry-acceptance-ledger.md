# V08 acceptance ledger — 27 October 2026

Initial reviewed source: `1b57752f79b4d232a5c5eca1995f1d3f07d50090`, subsequently
reconciled with the [verification follow-up](2026-10-27-telemetry-update-verification.md)
based on `e03513dfba4817025e9fe8b1a8428268b1671c6b` and the
[capture administration follow-up](2026-10-27-telemetry-capture-admin.md) based on
`626e25ea3e8084e788b5564db19f92663f29bf7d`. **V08 remains
Building**; collection/destination/route remain **false/null/null**, with release
CAs empty. The [66 requirements](../PRODUCT_REQUIREMENTS.md) and
[canonical acceptance contract](../implementation/anonymous-product-telemetry.md#required-acceptance-evidence)
are unchanged. This ledger reconciles evidence; it does not replace requirements
or qualify one platform from another platform's result.

The latest coverage checkpoint is [catalog v2 compatibility](2026-10-27-telemetry-catalog-compatibility.md),
integrated on main at `56bb40a01f5736c742be0d95add5a54beb605971` with
[source CI 40517759157](https://github.com/Perseusxrltd/mnemion/actions/runs/40517759157).
Its source/component checks do not qualify the pending native release or full
installed acceptance.

“Implemented” means present in source. “Scoped evidence” applies only to the
linked source, fixture and behavior. Every item in the last column remains
required for full acceptance.

| Area | Implemented | Scoped evidence | Still required |
| --- | --- | --- | --- |
| Workflow coverage | [Catalog v2 and action preview](../implementation/anonymous-product-telemetry-catalog.md): 96 of 96 categories mapped, including dedicated `capture.split` and `models.test`. Eight interfaces feed seven checked owner categories; 701 rows comprise 398 mapped, 295 excluded, eight delegated and zero unmeasured declarations. | [Catalog compatibility](2026-10-27-telemetry-catalog-compatibility.md): 322 distinct checks passed (175 Python, 136 browser-source, ten native wire and one native SQLite/Python upgrade), with no failures or skips; Electron build and frontend typecheck passed. The original 94 numeric IDs and saved budgets retain their meanings; four-byte wire v2 keeps its domains/weights, while report schema 4 preserves immutable schema 1–3 reports. Split preview remains excluded. The historical catalog-v1 checkpoint had 94 mapped categories and 700 rows: 396 mapped, 294 excluded, eight delegated and two unmeasured. [Earlier CLI variants and outcomes](2026-10-27-telemetry-cli-outcomes.md): 128 distinct Python passes (125 unchanged plus three corrected fixtures), one browser-source preview pass and SDK/frontend builds. Invocation-only suppression preserves saved policy; repair dry-run now stops before extraction/backup/delete/rewrite. Its 63 classic rows include 32 mapped, 29 excluded and two unmeasured. The [earlier CLI follow-up](2026-10-27-telemetry-cli-coverage.md) retains 66 Python and one preview check, nine mapped paths and its 51-row/29-unmeasured checkpoint. The preceding 637-row/zero-unmeasured inventory remains historical. [Capture administration](2026-10-27-telemetry-capture-admin.md): 106 distinct Python, 22 SDK and 49 Studio/policy source checks qualified; two app buttons use scoped owners and five capture mutations require fresh receipts. A reproduced grant binding race was fixed. [Verification follow-up](2026-10-27-telemetry-update-verification.md): 91 Python, 48 compiled Node and 29 browser-source checks passed. Linux needs fresh transfer plus successful completion and has no phase timing or opaque-failure classification. [MCP evidence](2026-10-27-telemetry-mcp-interfaces.md) and earlier map tests remain retained. | Reconcile hand-parsed options, other entrypoints, actual call sites and autonomous work. Zero unmeasured declarations does not prove complete product-workflow ownership. Authentication or a host preference cannot authorize unowned remote-client telemetry. Mapped categories and declarations do not establish complete runtime coverage. |
| Choice, review and persistence | Offline privacy controls, first-time disclosure, restrictive company policy, shared native/Python state, browser-local state, exact inspection, approval and discard. [Company-path correction](2026-10-27-telemetry-company-path.md) denies invalid ancestors and failed reads after stat. | [4.46.22 installed controls](2026-10-26-telemetry-installed-review.md) qualify eight telemetry fields on six targets. [Setup follow-up](2026-10-27-telemetry-setup-disclosure.md) passed ten compiled-browser checks and a separate ten-check Linux source-app journey over two launches, with 2,100 source files matched and cleanup. Earlier app/browser results remain retained. | Final installed app/agent/headless journeys on all six targets: disclosure, company precedence, unreadable state, restart/update, opt-out and empty re-enable. Complete web owner/cancellation/storage-loss qualification; its temporary certificate exception does not qualify production trust. |
| Delivery and reliability | [Shared budgets and cancellation](../implementation/anonymous-product-telemetry-budget.md), opportunistic owners, bounded queues and native/Python/browser transports. [Explicit native/Python trust](2026-10-26-telemetry-scoped-trust.md) retains hostname verification. | Source and isolated TLS checks; the compiled app/browser journeys each delivered one approved four-byte report matching inspection. The [browser/Python saturation follow-up](2026-10-27-telemetry-owner-saturation.md) qualifies 137 distinct Python and 96 mocked browser-source checks, including the separately corrected legacy MCP schema assertion. It adds no timer, lifetime or allowance and has no current app/platform qualification. The [saturation correction](2026-10-27-telemetry-delivery-opportunity.md) passed 50 actual Electron owner/TLS and five browser-activity source checks: later awake work can reoffer a prior committed stamp through refused scoped snapshots or recording, without new collection or budget. The 50 include the earlier 47; this does not establish the failed app comparison's cause. The [five-case Python loopback measurement](2026-10-27-telemetry-loopback-wire.md) counted segmented IPv4/TCP/TLS traffic with two agreeing counters and no retained raw packets. The [seven native sender cases](2026-10-27-telemetry-native-wire.md) add matching segmented counters in Electron/Node on Linux x64; all passed, including owner delivery, opt-out and a 53,683-frame-byte oversized reply. This remains same-process loopback component evidence. | Sentinel checks across body, headers, URLs, queues and ingress; real-memory offline/metered, DNS/TLS/error, suspension and saturation journeys; final-send opt-out across owners/processes. Substantiate total wire cost, retry bounds and tail latency, including the 256 KiB rolling-day wire ceiling. |
| Resources and sensors | Bounded storage/owners, pressure/network admission and allocation corrections. The [confirmed-opt-out hint](2026-10-27-telemetry-disabled-hint.md) avoids a duplicate native SQLite read while retaining its original deadline and fresh authority gates. | The [SQL-read follow-up](2026-10-27-telemetry-sql-reads.md) passed 123 source tests in Node 22.22 on Linux x64, with zero failures and two Windows-only skips; the Electron build passed. Fresh authority checks remain; those Node tests are not an actual app journey or measured saving. The later [SQL app comparison](2026-10-27-telemetry-sql-comparison.md), run 40523504727 on `3034bc0b`, qualified six actual Electron functional cases with 2,171 source bindings each, ownership controls and cleanup. Enabled main matched RSS maxima 2,572,288 / 2,859,008 bytes still exceed 2 MiB; the first renderer/GPU comparisons also exceed it. Resource acceptance remains false and CPU is descriptive. The negative-hint source group passed 116 actual Electron tests, with zero failures and two Windows-only skips; 623 inputs were unchanged. This is no measured resource saving or enabled-mode qualification. The [later desktop delivery comparison](2026-10-27-telemetry-delivery-comparison.md), run 40483350394 on 29dcd70d, qualified all six functional journeys, 2,143 source bindings per case, actual controls and cleanup; enabled main matched RSS maxima 3,768,320 / 3,129,344 bytes still fail 2 MiB. It predates the current browser/Python changes. The [earlier process-role comparison](2026-10-27-telemetry-resource-roles.md), run 40453953300 on `6ac77003`, passed six functional cases with 2,114 matched source files each, 2,322 successful fixture API requests, verified app main/renderer identities and cleanup. Without allocation attribution, both enabled main and all enabled/opted-out renderer comparisons still exceeded 2 MiB at matched phases. CPU remains descriptive; resource acceptance is false. The [original 4.46.32 failure](2026-10-27-telemetry-metadata-allocation-results.md), renderer ambiguity and all earlier outcomes remain retained. | Meet **2 MiB added RSS per participating process** and **0.5% of one core** over representative work; qualify supported sensors, other process roles and tails. Neither comparison samples nor component counts establish causal savings or general CPU qualification. The [fixed-catalog source checks](2026-10-27-telemetry-catalog-residency.md) remain scoped; its [original six-case comparison](2026-10-27-telemetry-catalog-comparison.md) failed with no second enabled reservation/delivery and no summary. Its cause remains unresolved; the later changed-source functional pass does not rewrite or retry that original. No causal resource saving is established. The completed SQL app comparison provides scoped functional evidence while retaining a failed resource result; it does not establish installed/platform acceptance. Budgets remain unchanged. |
| Collector, ingress and retention | [Bounded collector and publisher](../implementation/anonymous-product-telemetry-collector.md), metadata removal and fixed aggregate retention. | Isolated collector checks plus the [read-only provider review](2026-10-26-telemetry-ingress-review.md). That review found no production collector/listener and established only a free TLS candidate. The earlier [Linux crash-boundary follow-up](2026-10-27-telemetry-crash-boundary.md) retains 19 source cases. The [serving-process crash follow-up](2026-10-27-telemetry-collector-crash.md) passed 21 total cases, including two real TLS-process SIGABRT cases on Linux/WSL2 with a piped core handler and clean fixture state. All 435 selected inputs matched; runtime protection was unchanged. This qualifies the stated Linux process boundary, not installed service or provider retention. | Qualify the actual endpoint and certificate rotation, firewall/proxy/CDN/WAF/error/monitoring and production crash-handling paths, and backups. Ten logging targets, weekly/four-rotation UFW retention and a persistent journal remain unqualified. Hostinger's public policy/DPA do not verify this VPS's traffic or snapshot settings; the process guard does not control privileged host/provider snapshots. |
| Anonymity and useful aggregates | [Wire-v2/report-v3 selection rules](2026-10-26-telemetry-review-selection.md): randomized automatic categories, fixed manual body, bounded contributions and suppression. | Codec/selection checks support their stated conditional bounds. Manual reports contribute only to coarse volume; they establish no categorical, participation or network-anonymity guarantee. | Architecture/privacy and utility evidence for linkage, rare/coincident cohorts, repeated contributions, auxiliary information, suppression and difference attacks. Counts must remain sampled usage, not unique people or devices; no identifying workaround is permitted. |
| Final release | Normal source, native, artifact-verification and public release gates. | [4.46.29 publication](2026-10-27-release-scan-boundary.md) verified 38 unchanged original assets. The [later source follow-up](2026-10-27-telemetry-mcp-interfaces.md#release-qualification-follow-up) passed 30 CI-scope checks and 40 actual Windows x64 storage checks. | Qualify the final implementation on Linux, Windows and macOS x64/ARM64 plus web, including supported restart/update and public distribution. Source-component tests do not qualify installed delivery, Windows ARM64 or provider/resource/privacy acceptance. |

## Actual systemd credential rotation

The [28 October host qualification](2026-10-28-telemetry-systemd-rotation.md)
adds eight recorded checks of the repository's collector service and
credential command, with 440 source files bound to `772f5c0b`. Synthetic A/B
certificates exercised a real restart and two HTTP 204 reports over loopback;
old trust was refused, unchanged material did not restart, and a stopped
service stayed inactive. One report database had zero completed-window
reports; cleanup passed. The original `200/CHDIR` fixture failure remains
retained and is explained by its inaccessible parent directory.

This qualifies only the isolated Linux systemd rotation journey. Actual issuer
renewal, public ingress/provider/privacy, installed delivery, whole-wire and
resource acceptance remain required. Production settings, budgets, all 66
requirements and V08's Building state are unchanged.

## Actual systemd crash and automatic restart

The [29 October host qualification](2026-10-29-telemetry-systemd-crash.md)
adds six recorded checks on the same 440-file collector archive. One owned
`SIGABRT` produced signal termination without the kernel core-dump flag;
systemd performed one configured automatic restart, with successful synthetic
TLS reports before and after. Independent cleanup inspection passed.
The file-handler host result remains distinct from the earlier WSL
piped-handler checks. Public ingress/provider retention, resources, whole-wire,
installed platforms/workflows and broader privacy/utility acceptance remain
open. Production collection and V08's Building state are unchanged.

## Setup recovery follow-up

The [refused observation follow-up](2026-10-27-telemetry-refused-results.md)
reproduces four cases where the frontend still inspected result/error metadata
without an admitted measurement. The corrected owners preserve the action and
its outcome without that classification. All 53 focused owner/policy tests and
SDK/frontend builds passed, including late permission replies and exact-once
callbacks. Source evidence establishes no prior transmission, new resource
saving, complete runtime coverage or installed/platform acceptance.

The [current setup correction](2026-10-27-telemetry-setup-recovery.md) retains
three reproduced UI failures and passes 11 actual compiled-browser recovery
checks plus 29 policy-control tests. Failed current reads remove stale enable
controls; uncertain saves read actual state without write retries. The saved
policy remains authoritative, and the fixture's simulated native replies do not
qualify installed storage, provider, resource or full telemetry acceptance.

## Action timing follow-up

The [Python owner correction](2026-10-27-telemetry-agent-timing.md), prepared on
`6ac7700312e9c77a9793cd6e740419f1b39e2c5e`, includes optional policy/contribution
reads in action latency. Both reproduced timing regressions now persist the
correct bucket; 135 focused owner checks passed. Existing consent, generation,
replay and contribution fences remain. This does not close runtime coverage,
resource, installed or privacy acceptance.

## Aggregate utility at current settings

The [aggregate privacy follow-up](2026-10-27-telemetry-aggregate-privacy.md)
adds 46 exact known-background scenarios across 23 views, linked-report
inference calculations and explicit unprotected participation/policy controls.
Seventy distinct source tests include competing SQLite publisher connections
and refused difference-query routes. Those checks substantiate the conditional
single-category bound and missing rare-cell values in the stated fixtures;
they do not establish participant/lifetime/network anonymity, useful-population
statistics, actual provider privacy or the whole aggregate acceptance group.
Production collection and the unchanged resource/platform gates remain open.

The [configuration-bound analysis](2026-10-27-telemetry-aggregate-utility.md)
preserves all 23 views and 280 aggregate categories. With all groups enabled,
1,000 stores contributing the optimistic seven accepted reports each yield
only 1,093.75 family / 437.5 feature reports in expectation, below the 4,096
detail minimum. Four deterministic mean fixtures demonstrated broad estimates
and rare-cell suppression; they do not qualify sampling coverage or real
adoption. Linked reports compose the conditional category bound at most as
`n ln(3)`, without participation, lifetime or identity protection. Detailed
initial-adoption utility and aggregate privacy/attack evidence remain required;
no threshold, resource budget or acceptance state changed.

## Receive-window finding and scoped correction

The [Python burst follow-up](2026-10-27-telemetry-receive-window.md) retained an
original observation of **123,053 frame bytes** despite charging only **21,683
TLS bytes**, exceeding the unchanged **65,536-byte** attempt reservation. With
the pre-connect receive-buffer bound, the corrected case observed **23,110
frame bytes**; 32 transport tests passed. Both observations refused
the malformed response, retained spending and cleared the lease. This is a
Linux IPv4/Python component result, with two agreeing counters and zero capture
drops. The original five-case limits remain; total wire/retransmission, IPv6,
other-platform, Electron/browser and rolling-day qualification remain required.

## Native controls in diagnostic fixtures

The [source-kernel control diagnostic](2026-10-27-telemetry-probe-controls.md),
original run **40470335733** on `d56d578f`, remains **failed**. All three cases
completed 128 memory cycles and 387/387 API requests, with cleanup. Actual
opt-out correctly cleared disclosure acknowledgement and produced no telemetry
writes or reports; the new validator incorrectly required acknowledgement.
The corrected validator passed 35 report tests and Ruff without an app rerun.
Original receipts and the earlier 33-test/19-assertion stages remain historical.
Completed retained-evidence analysis matched 2,130 source inputs per case and
confirmed all three recorded control states, with four further private mutation
assertions. It preserves the original failed workflow and false opt-out journey
flag; resources and installed/privacy acceptance remain unqualified, with all
earlier resource failures retained.

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

A later retained observation at 02:52 UTC confirms
[4.46.34 publication](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.34)
with 38 assets. Native run 40433580410, artifact verification 40438996406,
website sync 40439536199 and public update checks 40439538705 all passed.
That release precedes the setup and verification source follow-ups and does
not qualify full telemetry or an upgrade of a particular user's installation.

Full acceptance still requires the canonical six evidence groups and complete
native/web target journeys: actual outbound sentinel proof, persistent policy,
opt-out during interruption, resource/reliability limits, deployed-ingress
privacy, and aggregate attack/utility evidence. Final receipts must bind the
reviewed implementation and published artifacts.
