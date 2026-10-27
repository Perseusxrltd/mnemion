# Python telemetry receive window — 27 October 2026

A synthetic TLS response burst exposed bytes received by the kernel beyond
those charged by the Python TLS reader. The original failure remains retained;
the corrected Linux component observation fits the unchanged **65,536-byte
attempt reservation**. This does not qualify total wire cost on all networks.

The [machine-readable evidence](2026-10-27-telemetry-receive-window.json) binds
the original source `e18b495cdf554f682a4a2be0f1f2498e9d934fc4`, corrected base
`b42a309fcffbf791197ae35b11604e98fb5d2882` **plus the transport patch**, exact
source hashes and original receipts. Both observations used the same diagnostic
script and a peer sending headers with **262,144 synthetic noise bytes** in
one burst; synthetic certificates vary between fixtures.

| Observed quantity | Original | Corrected |
| --- | ---: | ---: |
| TLS bytes charged | 21,683 | 18,394 |
| IPv4/TCP bytes | 121,471 | 22,634 |
| Captured frame bytes | **123,053** | **23,110** |
| TCP frames | 113 | 34 |
| Requests / report body bytes | 1 / 4 | 1 / 4 |
| Frame total within attempt reservation | No | Yes |

The isolated loopback interface had MTU **1,280** with TSO/GSO/GRO disabled.
Packet-derived IPv4/TCP totals agreed with independent interface counters;
frame totals include the 14-byte captured link header. Loopback receive and
transmit counters are not added together. Both observations had zero capture
drops or unexpected frames, and maximum frame size **1,294 bytes**. Only
aggregate counts were retained, without raw packets or request metadata.

The [Python transport](../../mnemion/product_telemetry/transport.py) now requests
`SO_RCVBUF=4096` before connecting and requires a positive readback of at most
**8,192 bytes**. A setting/readback error or out-of-range value refuses the
connection. The existing TLS trust, consent, deadlines and spending rules remain
unchanged; a bounded receive window does not bound retransmissions.

**32 transport tests passed**, including four new pre-connect refusal cases for
setting failure, readback failure, oversized readback and zero readback. Both
burst observations refused the malformed response: `outcome=failed` is not a
successful delivery. Each retained the spent attempt, cleared its lease and
removed the temporary fixture. Production disclosure was unchanged.

The [earlier five-case loopback observations](2026-10-27-telemetry-loopback-wire.md)
remain separate and were not repeated. Their smaller measured totals did not
establish a universal wire bound; the retained burst failure demonstrates that
limit. This correction qualifies only the Linux IPv4/Python burst component.
Physical-link overhead, retransmissions, IPv6, Windows, macOS, Electron, browser,
rolling-day accounting and installed delivery remain unqualified. No resource
or collector-privacy acceptance follows, and the **2 MiB / 0.5%** limits are
unchanged. All 66 requirements remain intact; V08 is **Building**, with
collection/destination/route **false/null/null** and release CAs empty.
