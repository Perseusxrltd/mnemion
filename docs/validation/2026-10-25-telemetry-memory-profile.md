# Telemetry denial hints and real-memory diagnostic

**Unreleased source checkpoint, 25 October 2026; V08 remains Building.** Focused
checks and both isolated diagnostic modes completed. They do **not** establish a
resource pass. Production collection remains false, with null destination and
route; all 66 requirement texts and states are unchanged.

## Source changes

The [native store](../../studio/electron/telemetry-store.ts) uses ordinary numeric
file statistics and a scalar snapshot scope; the
[workflow boundary](../../studio/electron/telemetry-workflow.ts) shares its default
clock function. Exhausted scopes merge only under the same private file version,
day and original monotonic expiry. Merging does not extend the 60-second limit.
Precision or file-version races can only suppress extra optional samples.

The [renderer policy adapter](../../studio/frontend/src/workspace/telemetry-policy.ts)
passes the fixed workflow through the [snapshot bridge](../../studio/electron/service-bridge.ts),
which fixes the surface to `desktop`; the store checks catalog membership.
Accepted observations, reservations and final handoffs retain fresh policy,
generation/revision and private-storage fences. No positive consent cache, idle
timer or change to spent allowance is introduced.

## Real-memory diagnostic

The [pipeline runner](../../deploy/probe_telemetry_pipeline.py) adds
`--memory-workload`, using a [disposable real API/PostgreSQL fixture](../../deploy/telemetry_memory_fixture.py)
with non-owner service roles. At **19:45:01 UTC**, all three variants completed
**128 save/fetch/lexical-search cycles, 384/384 successful API requests each**.
Each saved memory was fetched unchanged and returned by lexical search.

The [prepared wrapper](../../studio/electron/scripts/prepare-telemetry-memory.mjs)
uses the actual SDK and [`measuredStudioClient`](../../studio/frontend/src/workspace/measured-client.ts)
with a supplied native store in the main process. Requests use actual
`workspaceFetch` and Electron `net.fetch` over loopback HTTP. The runtime was
**Electron 44.9.3 / Node 24.22.0, Linux x64**. This is not renderer/IPC or installed
proof. The four-dimensional embedder is a protocol fixture with no model calls.

The [probe](../../studio/electron/scripts/probe-telemetry-pipeline.mjs) starts its
baseline after real app bootstrap and includes cold first-operation costs in
every variant. There is no forced GC or idle padding. Gauges are actual; unknown
metering is resolved by an explicit fixture-only unmetered declaration.
Main-process figures exclude API/PostgreSQL and Chromium network-service
process costs, startup and static-module costs outside that baseline.

| Variant | Process CPU (ms) | Elapsed (s) | Ending RSS growth (bytes) | Sampled peak growth (bytes) |
| --- | --- | --- | --- | --- |
| Collection unavailable | 2,714.580 | 94.066 | 13,656,064 | 16,203,776 |
| Collection-capable fixture, saved opt-out | 2,495.809 | 96.246 | 16,003,072 | 19,353,600 |
| Collection-capable fixture, enabled | 2,405.791 | 95.557 | 18,276,352 | 18,276,352 |

Enabled ending growth exceeded unavailable by **4,620,288 bytes (4.41 MiB)**,
while their sampled-peak difference was **2,072,576 bytes (1.98 MiB)**. Enabled
ending growth exceeded opted-out by **2,273,280 bytes (2.17 MiB)**. The lower
peak difference cannot establish a 2 MiB pass. Negative CPU differences are
run/runtime variation, not evidence that telemetry speeds up memory work.
One fixed sequence does not qualify representative-workload CPU or whole-app RSS.

The enabled variant accepted **64 paired records** from selected UI workflows
(the ownership catalog excludes some ordinary calls), one four-byte TLS report
and one spent **65,536-byte reservation**. Its lease cleared and database was
24 KiB. Unavailable/opted-out variants made no telemetry writes or reports.
Reserved bytes do not measure full wire cost.

## Original synthetic mode and source checks

The default **544-call synthetic instrumentation mode** completed at
**19:46:44 UTC** on the same source:

| Variant | Process CPU (ms) | Added RSS (bytes) |
| --- | --- | --- |
| Collection unavailable | 7.249 | 540,672 |
| Saved opt-out | 18.852 | 3,424,256 (3.27 MiB) |
| Enabled | 170.015 | 6,909,952 (6.59 MiB) |

Enabled collection accepted 32 paired records and one four-byte report; its
single reservation remained spent, lease cleared and database was 24 KiB.
Both other variants made no telemetry writes or reports. These results do not
show an overall RSS reduction or meet the 2 MiB target. The earlier
[6.40 MiB enabled observation](2026-10-25-telemetry-producer-overhead.md) and
[OS-component measurements](2026-10-25-telemetry-native-conditions.md) remain
separate historical evidence, not replaced by this run.

Focused checks passed: **22 actual Electron tests with two Windows-only skips**
(24 total, 19.115 seconds), **91 frontend checks** in 9.197 seconds, native build
and frontend TypeScript/Vite build (4.23 seconds). The first memory run's
duplicate `measuredStudioClient` declaration failed before workload results;
the fixture alias and pre-start syntax check corrected it. That failure remains
preserved. Process-map experiments using SIGSTOP remain diagnostic only.

Both completed modes verified profile removal, stopped collectors and removed
temporary certificate trust. They published zero aggregates and made zero
production memory/model calls. Their **390 real-memory and 185 synthetic
source/build inputs** still matched when reviewed; original receipts were retained.

## SHA-256 provenance

| Original evidence | SHA-256 |
| --- | --- |
| Real-memory receipt | `c55029fea90bf0bc11722836d223d61f33c21fa7af257e9f7c00f0a8d0b3e67f` |
| Real-memory 390-input inventory | `f11599f6922982ed03e83632f80306415dc092dd6628b5935846cea428b2eb91` |
| Synthetic receipt | `685b9219515ce0f9026ca3b4c9f090d6d001dd0a66acb3c1c721090955c7af7b` |
| Synthetic 185-input inventory | `1077887f7e32c84fbfb3ce2cbc99efb0fc7260079efd6114f0e7b57850d072f3` |
| Cleanup receipts, identical contents for both runs | `c52b943d5363ce402d72c37f33f89cbeaa3c7b9444744746e3d867040c4584dc` |
| Electron checks | `1586eb687877d933028e8fc2e005282e3e42c07fbb77f8cdbfdf97db9df70dd3` |
| Frontend checks | `a05742b9f1562940b20340da50074676ba5af75047487d3c6d87a30d34ecb9cb` |
| Native build | `d6c88c1616d194ec9efcfcb3452aba2a266884a087e8fff900fdafce023ecfc4` |
| Frontend build | `bae953cd2c1ce5a0cb1e47ac8beecffef7c4669aa0cb9a7febd86d842ca0c3af` |
| Original generated-fixture failure | `7d7a5979646fce9080f29249dd0e864d5e4572cea3c8feaf667a1b2a65a59ba1` |

The [full contract](../implementation/anonymous-product-telemetry.md) retains its
**2 MiB added-RSS and 0.5% of one core averaged over representative work** targets.
Renderer/IPC, full process costs, all-six-native plus web, whole-wire cost and
production collector/ingress privacy remain unqualified. These diagnostics do
not establish a released telemetry feature.
