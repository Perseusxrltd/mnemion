# Telemetry loopback network measurement — 27 October 2026

Five Python TLS transport cases completed against source
`1b57752f79b4d232a5c5eca1995f1d3f07d50090` in a dedicated Linux user/network
namespace. Only that namespace's loopback interface was observed. The
[machine-readable receipt](2026-10-27-telemetry-loopback-wire.json) binds the
source inputs, runtime, independent counters, original observation and cleanup.
This is component evidence; **full V08 bandwidth acceptance remains open**.

The counter retained aggregate frame counts and lengths. It copied only a fixed
packet prefix and retained no raw packets, addresses, ports, request headers,
bodies or certificates. The client and TLS peer used existing disposable
fixtures; production disclosure, the user application and workspaces were
untouched. This measured no model calls.

## Segmented observations

The namespace had MTU **1,280**. TSO, GSO and GRO were explicitly disabled and
read back as off on its own loopback interface. Every observed frame was at most
**1,294 bytes**, including the loopback link's 14-byte header. AF_PACKET counts
and the namespace's independent interface counters agreed for every case;
kernel packet drops and unexpected traffic were zero.

| Case | Result | Body bytes | Charged TLS bytes | IPv4/TCP bytes | Frames including link headers |
| --- | --- | ---: | ---: | ---: | ---: |
| Normal delivery | Delivered once | 4 | 1,311 | 2,159 | 2,383 |
| Redirect | Refused; no redirect request | 4 | 1,330 | 2,178 | 2,402 |
| Oversized response headers | Refused | 4 | 5,381 | 6,437 | 6,717 |
| Opt-out after the body | Suppressed; prior bytes remain counted | 4 | 1,201 | 1,893 | 2,075 |
| Opt-out during the handshake | Suppressed before a report body | 0 | 254 | 686 | 798 |

Each case retained its spent reservation and cleared the active lease. The
whole fixture directory was removed and the production disclosure remained
unchanged. The five-case measurement completed in **1.53 seconds**. Every
observed case used less than its **65,536-byte** attempt reservation; this is
an observation of these fixtures, not a universal wire-cost bound.

## Original observations and limits

The first five cases completed with zero packet drops, but loopback coalescing
produced one **4,222-byte** frame despite the configured MTU. That receipt is
retained rather than used as segmented packet evidence. The follow-up disabled
coalescing and required every frame to fit the MTU. Source inputs and scenarios
were unchanged; certificate generation can change TLS lengths slightly, so the
two runs are not a causal savings comparison.

The initial diagnostic setup failures are also retained: source lint findings
and a user-namespace denial when reading PID 1's namespace identity occurred
before traffic collection. The corrected launcher obtains its own namespace
identity before entering the new namespace. The final source review passed.

These are IPv4 loopback observations with a synthetic TLS authority, not a
production certificate chain or physical network. They do not measure Ethernet
preamble/FCS/inter-frame gaps, Wi-Fi/cellular overhead, IPv6, packet loss or
retransmission. Native Electron and browser transports, other operating systems,
shared rolling-day behavior, actual provider logging/privacy and final installed
journeys remain unqualified. The **256 KiB rolling-day**, **2 MiB added RSS** and
**0.5% of one core** requirements remain unchanged.

The private `2026-10-27-telemetry-loopback-wire` evidence set retains the script,
both observations, setup errors and qualification. The segmented receipt has
SHA-256 `b8385c48360f816f73db350e4e6d11b97de94b88bf3477981e9c472331b122d0`.
V08 remains Building with collection/destination/route **false/null/null** and
release CAs empty. See the [acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md)
for the full remaining scope.
