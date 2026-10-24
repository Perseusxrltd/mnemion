# Telemetry TLS transport: source checkpoint

**24 October 2026; unreleased source, V08 Building.** The new
[Python transport](../../mnemion/product_telemetry/transport.py) implements a
bounded TLS attempt for an already reserved report. Final source checks and
isolated browser/TLS journeys passed. It is not wired to application owners,
no collector endpoint is selected, and disclosure remains
`collection_available: false`, `destination: null`. These results qualify the
components exercised below, not production collection or released telemetry.

## Source boundaries

| Boundary | Implemented source behavior |
| --- | --- |
| Destination | A release-owned literal IP; the certificate hostname and port must match the disclosed HTTPS collector at `/v1/report`. No DNS lookup, proxy, workspace destination or credentials. |
| Connection | Certificate verification, minimum TLS 1.3 and one HTTP/1.1 request. No redirect, retry, scheduler or shutdown flush. |
| Accounting | At most **32,768 charged encrypted TLS bytes**, combining attempted outgoing bytes and received bytes. Partial/uncertain writes remain charged. This excludes TCP/IP overhead and does not qualify the separate 65,536-byte reservation as a whole-wire upper bound. |
| Lifetime | The reservation's existing **five-second** wall-clock/monotonic validity covers setup, handshake, handoff and response; it is not restarted by the transport. |
| Handoff and response | One synchronous nonblocking application write under the privacy fence; **2,048-byte response-header cap**, with an empty HTTP 204 response required for `delivered`. This result describes the transport component only. |
| Cancellation | The active watcher can close the socket and cancel pending I/O. Completion/cancellation erases the report and attempts lease cleanup without refund. No TLS close notification or application flush is added after cancellation. |

The [budget components](../implementation/anonymous-product-telemetry-budget.md)
now retain native/Python leases after successful handoff, matching the browser.
Python, Electron and browser report handles claim the application handoff once;
a competing handoff does not write twice or cancel the winner. Python's
`PreparedReport.claim_transport()` separately claims the entire attempt before
connection setup or cleanup ownership. Duplicate `send()` calls return without
connecting or cancelling the winner, including while its response is pending.
The final checks below cover these changes; earlier budget/browser receipts
remain evidence for their preceding source versions.

## Final component evidence

| Check | Observed result |
| --- | --- |
| Final Python selection | **69 passed in 17.35 seconds**, including [11 TLS cases](../../tests/test_product_telemetry_transport.py) covering concurrent senders and a duplicate call while the response is held. |
| Final actual Electron selection | **21 passed, two Windows-only ACL skips**, 23 total, in 9.612 seconds; Electron **44.9.3**, Node **24.22.0**, Linux x64. Includes [native delivery](../../studio/electron/scripts/test-telemetry-delivery.mjs) and store checks, not installed-package acceptance. |
| Browser source selection | **45 passed**, zero failures or skips, in 2.296 seconds. This does not establish a browser TLS sender. |
| Actual Chromium journey | **21 checks passed**, Chromium **144.0.7559.96**, completed at **07:25:56 UTC**. Exactly one loopback report request across the isolated journeys. |
| Actual TLS/collector journey | **14 checks passed** at **07:29:40 UTC**; Python **3.12.3**, OpenSSL **3.0.13**. Two competing callers produced one report and **2,055 charged TLS bytes**. |

The fresh browser journey exercised competing guarded handoffs, preservation of
the winner's live lease, cross-tab opt-out during the active fetch, and
quota/crash recovery with spending retained. The server received the original
four body bytes before cancellation; opt-out cannot recall those bytes. Only
the isolated fixture enabled disclosure in memory. No production memory/model
calls or non-fixture context requests occurred. Cleanup at **07:30:52 UTC**
verified all three isolated contexts, the browser session and loopback server
closed. This was trusted loopback HTTP, not a browser TLS transport test.

The TLS journey used the actual Python sender and
[Collector](../../mnemion/product_telemetry/collector.py) under Uvicorn with a
**loopback address and test CA**. The collector accepted exactly one contribution
and produced no publishable small-cohort output. Completion erased the report
and lease while retaining spending; shutdown erased the collector's aggregate
window. The temporary client store/certificate profile was removed and the
server log was empty. No production memory/model calls occurred. The measured
2,055 bytes are this fixture's charged TLS traffic, not TCP/IP wire usage or a
qualified worst-case transport bound. Public trust, ingress and provider logging
were not exercised.

## Preserved failures and earlier checks

The initial Python selection had **one failure and 66 passes in 18.43 seconds**:
the response parser used a `bytearray` header name as a set key. Converting the
header block to immutable bytes corrected that failure. The next selection
passed **67 tests in 16.72 seconds**, including nine TLS cases, before the
whole-attempt ownership correction. The intermediate Electron selection passed
**21 tests with two Windows-only skips in 9.978 seconds**; the native source
build also passed at that earlier checkpoint. All original evidence is retained.

The earlier main container build for source `4371d2f` failed at **06:54 UTC**
because its frontend stage could not resolve `telemetry-wire` and `wire-v1.json`. The corrected
[Dockerfile](../../deploy/Dockerfile) and [.dockerignore](../../.dockerignore)
include those required inputs. The failed log remains preserved; a passing
replacement container build/CI result is not claimed here.

Canonical owner wiring, endpoint selection, actual network/pressure sensors,
TCP/IP wire accounting, resource limits, ingress metadata/log privacy and
all-platform release acceptance remain open. This source checkpoint does not
activate production collection or complete V08. All 66 requirement states and
the existing privacy, utility and resource requirements are unchanged.

| Original evidence | SHA-256 |
| --- | --- |
| Final Python selection | `2067e7b102aa946b82b43bf4bfdbf198ca982961290d011d722ef79615545b6d` |
| Final actual Electron selection | `d0ca018093b07d1b9c5beacb52bc64041933e829a1d2b6a9574fef9786ccb5ba` |
| Electron runtime identity | `d54a1d2833648a69a402f76cdd73f49d9aef2c900dcf99ff93b6dbb0a89dd10b` |
| Browser source selection | `9c00e3a282c66831e69c5d265e17116b5183ab6e6d05751ac9b706e5c1e3beb9` |
| Actual Chromium journey receipt | `973577ae21f5eb4cf2e4355886ca378ac9e8b7279cb7bfa2b8e4d70c9fd6956a` |
| Browser fixture source manifest | `8f3897a97926a55b7ea3ff58c5d3e633b7dfc3bc6771094bb84765c067f54dbe` |
| Browser cleanup receipt | `7664dd2aec8435d3a2166570b9d8e4d7e7601d20428070d472a99422af095b9f` |
| Actual TLS/collector journey receipt | `3ec8f4eaee633aa3e2b3d31cccac519a9cdb2cfe1bf7cf60a5dfff21d4041979` |
| TLS/collector fixture script | `106fa480b020961ac17b4676fbce1fbd6a84adb483cef8d5d089ec80b756d5bc` |
| Empty TLS server log | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| Initial Python parser failure | `ab6dc8a219b05ed0de9510c2cb929d79774ee73b3c0dcbd283002ad7eaf2056c` |
| Python parser-correction selection | `3d041f68792f7b79b6ca00656eb90a07ac713c8e33a52f22d263195abbeeed74` |
| Intermediate Electron selection | `8b1f03c1ef81c0db644a5b65651834b70b6ad7f75d8edf4bcc4ccbe03c3f9202` |
| Intermediate native source build | `873b841c25f2b8da83857d248087de185ea22e1986b5fb6eb43f96e70e00896b` |
| Original main container failure | `750310c08f310f822a7b92966dacd7516d0980c7b31195d324beab3cd9198344` |
