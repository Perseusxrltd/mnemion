# Telemetry native and browser transports: source checkpoint

**24 October 2026; unreleased source, V08 Building.** The
[native](../../studio/electron/telemetry-transport.ts) and
[browser](../../studio/frontend/src/workspace/telemetry-transport.ts) senders now
exist in source. The final Electron selection passed **32 checks with two
Windows-only skips**; **65 browser source checks** passed. Actual loopback
TLS/collector journeys passed **22 browser checks and 18 native checks**.
No application owner is wired,
no production endpoint is selected, and disclosure remains
`collection_available: false`, `destination: null`.

This follows the separately recorded
[Python TLS component](2026-10-24-telemetry-transport.md). Earlier source and
loopback receipts do not qualify these new senders. The
[delivery design](../implementation/anonymous-product-telemetry-delivery.md#native-and-browser-transport-follow-up)
and [shared budget](../implementation/anonymous-product-telemetry-budget.md)
retain the full contract and reservation limits.

## Implemented boundaries

Both report handles claim the complete transport attempt before connection setup
or cleanup ownership. A duplicate returns without starting another connection or
cancelling the winner. They use the original report's remaining five-second
lifetime, retain its lease during active work, and attempt report/lease cleanup
without refund on completion or cancellation. No scheduler, application-level
retry or shutdown flush is added.

| Boundary | Native source | Browser source |
| --- | --- | --- |
| Connection | Literal release-owned address, verified certificate hostname/port, minimum TLS 1.3 and HTTP/1.1. No DNS, proxy or ambient credentials. | Disclosed HTTPS `/v1/report` URL; Fetch owns connection setup. DNS, proxy use, TLS and connection reuse are browser-controlled. |
| Request and final fence | Four-byte body with fixed headers, encrypted before one nonblocking raw-socket write under the SQLite privacy fence. | Four copied bytes passed to Fetch under the Web Lock fence, with credentials omitted, no referrer, cache disabled, redirects refused and keepalive disabled. |
| Accounting and response | At most 32,768 charged TLS stream bytes, combining outgoing attempts and received bytes; 2,048 response-header bytes and an exact empty HTTP 204 response. | No exposed TLS/TCP/IP accounting or response-header cap. Success requires API-observed 204, the exact destination, no redirect and `Content-Length: 0` before the active deadline. The body is never read; a null stream is not required. |
| Active cancellation | Close the socket, erase owned buffers and stop the watcher. | Abort Fetch and discard its response; no response content is read. |

Native charged bytes exclude TCP/IP retransmissions and lower-layer overhead.
Browser-generated headers and cross-origin preflight are additional traffic;
the collector's fixed `POST`/`OPTIONS` CORS response does not establish public
ingress privacy. Neither path qualifies the **65,536-byte reservation** as an
actual whole-wire upper bound. Bytes handed off before opt-out cannot be recalled.

Browser lifecycle/cancellation listeners are installed **before Fetch**. An
optional handoff promise delays only policy lock polling until the guarded
handoff releases its Web Lock. The deadline and owner abort are already armed;
pagehide and choice changes can cancel during the handoff. The redundant
post-response policy lock was removed to avoid another self-contending read.

## Current evidence

| Original check | Result and scope |
| --- | --- |
| Final native selection | **32 passed, two Windows-only ACL skips**, 34 total, in **11.442 seconds**, under Electron **44.9.3 / Node 24.22.0 / Linux x64**. Includes 11 [native transport checks](../../studio/electron/scripts/test-telemetry-transport.mjs) with isolated TLS peers, a temporary test CA and private synthetic stores. |
| Final browser source selection | **65 passed**, zero failures or skips, in **6.648 seconds**; includes [sender and asynchronous-lock regressions](../../studio/frontend/scripts/test-telemetry-delivery.mjs). Actual browser evidence is recorded separately below. |
| Initial native build | Failed type checking because `highWaterMark` was not declared in the installed `SocketConstructorOpts` type. This original failure is preserved. |
| Final native build | Passed after the final source changes. This is source-build evidence, not installed-package or all-platform acceptance. |
| Final frontend type checks | Passed after the browser corrections; the initial callback-narrowing error is retained. No frontend production-build result is inferred from this check. |
| Actual Chromium/TLS journey | **22 checks passed at 08:16:15 UTC**, Chromium **144.0.7559.96**. Exactly two new reports and two real CORS preflights reached the actual TLS Collector; both reports were accepted. |
| Actual native/TLS Collector journey | **18 checks passed at 08:18:38 UTC**, Electron **44.9.3 / Node 24.22.0 / Linux x64**. Two competing sends produced one accepted report with **2,649 charged TLS bytes**. |

The [CI](../../.github/workflows/ci.yml) and
[native workflow](../../.github/workflows/desktop.yml) now invoke npm tests through
the existing locked uv environment for the cryptography fixtures. This is source
configuration; no new CI or native-release pass is claimed here.

The native checks exercise one fixed request with DNS refused; concurrent and
response-pending duplicates; Python opt-out during handshake and response waits;
owner cancellation without refund; rejection of redirects, oversized headers,
certificate-name mismatch and an oversized TLS handshake; the five-second
deadline; and refusal of an undisclosed/nonliteral destination. They use the
real native sender with controlled peers, not a production collector or an
installed application owner. Test cleanup verifies report erasure and the absence
of a live lease while retaining the spent attempt.

The final Chromium journey used **no request interception**. It exercised
pre-send opt-out without POST or preflight, competing senders, a duplicate while
the response was pending, and cross-tab opt-out during an actual TLS request.
Observed requests omitted the seeded cookie, authorization and referrer.
Browser Origin and User-Agent remained visible ingress metadata; this does not
qualify a public ingress's retention or logs. Three earlier diagnostic reports
remain preserved separately from the two new accepted reports. No production
memory/model calls or non-fixture context requests occurred.

The native journey verified the original four-byte report, four fixed headers,
no preflight or credentials, report/lease erasure and one spent reservation.
Its 2,649-byte observation measures charged TLS traffic for this fixture, not
TCP/IP wire usage or a worst-case upper bound. The temporary native profile was
removed. Both journeys used isolated loopback TLS with temporary certificate
trust; browser certificate errors were accepted only within the isolated test
contexts. **Public certificate trust was not qualified.**

Cleanup at **08:19:44 UTC** verified the journey contexts, owned browser, local
UI and TLS server closed and the temporary certificate profile removed.
The collector published **zero aggregates**. Repository disclosure stayed disabled;
the private fixtures restored their temporary process overrides. Neither journey
activated production collection.

## Preserved failures and corrections

The earlier native transport selection passed **11 checks with zero skips in
9.115 seconds**. The final native source also refuses a stopped handshake before
connecting or constructing its TLS socket, and erases the temporary body on an
early capture return. The final 32-pass selection covers that later source;
the initial 11-pass receipt remains historical. Browser type checking was
corrected by separating the timeout flag from the result variable narrowed
outside its callback. These changes do not wire production owners or select an
endpoint.

- The first Chromium journey failed before any network; its **08:08:34 UTC**
  statistics show zero POST/OPTIONS requests. The watcher and guarded handoff
  competed for an asynchronously released `ifAvailable` Web Lock. A focused
  regression using realistic asynchronous release reproduced the rejection.
- Moving the entire watcher after handoff exposed a pagehide gap: the next
  browser selection had **62 passes and one failure**. The final design arms
  listeners first and delays only lock polling; the final 65-pass run covers it.
  The preceding 62-pass source result remains historical.
- Chromium exposed a non-null response stream for a legitimate empty HTTP 204.
  The original response diagnosis is retained; the sender now requires the fixed
  `Content-Length: 0` header and never reads the stream. Earlier intercepted
  browser diagnostics skipped real preflight; the final journey without interception
  verifies two real CORS preflights instead.
- The first native collector fixture exited with an unsettled top-level await:
  the unreferenced transport correctly did not keep a one-shot process alive.
  The corrected private fixture used a bounded `MessageChannel` to represent an
  already awake owner, with no idle polling or product change for that correction.
  Its original failure and stderr remain preserved.

| Original evidence | SHA-256 |
| --- | --- |
| Final native selection | `95cd3b7fef9f449299871ece40e5dc0d7a2ef5b9a78bc6df1efd89b090a0ea17` |
| Actual Electron runtime identity | `d54a1d2833648a69a402f76cdd73f49d9aef2c900dcf99ff93b6dbb0a89dd10b` |
| Final browser source selection | `4f22adc1acb59a24fd2ab9099979bfb96d8618ad7c0a8c58502104ca917d1820` |
| Actual Chromium journey receipt | `1e403d47f6ccdb20f1bc9205f506b677276bf28a0fd8f9a3263e89c0e8850540` |
| Browser fixture source manifest | `4137551c75fd120bdf739dc7b01aa23e6f4fdd567bad7cc069164558103a1430` |
| Browser/server cleanup receipt | `77e99afd37177e03a11a2b37356bd71f5429c5cc7add58c74c40ab649f0567c4` |
| Actual native collector journey receipt | `2f932b0a8cb2a8d4112af731df052eee8c0a925c756867e4f9ef8f316c697a3d` |
| Earlier 62-pass browser selection | `8bb939f10e7431b5d6208872d4446cbed377ebd76e5249b2c82658fe1efed1e4` |
| Original Chromium failure | `6c7936cb8c59b8dfd14d02d702716ebea315a1cd6bc515d14e254bd1a640e369` |
| Original zero-network failure statistics | `b45f6cc5839220bba1b82740d7853e77f3b4d420bf3a6f30b54aa464fa594359` |
| Web Lock diagnosis | `120086b7aea3429f7b17924aabf5f01207f41fc1edd1d8f24c0be8b02ae04b7a` |
| Reproduced asynchronous-lock regression | `4aa341b8f4c66201b8664d9ebd9067013c14b75e37411ff0017a3d7d1e8ea3ad` |
| Pagehide regression failure | `0c3fe1f8f4df2d06a655bd26ed24958128adfd90f1252ccff4bcd3a761fedb37` |
| Original empty-response diagnosis | `9e7519ef8b4546bf213c18e6301c6094559e3c0d1ad8f67a39c5b0786782cc1b` |
| Original native collector fixture failure | `b8a205e80ae7242e9946f1bc1aaab99c8ce6118b254e7264ccff8a29afa54e2c` |
| Original native fixture stderr | `27811c8a2024d789b72d692169d724d632360e08a9a51770975d45db1aa65e69` |
| Earlier native transport selection | `5e37e2829e177ced0d803b670a4263c1fb92a20880cc88859987a471004afc9f` |
| Original native type-check failure | `50554b92a7c386ccb58e3612c3a957cd777b861a7d228fd5ab521334f7d1a790` |
| Corrected and final native build logs (identical bytes) | `873b841c25f2b8da83857d248087de185ea22e1986b5fb6eb43f96e70e00896b` |
| Original frontend type-check failure | `0f4103bf52af3c27ca8d5a6caa88ece3f8831d0d9f4182a1c4a1bab8d10c31c4` |
| Corrected/final frontend type-check logs (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

Application-owner integration, network/pressure sensors, complete wire and
resource measurements, public-ingress metadata/log privacy, deployed retention
and all-six-native plus web release acceptance remain open. The unchanged
**2 MiB added-RSS / 0.5% of one core** limits are not qualified by these checks.
No production telemetry is activated, and none of the 66 requirement states is
changed by this component checkpoint.
