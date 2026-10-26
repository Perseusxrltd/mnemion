# Headless Windows network admission — 26 October 2026

The compiler-free Windows cost reader passed focused source and Windows x64
component checks. This later source is excluded from published 4.46.13. V08
remains **Building**, all 66 requirement states are unchanged, and production
collection/destination/route remain **false/null/null**.

[network_system.py](../../mnemion/product_telemetry/network_system.py) reads
[`GetNetworkConnectivityHint`](https://learn.microsoft.com/en-us/windows/win32/api/netioapi/nf-netioapi-getnetworkconnectivityhint)
through the System32 library. It uses no COM, interface enumeration, network
request or idle task. The [existing admission reader](../../mnemion/product_telemetry/network.py)
selects this path only when `network-state.node` is absent. A present broken or
unreadable helper is never bypassed. Unavailable APIs remain unknown; Linux and
macOS source installs without the helper also remain unknown.

Unknown cost already allowed an explicit unmetered declaration after a completed
valid probe that reported no constraint. Automatic mode still refuses unknown
cost, and metered/offline/constrained readings, pressure, policy and lifetime
checks still veto delivery. This adds a Windows observation capability; it does
not repair a previously broken manual choice or change delivery allowance.

## Retained component evidence

- **82 focused Python tests passed in 5.61 seconds.**
- Actual Windows x64 **Python 3.13.11** direct flags **9** matched stable C-helper
  readings before and after the call; the direct call took **0.0001408 seconds**.
  **Node 25.2.1** also returned flags **9**. This was not an Electron or installed
  app journey, a full network-transition matrix or a resource qualification.
- The existing native helper was reused unchanged, SHA-256
  `2860bf0b39401e8af4f6d70acb440acd07c7a401db12d384f52813ca1075aee3`.
  No app or network configuration was changed.

The first component fixture omitted `disclosure.json`, which the real package
initializer requires. Its failure and the correction receipt remain preserved;
this was a fixture omission, not evidence of a product-code failure.

| Original evidence | SHA-256 |
| --- | --- |
| Focused Python log | `bfdf50c4aa8d17ce96f6cfeee37a024fc4d9f317eb7a1eb4f89343c87db934e3` |
| Windows component receipt | `81232be7a4dde26a7875a6c75d716e68ad7a88353c672d87ee68403e4cd8674e` |
| Original fixture failure | `843b656d200b35bbf811b5865d0d678151ac1de32174cdc384e5e8277cd2afc3` |
| Fixture correction | `b2c1ba259bf06a90727a460ddb3bbf658f8dbba3327ecc3a39717b3ab1196eed` |

The unchanged **2 MiB / 0.5%** resource gates, Windows ARM64 component coverage,
all-platform installed delivery, whole-wire accounting and production ingress
privacy remain open. No full-CI pass is claimed from these component results.
See the [controls guide](../guides/product-telemetry-controls.md) and
[delivery budget](../implementation/anonymous-product-telemetry-budget.md).
