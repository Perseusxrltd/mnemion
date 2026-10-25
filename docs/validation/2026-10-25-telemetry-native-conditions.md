# Native telemetry network admission

**Unreleased source checkpoint, 25 October 2026; V08 remains Building.** A shared
OS-cost helper and desktop/Python admission checks now have focused source and
actual component evidence. Production remains `collection_available: false`,
`destination: null`, with a null release route address. The public 4.46.6 release
is unchanged; all 66 requirement texts and states retain their scope.

## Source boundary

The [shared C implementation](../../mnemion/product_telemetry/native/network-state.c)
exposes fixed flags through its
[Node-API bridge](../../mnemion/product_telemetry/native/network-node.c) and
[Python loader](../../mnemion/product_telemetry/network.py). It reads Windows
`GetNetworkConnectivityHint`, macOS Network path state or Linux NetworkManager
cost/connectivity. The [implementation notes](../implementation/anonymous-product-telemetry-delivery.md#native-os-cost-admission)
record each mapping and primary Windows/NetworkManager references. macOS is not
yet compiled or accepted.

The Linux path opens only the local private system D-Bus connection, ignores
remote `DBUS_*` overrides and disables service auto-start. It reads only the
`Metered` and `State` properties; guessed unmetered state remains unknown.
Nonblocking pending calls and bounded dispatch enforce a 200 ms monotonic limit
per exchange, including authentication progress. The receive cap is 8 KiB and
the message cap is 4 KiB; replies carrying file descriptors are refused. The C
core emits no production logs.
None of these OS paths enumerates network names/addresses, changes settings or
probes the Internet. These are admission flags, not collected metrics.

The [desktop owner](../../studio/electron/telemetry-activity.ts) and
[Python owner](../../mnemion/product_telemetry/activity.py) check policy, queued
work and allowance read-only before starting gauges. Reservation separately
rechecks the conditions before spending. The
[native coordinator](../../studio/electron/telemetry-network.ts) and Python
equivalent wait up to one second for an initial OS read and reject readings at
least one second old **from query start**, including reply latency. Refresh is
requested only by existing active checks after 250 ms. There is no idle timer.
Cancellation stops queued work from invoking the OS and invalidates late
results; it does not terminate an OS call already running. No second call
overlaps that outstanding probe, and owner cleanup closes gauges.

The one-second limit is not an end-to-end preparation/resource guarantee: CPU
admission may also need a delta. Loss of OS support cannot erase an observed
metered/limited path. Explicit `unmetered` resolves unknown cost only, never
metering or constraints. Without the compiled helper, source/pip installs stay
unknown. Desktop and frozen-engine build wiring now includes that helper; this
does not establish installed-package acceptance. The
[reusable component probe](../../deploy/probe_telemetry_network.py) checks the
actual binary through matching Python and Node runtimes. Intel and ARM macOS
[CI steps](../../.github/workflows/ci.yml) were added but have not yet run.

## Final local checks and retained failures

These selections overlap; their counts are not a combined test total.

| Selection | Result and scope |
| --- | --- |
| [Python network checks](../../tests/test_product_telemetry_network.py) | **38 passed in 6.48 seconds**: strict flags, real private Unix-socket D-Bus, metered/guessed/limited transitions, wrong types, late replies, authentication stalls, queued-executor cancellation and freshness from query start. |
| [Node network checks](../../studio/electron/scripts/test-telemetry-network.mjs) | **10 passed**, no failures, cancellations or skips, in **1.505 seconds** under Node 22. These are not Electron app acceptance, despite the retained log filename. |
| Strengthened packaging checks | **19 passed in 3.32 seconds**, including rejection of a missing or nonbinary helper. |
| Earlier broad Python selection | **89 passed in 17.26 seconds** across owner, TLS, delivery, packaging and the earlier network implementation. This does not qualify later network changes. |
| Builds and lint | The final Electron source build and Ruff check passed. Frontend TypeScript/Vite passed in **2.56 seconds**, before the final documentation edits. |

The first broader **Node** selection had 38 passes and one cancelled fixture:
its only timer intentionally did not keep the process alive. Correcting only
the fixture lifetime gave an intermediate isolated eight-pass run; the product's
unref timer was unchanged. Both attempts remain preserved.

The first real Linux D-Bus selection failed three checks. Stalled authentication
exceeded two seconds despite the blocking API's requested 200 ms timeout; the
source now uses nonblocking pending calls and bounded dispatch. The missing
healthy replies had a separate fixture cause: its observer filter consumed
messages, and a reference D-Bus client also returned `NoReply`. The fixture now
returns `NOT_YET_HANDLED`. An intermediate source setting of zero aggregate
file-descriptor quota then prevented all reads; it was corrected to one while
the per-message quota stays zero, so descriptor-bearing messages remain refused.
The corrected three-check D-Bus run passed and is included in the final 38.

A final additional-detector guard preserves the OS's metered veto in
[desktop](../../studio/electron/telemetry-conditions.ts) and
[service conditions](../../mnemion/product_telemetry/conditions.py). Its separate
Python regression passed **one check, with 38 deselected, in 2.21 seconds**;
its Node regression passed **one check with no failures or cancellations in
104.8 ms**. The accepted selections above were not replayed for that change.

## Retained component measurements

Both observations below used actual Windows Node 25.2.1. They measure the
individual probe, not whole-app telemetry overhead or supported-platform
acceptance.

| Probe | Elapsed | Added RSS | Interpretation |
| --- | --- | --- | --- |
| Original COM implementation | **2,382.4622 ms** | **4,956,160 bytes** | Rejected: exceeds the one-second probe wait and the full-feature 2 MiB RSS target. Original artifact and failure receipt retained. |
| Earlier replacement connectivity-hint implementation, cold process | **14.7079 ms** | **2,224,128 bytes (2.12 MiB)** | Faster in this observation, but still above the unchanged full-feature 2 MiB RSS target. Not resource acceptance. |

The final actual component receipts record:

| Platform/runtime | Fixed flags | Elapsed | Added RSS |
| --- | --- | --- | --- |
| Linux x64, Python 3.12.3 | `0`: unknown | **5.323 ms** | Not measured |
| Linux x64, Electron 44.9.3 / Node 24.22.0 | `0`: unknown | **6.819 ms** | **2,342,912 bytes (2.23 MiB)** |
| Windows x64, Python 3.13.11 | `9`: observed unmetered | **1.549 ms** | Not measured |
| Windows x64, Node 25.2.1 | `9`: observed unmetered | **11.2614 ms** | **2,215,936 bytes (2.11 MiB)** |

The Linux receipt proves bounded unknown fallback on that system; cost-state
transitions are exercised in the separate private-bus fixture.
The Windows receipt captures one OS observation. The Windows runtime was Node,
not Electron. Both measured JavaScript components remain above the **2 MiB
full-feature RSS target**. None establishes whole-app resource, installed-client
or all-platform acceptance; Python RSS was not measured.

The final Linux binary still matches the actual Electron component receipt.
At **18:24:58 UTC**, cleanup verified that the owned Windows temporary probe
directory was removed and the earlier/replacement artifacts and hashes were
retained. The installed Windows app and production host were unchanged; no
production-memory or cloud-model calls occurred.

SHA-256 provenance; private raw logs and paths are not published:

| Evidence | SHA-256 |
| --- | --- |
| Rejected COM component receipt | `4bd829ecd450ba7517dd13fc848fc3a216a2197dd8492a0696fa3b65ca1626d0` |
| Replacement Windows build/probe log | `6c58931e16dc8382b891f19c6543f8341f9428f09f0044a36f858e9a16941740` |
| Initial Python selection | `41598a4c48b34765a5864e4b9302f534ed76bdda71021fd55ba64c58a707e010` |
| Original incomplete Node selection | `b527dac3362d7ca5995095f40537d7293af6bad7e1a846a50bd28bd53338f772` |
| Intermediate eight-pass Node selection | `6ac669069bb075e440233e2d4691a0d7219c574c6c90818f59a126825b9c8dea` |
| Original three-failure Linux D-Bus selection | `b8ed2c23010ff9c00309583b83a9b96a0ccbceb0bb0b99bb440f5b1471ad5fc6` |
| Reference D-Bus client/fixture diagnosis | `8b7a9db41be958edeb79943d6a493a7e637747586946e6031ec6e1895af96bac` |
| Intermediate aggregate-FD-quota failure | `b9544ac964435452419dcca9ed5af68d34afeb0ac120646b591af39c30285cba` |
| Corrected three-check D-Bus selection | `e3774f61f4b5e3a8f1a930633c4275b3f2c99fcd5ccbffd20ca293a080c50631` |
| Final Python network selection | `733b83dd3f2dcc801d4504ef46bbcbfc0f1ff08b9f1017cc63b38096202d6665` |
| Final ten-pass Node network selection | `98953cfe53460832d72f8aa755a62b7b8b97f20e0285524fff4b8167f9a890ce` |
| Separate Python metered-veto regression | `ea830cf4f72ecd6e1890bb4cceb1949953e92361d996eb1355d37bb968835d6e` |
| Separate Node metered-veto regression | `259d8b281b8607abd59be2d47c571347cd026cb9b2ae5459a3200fa07ad36972` |
| Final packaging selection | `d182bf19b41e25f765ba0d4e532586c3a9ced6cd0e49496579ddf85dac2d59fa` |
| Linux Python/Electron component receipt | `44ea00374873675461bff6d7cb8f22906637bef2bf53aa076d26d3752628a0f7` |
| Windows Python/Node component receipt | `dd4009e79899e7872617685eb4d9b5c05e84043fb177a1884ec4d28fa3d03ff0` |
| Linux x64 artifact, bound by its final receipt | `e5808426b41c18dc79ed1b1bdd595c3aac7ed74cd1913467426a2bca59385027` |
| Windows x64 artifact, bound by its final receipt | `e2e8a68ceb515ad92b59fb7d9761cb37dde32bd1095f3499f910e814baad3a73` |
| Final Electron source build | `d6c88c1616d194ec9efcfcb3452aba2a266884a087e8fff900fdafce023ecfc4` |
| Final Ruff check | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |
| Frontend build before final prose edits | `3d143b377b67b9b157d6a726e0aae952dbf326f49abe4851069aabf75f49a2e0` |
| Native fixture cleanup receipt | `fabeb850a580968f8c7c3124a3b0f1c7fa2699e131c28aa248ed59daefee82e5` |

## Remaining acceptance

macOS compilation/probes, all six installed native targets and complete
app/agent owner journeys remain open. Component
measurements do not qualify the **2 MiB added RSS / 0.5% CPU** resource contract,
whole-wire traffic, a production collector or ingress/log privacy. Earlier
[browser policy-refresh acceptance](2026-10-24-telemetry-company-refresh.md) keeps
its original component scope; it does not qualify this new native path. The
[full V08 contract](../implementation/anonymous-product-telemetry.md) and its
earlier resource failures remain unchanged. No production activation, completed
V08 or release notification follows from these component checks.

## macOS component follow-up

**25 October 2026, observed at 18:39:48 UTC.** The original local checkpoint
above correctly left macOS pending. Later
[CI run 40221952456](https://github.com/Perseusxrltd/mnemion/actions/runs/40221952456),
on source [`f35f1074a16c44bd029dd885bb80c342016c0376`](https://github.com/Perseusxrltd/mnemion/commit/f35f1074a16c44bd029dd885bb80c342016c0376),
compiled the helper and completed its Python/Node probes on both architectures.
The component steps and artifact uploads passed; the overall CI run and its
enclosing jobs were still in progress in that saved observation.

Both receipts report flags `9` (observed unmetered), Python **3.12.10** and
Node **22.23.2**, with no Electron runtime:

| Target | Component step completed (UTC) | Python elapsed | Node elapsed | Node added RSS |
| --- | --- | --- | --- | --- |
| [macOS ARM64](https://github.com/Perseusxrltd/mnemion/actions/runs/40221952456/job/121255287739) | 18:35:45 | 3.831 ms | 4.763 ms | **1,703,936 bytes** |
| [macOS x64](https://github.com/Perseusxrltd/mnemion/actions/runs/40221952456/job/121255287769) | 18:35:47 | 3.897 ms | 6.118 ms | **1,003,520 bytes** |

These are individual compiled-probe observations. They do not qualify Electron,
an installed client, the complete telemetry owner or all six native targets.
Python RSS was not measured. The smaller macOS probe results do not replace
the retained above-target Windows/Linux measurements; full-feature resource
acceptance remains unmet. Later producer-optimization work is outside these
receipts. Collection stays false, the destination and route stay null, and no
production collector, telemetry release or completion notification is established.

The original receipt hashes above are unchanged. Additional SHA-256 provenance:

| Evidence | SHA-256 |
| --- | --- |
| macOS ARM64 component receipt | `93afc1780f9bb974252f0676a41dc41da293010c85300e4d177b666587a8d186` |
| macOS ARM64 artifact, bound by its receipt | `fdcb1b77aba7d8ee70c775aa54c5c3922e2869dede54bd29397791ea5cccf4f2` |
| macOS x64 component receipt | `2eed1ecf6f24e7160f5aa151a673944832374ab76b3be8773f63f624456e9207` |
| macOS x64 artifact, bound by its receipt | `6a6d043fc323076325a0681df9d6d2cabdf3440f432872a36615e9597a926b8a` |
| Saved CI step/source observation | `b6c451faabc2d199d45bab8e839cf5db1c55f9c9442e3a71de372ab65928729d` |
