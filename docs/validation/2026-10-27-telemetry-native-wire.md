# Native telemetry network measurement — 27 October 2026

Seven native sender cases passed at source
`7bc322b2088080a5cc06ce69c99a6f21ee53f3a5`, using Electron **44.9.3** in Node
mode (**24.22.0**, Linux x64). This adds frame measurements to the existing
native TLS assertions. **Full V08 bandwidth acceptance remains open**; this is
a transport-component measurement, not an installed desktop or browser journey.

The [machine-readable result](2026-10-27-telemetry-native-wire.json) records all
seven cases, the two counters, runtime and qualification. All **2,111 source
inputs and 92 compiled inputs** matched after the run. The existing compiled
sender and private policy store were reused without rebuilding or changing them.
The six existing scenarios retain their functional assertions; a seventh sends
a larger response from the same disposable peer.

## Observed traffic

Only a new Linux user/network namespace's loopback interface was observed.
Its MTU was **1,280**; TSO, GSO and GRO were disabled and read back as off.
The existing AF_PACKET counter retained aggregate frame counts and lengths,
without raw packets, addresses, ports, request headers, bodies or certificates.
Its IPv4/TCP counts agreed with the independent interface counters in every
case. Kernel drops and unexpected traffic were zero; the largest observed frame
was **1,294 bytes**, including the loopback link's 14-byte header.

| Case | Result | Report body bytes | Charged TLS bytes | IPv4/TCP bytes | Frames including link headers |
| --- | --- | ---: | ---: | ---: | ---: |
| Direct native delivery | One delivery, no DNS or ambient credentials | 4 | 3,484 | 4,488 | 4,754 |
| Delivery owned by ordinary desktop recording | One delivery; a later recording respects cooldown | 4 | Not separately instrumented | 4,486 | 4,752 |
| Python opt-out during handshake | Suppressed before a report body | 0 | 1,434 | 2,022 | 2,176 |
| Python opt-out after the body | Suppressed; already transmitted bytes remain counted | 4 | 3,373 | 4,337 | 4,589 |
| Redirect response | Refused without another request | 4 | 3,501 | 4,505 | 4,771 |
| Oversized response headers | Refused | 4 | 7,552 | 8,764 | 9,086 |
| Peer queues a 256 KiB response-header burst | Refused with spending retained | 4 | 20,565 | 52,913 | 53,683 |

Every case used less than its **65,536-byte** reserved allowance. The larger
peer burst demonstrates why charged TLS bytes are not a whole-wire measurement:
the counter observed more traffic than the native sender processed. It does not
establish a universal bound for other peers, scheduling or network conditions.
No reservation was refunded and active leases cleared. The normal owner path
was exercised without a manual reservation or sender call; its internal return
value was not replaced or intercepted to invent a TLS-byte figure.

The seven tests passed without skips. Controller syntax passed before scenarios
started. Measurement took **3.299 seconds**. Temporary profiles, certificates and
the staged test controller were removed; the original controller and logs are
retained in private evidence. Production disclosure stayed byte-identical and
collection stayed disabled. There were no model calls or user-workspace changes.

## Scope and remaining evidence

The TLS peer and client share the test process and use a synthetic authority.
This is segmented IPv4 loopback evidence, not a physical connection, production
certificate chain or independently scheduled remote peer. It does not qualify
IPv6, loss/retransmission, Wi-Fi/cellular overhead, other native platforms,
browser transport, aggregate shared rolling-day behavior or installed updates.
The original [Python observations](2026-10-27-telemetry-loopback-wire.md) and its
[receive-window correction](2026-10-27-telemetry-receive-window.md) retain their
separate scope and unfavorable observations.

No new resource measurement or permission cache was selected. The failed
[resource result](2026-10-27-telemetry-metadata-allocation-results.md), unchanged
**2 MiB / 0.5%** limits, **256 KiB rolling-day** wire ceiling, provider privacy
and aggregate requirements remain in the
[acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md).
All [66 requirements](../PRODUCT_REQUIREMENTS.md) remain retained.

Qualification SHA-256:
`8f446e29c631b9650fd29d3b255d949211968240ea637fb40b95882e307824ae`.
Original measurement SHA-256:
`1c8e10cc83a5ab303ba3be521eae335ec1d2fbb9ab9033850d3282150ad4b9b1`.
No new native release is requested for this documentation batch. The existing
4.46.36 hotfix pipeline remains separately owned. V08 remains **Building**, with
collection/destination/route **false/null/null** and release CAs empty.
