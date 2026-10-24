# Telemetry application owners and connection controls

**24 October 2026; unreleased source, V08 Building.** This batch adds
connection preferences and opportunistic application-owner wiring. Final source
checks and a 19-assertion Chromium owner fixture passed. Browser CPU admission
was synthetic; these results do not qualify actual sensors or all platforms.
Production disclosure is still `collection_available: false`, `destination: null`;
the release-owned [route](../../mnemion/product_telemetry/transport-route.json)
has `address: null`. No endpoint or public telemetry release is activated.

The earlier [transport evidence](2026-10-24-telemetry-client-transports.md)
retains its 32 Electron passes/two Windows-only skips, 65 browser source passes
and 22 browser/18 native loopback collector checks. Those results do not qualify
this later owner batch. Prior main [CI 40078254710](https://github.com/Perseusxrltd/mnemion/actions/runs/40078254710)
completed successfully with 12 jobs; it is also earlier-source evidence.

## Connection choice and migration

The [privacy page](../../studio/frontend/src/workspace/Privacy.tsx), native
controls and [private-stdin schema](../../mnemion/product_telemetry/cli.py) expose
the optional `connection_mode` field. It applies to the private OS-account
installation or browser origin/profile, not a stored network identity.
The [maintained local MCP choice](../../mnemion/service/mcp.py) also accepts
the connection mode and disclosure version `0`. Omitted fields stay omitted
when forwarded to policy; HTTP callers cannot use these local controls.

| Choice | Source meaning |
| --- | --- |
| `auto` | Default; unknown metering refuses delivery. Wi-Fi/Ethernet alone is not evidence of an unlimited plan. |
| `unmetered` | Persistent user declaration resolving unknown metering only; detected data limits, pressure, offline state and privacy restrictions still refuse delivery. |
| `metered` | Pause delivery regardless of observed connectivity. |

[Python policy](../../mnemion/product_telemetry/policy.py) uses SQLite storage
version **5**; [browser choice](../../studio/frontend/src/workspace/telemetry-policy.ts)
uses version **4**, with the separate browser delivery budget still version 1.
The public control protocol remains unchanged. Supported migrations default
the connection choice to `auto` and retain the existing spent ledger/cooldown.
Explicit choice changes clear pending measurements and cancel the lease without
refunding attempts. Stale opt-out remains authoritative for disablement while
preserving a newer connection choice; omitting the field preserves it too.
Changing connection mode does not acknowledge an unseen disclosure. Damaged
settings still fail closed; this is not a repair mechanism.

An actual brief SQLite reader caused explicit opt-out to fail with
`telemetry_busy`; the original regression is preserved. Explicit `configure`
now permits **up to 250 ms per busy lock**. This is not a single 250 ms deadline
for the entire action or a guarantee against a persistent lock. Producers and
delivery retain zero lock waiting; no retry queue or spending refund is added.

## Owners and active conditions

| Source owner | Admission and lifetime |
| --- | --- |
| [Desktop activity](../../studio/electron/telemetry-activity.ts) and [service bridge](../../studio/electron/service-bridge.ts) | A committed owned local observation offers delivery after its SQLite transaction closes. The existing app lifetime owns the attempt; quit/suspend cancel it. Resume restores eligibility without starting a send. |
| [Browser activity](../../studio/frontend/src/workspace/telemetry-activity.ts) | An accepted observation offers work after its Web Lock releases. Page-owned pagehide/pageshow listeners cover the interval before deferred dispatch; offline, visibility and connection changes cancel active work. No service worker is added. |
| [Python activity](../../mnemion/product_telemetry/activity.py), [service lifespan](../../mnemion/service/api.py) and [maintained local stdio](../../mnemion/service/mcp.py) | One registered owner per private installation directory uses an existing loop. A committed local workflow supplies only its revision/generation stamp. Closing the lifespan cancels the attempt; a one-shot CLI creates no loop or keepalive. |

The [shared controller](../../studio/electron/telemetry-owner.ts) and Python
owner admit one active attempt with a one-minute eligibility throttle; an
explicit desktop/browser resume restores eligibility without starting work.
This is driven by newly offered work, not a timer or a scheduled wake.
The existing seven-attempt rolling week, minimum 24-hour-plus-jitter spacing,
five-second report lifetime and no-refund rules remain. Missed opportunities,
workflow inputs and results are not retained for retry; shutdown creates no report.

[Native](../../studio/electron/telemetry-conditions.ts) and
[Python](../../mnemion/product_telemetry/conditions.py) admission use local CPU,
available-memory and online observations. Python also consults the existing
background-admission guard; native thermal restrictions apply where exposed.
Missing/unusable required observations refuse work.
Neither currently supplies an OS metering detector, so unknown metering needs
an explicit unmetered declaration. These gauges remain local admission controls,
not analytics fields or proof of the whole-application resource limits.

[Browser conditions](../../studio/frontend/src/workspace/telemetry-conditions.ts)
treat data-saving/cellular and slow connections conservatively, require a visible
online page, and require fresh nominal CPU-pressure and usable heap observations.
Unsupported, denied or stale capabilities refuse delivery. The pressure observer
is bounded to the offered active opportunity and removed during cleanup; it is
not an idle sampler. Current browser capability coverage remains limited.

## Final source evidence

| Check | Result and scope |
| --- | --- |
| Python selection | **105 passed in 30.14 seconds**, including actual TLS through an existing loop/threaded workflow, shutdown/pressure cases and real local MCP choices/lifespan. |
| Actual Electron selection | **40 passed, two Windows-only ACL skips**, 42 total, in **17.387 seconds**; Electron **44.9.3 / Node 24.22.0 / Linux x64**. Includes ordinary desktop recording triggering TLS without manual reservation/sender calls. |
| Browser source selection | **68 passed**, zero failures or skips, in **7.468 seconds**. |
| Frontend | Type checks and production build passed; Vite reported **2.47 seconds**. Ruff source checks also passed. No release-pipeline result follows. |
| Actual Chromium owner journey | **19 assertions passed at 09:15:28 UTC**, Chromium **144.0.7559.96**; two new reports and two real CORS preflights were accepted by the actual loopback TLS Collector. |

The browser fixture used the actual React Privacy component and ordinary
`recordBrowserTelemetryMany` delivery owner, with no manual reservation/sender
call or request interception. It exercised automatic unknown-metering refusal
before any observer, connection editing while opted out, unseen-disclosure
preservation, cross-tab opt-out during a held response, critical-pressure refusal
and pagehide before deferred dispatch. Successful/aborted attempts retained the
spent allowance. Seeded cookies, credentials and referrers were absent; browser
Origin and other normal browser metadata remained visible at ingress.

**CPU-pressure admission was synthetic inside the isolated contexts.** Heap
readings and browser networking were real. The original browser exposed both
PressureObserver and heap interfaces, but interface availability and simulated
pressure values do not qualify actual sensor behavior. The fixture alone enabled
its in-memory disclosure and temporary certificate trust; production collection,
public certificate trust and whole-wire/resource limits remain unqualified.

The final receipt counts **two new reports**, distinct from the earlier failed
journey's one report and two preflights. Preserved cumulative server statistics
therefore show three reports and four preflights. By **09:17:01 UTC**, cleanup
verified all four isolated contexts, the owned browser, UI and TLS server closed,
the temporary certificate profile removed and **zero aggregate publications**.
There were no production-memory/model calls; observed browser traffic remained
within the isolated UI/Collector origins.

The earlier browser journey failed its count check. A private-runner diagnosis
showed `waitForFunction(async () => false)` returning false in **35 ms** instead
of timing out. The corrected fixture used finite polling that explicitly awaited
`page.evaluate` results; the final observed counts above are authoritative. This
was a harness correction, separate from the reproduced SQLite opt-out defect.
Both original failures remain preserved. The preceding **86 Python passes in
17.16 seconds** are retained as earlier evidence; the final selection has 105.

| Original evidence | SHA-256 |
| --- | --- |
| Final Python selection | `930548be00bf18d100ab8685bf8f4504b4698db57ebff0b75850ea799d070aa6` |
| Final actual Electron selection | `9c9a231d2bd97b5d0061164dbdcc6170cf29945a917a84532248b917f2664dcb` |
| Actual Electron runtime identity | `70e397bd879a2d87b87440390f537adda58f7b0fd228e4750145080e7d5b0732` |
| Final browser source selection | `e85caf71ba374efc1e065a801bb8d8d4e543800faaf6f5e81ea21ff70698bef8` |
| Frontend type/build log | `e60a2e755ef9a544f7c736ce635ff45a82761bcc4961faddf04700c07e397e5f` |
| Actual Chromium owner receipt | `5e7bf0c557368a7531dc5bac3eb6c4722ad3352959db042870a95a7bfd0b3fbe` |
| Browser fixture input manifest | `73f8aff245a919f6cf72f26c5c7cebbf1f967c80f6c3a510fb6cf857657b9216` |
| Browser cleanup receipt | `61e70fb1924b7b70835b37f3b5c69022679e1b674f93f4b6ab7facb40ca28f0e` |
| Final server/temporary-profile cleanup | `25e94b0317175500e250f6b24cd0b06c3c3fe2ee32057674ae165ff824f69ebd` |
| Original brief-reader opt-out failure | `2f1b8a3b1112062d715f1082eb55c817640062f5fa815530a741937bec130ce4` |
| Original browser count-check failure | `4ebac0a14aed8d20b5912204c5f91fe33be7728db168ab028ebebd42d529e5b0` |
| Private async-predicate diagnosis | `7c84a7a3e54c0b7744240bf8cf770d35bc1cb5081fe06be2af021027d182c96c` |
| Earlier 86-pass Python selection | `83a646a5ee85c195f353dbbd1dbff1e61fbfa0eabe9aca775cac78ad9e9abd77` |

## Outstanding acceptance

The source and isolated owner checks above do not complete delivery acceptance.
Fresh browser
organization-policy refresh, complete headless/workflow coverage, sensor behavior
on every platform, whole-wire/CPU/RAM measurements, public certificate/endpoint
and ingress-log privacy, collector/deployment retention and all-six-native plus
web release acceptance remain open. The unchanged **2 MiB added RSS / 0.5% of
one core** limits are not qualified by earlier component measurements.

Delivery ownership does not make remote API/MCP requests, unknown clients,
derived server jobs or mixed-host operational totals eligible for measurement.
Those privacy exclusions preserve the [full V08 scope](../implementation/anonymous-product-telemetry.md)
and its unresolved coverage; they do not complete it. All 66 requirement texts
and statuses remain unchanged.
