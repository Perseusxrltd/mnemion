# Product telemetry delivery components — V08

**Unreleased source checkpoint, 26 October 2026; V08 remains Building.** The
[full contract](anonymous-product-telemetry.md) and
[local catalog/ownership](anonymous-product-telemetry-catalog.md) retain their
scope. Python/TypeScript packet encoders, a volatile weekly accumulator, an
ASGI ingress adapter and a private closed-week publisher now exist in source.
The later [native/Python budget components](anonymous-product-telemetry-budget.md)
add shared private reservations and cancellation fences; their focused source
checks passed, without qualifying installed delivery or transport costs.
The subsequent [Python TLS transport](../validation/2026-10-24-telemetry-transport.md)
has passing source and isolated loopback component checks. The later
[native and browser senders](../validation/2026-10-24-telemetry-client-transports.md)
are source components; **32 Electron checks passed with two Windows-only skips**,
and **65 browser source checks passed**. Actual loopback TLS/collector journeys
passed **22 browser checks and 18 native checks**. **Production collection
remains disabled; installed production delivery and ingress qualification remain
open.** The disclosure remains `collection_available: false` with
`destination: null`. Source and synthetic utility evidence is recorded in the
[delivery validation](../validation/2026-10-24-telemetry-delivery.md).

The later [application-owner source batch](../validation/2026-10-24-telemetry-app-owners.md)
wires these senders to already awake desktop/browser work and an existing Python
service or maintained local stdio loop, with persistent connection controls and
active environment checks. Source checks and the actual Chromium owner fixture
passed; the fixture used synthetic CPU admission, so actual sensor qualification
remains open. The release-owned route address remains
null; these earlier transport passes do not qualify the new owner paths.

## One randomized category per report

The [version 1 format](../../mnemion/product_telemetry/wire-v1.json) defines
**23 views, 280 category values and 400 padded Hadamard coordinates**. The views
cover feature family/operation, invocation surface, outcome/reason, fixed metric
buckets and separate coarse platform, architecture and release-family cohorts.
They do not form a joined device profile.

The [Python](../../mnemion/product_telemetry/wire.py) and
[TypeScript](../../studio/electron/telemetry-wire.ts) encoders:

1. Select one view using fixed weights among permitted metric groups, independently
   of measurement values. They do not send all 23 views together.
2. Sample one category using the already bounded local cell counts. Missing
   sensors use `unobserved`, not a fabricated zero. Only reviewed cohort enums
   are accepted.
3. Choose a random Hadamard coordinate, retain its true sign with probability
   **3/4**, and flip it with probability **1/4**.

The result is exactly **four body bytes**:

| Byte | Meaning |
| --- | --- |
| 0 | Format version, currently `1` |
| 1 | Chosen view index |
| 2 | Random coordinate within that view's padded domain |
| 3 | Randomized positive-sign flag, `0` or `1` |

The source app, native CLI and browser controls now expose the fixed synthetic
bytes `01 00 07 00` as Base64 **`AQAHAA==`** under `illustrative_packet`, labeled
`kind: "synthetic_example"` and `body_encoding: "base64"`. The shared Python
`format_example` and TypeScript `formatExample` helpers describe `feature_family`,
coordinate `7`, sign `-1` and four body bytes. They do not recover a true category,
read a queue, draw new randomness or reserve an attempt. The wire remains v1.

The actual-body fields stay `outbound_body: null`, `outbound_bytes: 0` and
`outbound_state: "not_inspected"`. This is a report-format example, not an
inspection of a queued or sent packet. It neither spends delivery allowance nor
acknowledges disclosure or sends a request. Local aggregate inspection remains a
separately labeled snapshot; the app clears it on choice changes, status refresh
or window focus and rejects late preview responses. The
[exact-packet acceptance requirement](anonymous-product-telemetry.md#proposed-outbound-schema-and-payload-preview)
remains open. The original source checkpoint left installed checks pending;
later [five-target qualification](../validation/2026-10-26-telemetry-preview.md#five-installed-native-targets-qualified)
verified Linux and Windows x64/ARM64 plus macOS ARM64 against **64 required true
fields each**, including the format preview, app/native choice parity and opt-out
persistence across restart. Windows ARM64 used x64 engine/database components
under emulation. The overall 4.46.12 run failed on Intel Mac, whose installed
journey was skipped; the candidate remains unpublished. These control checks
do not qualify installed production delivery. Earlier codec and sender receipts
retain their original scope. HTTP headers, framing, TLS and other transport
traffic are additional bytes and remain unqualified.

`prepare` accepts only bounded `(cell, count)` pairs and reviewed cohort enums.
It does **not** itself read policy or enforce an attempt budget. The later
[budget wrapper](anonymous-product-telemetry-budget.md) supplies the shared
policy/queue reservation in source; every transport must use that boundary for
its attempt. Current `schema` exposes `transport_catalog` and
`transport_available`, meaning valid configured release-route capability,
separate from consent, an active attempt or delivery success. It remains false
with the production false/null/null gates.

Python status and sending share the pure
[endpoint validator](../../mnemion/product_telemetry/endpoint.py); its bounded
release-route read is cached because that file is an immutable package input,
not a user consent setting. Browser status and sending share the same
[HTTPS destination validator](../../studio/frontend/src/workspace/telemetry-capability.ts).
These checks perform no DNS or network request. Discovering capability does not
reserve, activate or authorize sending, and does not replace fresh policy and
environment checks on an actual attempt.

## What the privacy bound covers

For a fixed permitted view and coordinate, a randomized sign has probability
`3/4` or `1/4` under any possible category. The maximum likelihood ratio is
therefore `3`, giving **per-report local differential privacy ε = ln(3)** for
the sampled categorical value, conditional on that permitted view.

This is **not** participation, policy-choice, lifetime or network anonymity.
The chosen view is visible, permission groups affect view selection, and repeated
reports compose privacy loss. The packet contains no category label, local count,
stable identifier, generation token, credential or event timestamp, but absence
of these fields alone does not establish anonymity. Confidence and utility also
assume independent randomization by conforming senders; the source provides no
authenticated-contributor or poisoning-resistance guarantee.

At the codec-only checkpoint, the JSON's budget entries were proposals. The later
native/Python source wrapper implements reservation accounting as follows. Its
preceding source checks passed before the later application-owner source wiring;
installed production delivery remains unqualified:

| Bound | Current source status |
| --- | --- |
| At least 86,400 seconds between attempts | Shared cooldown adds zero through one hour of random jitter; no scheduler exists. |
| At most seven attempts per rolling week | Private SQLite accounting survives opt-out; every reservation remains spent without a refund. |
| Conditional weekly bound `7 × ln(3)` | Requires every actual report to use the allowance; no installed sender proves this and it is not a lifetime/person guarantee. |
| Reserve 65,536 wire bytes per attempt | Fixed accounting plus a 256 KiB rolling-day guard. The newer Python component caps charged TLS bytes separately; whole-wire cost remains unqualified. |

Existing local cell/contribution limits clear on explicit choice; the separate
delivery attempt ledger and cooldown do not. The contract's opt-out fencing, final-send
cancellation and resource/bandwidth ceilings remain unchanged.

## Python TLS transport follow-up

The [new transport checkpoint](../validation/2026-10-24-telemetry-transport.md)
describes a Python TLS attempt to a literal IP whose verified hostname and port
match the disclosed collector. It has no DNS, proxy, credentials, redirect or
retry; it caps combined charged TLS bytes at **32,768**, response headers at
**2,048 bytes**, and uses the reservation's existing five-second lifetime.
Successful handoffs remain cancellable until completion. A private whole-attempt
claim precedes connection setup and cleanup ownership, so duplicate senders do
not connect or cancel the winner. Final source checks and a **14-check actual
TLS/collector journey** cover this path, using loopback and a test CA. Earlier
codec, budget and browser receipts retain their original scope. At that checkpoint
no application owner was wired. The later owner source now has its own scoped checks;
no endpoint is selected, and TCP/IP overhead, sensors, resources, ingress and
all-platform acceptance remain open.

## Native and browser transport follow-up

The [native sender](../../studio/electron/telemetry-transport.ts) uses a raw socket
under TLS, rather than Electron session networking. The
[browser sender](../../studio/frontend/src/workspace/telemetry-transport.ts) uses
Fetch. Both claim the report's whole attempt before setup or cleanup ownership,
keep its original five-second lifetime and cancel the lease on completion without
refund. Those component checks preceded application-owner wiring. The current
source offers attempts only from already active work; it adds no idle scheduler.

| Boundary | Native source | Browser source |
| --- | --- | --- |
| Destination and connection | Release-owned literal IP; certificate verification, minimum TLS 1.3 and disclosed hostname/port. No DNS or proxy. | Exact disclosed HTTPS URL at `/v1/report`, without credentials, query or fragment. The browser manages DNS, proxies, TLS and connection reuse. |
| Request | Four bytes and fixed HTTP/1.1 headers; one nonblocking raw-socket handoff under the SQLite privacy fence. | Four copied bytes passed to Fetch under the Web Lock fence; credentials omitted, no referrer, cache disabled, redirects refused and keepalive disabled. |
| Transport bounds | 32,768 combined charged TLS stream bytes and a 2,048-byte response-header cap; neither includes TCP/IP overhead. | Fetch exposes neither an enforceable TLS/TCP/IP byte cap nor a response-header cap. The fixed reservation is not a measured whole-wire bound. |
| Success observation | Exact empty HTTP 204 parsed from the bounded response. | Fetch exposes status 204, the exact destination, no redirect and `Content-Length: 0` before the active deadline. The body is never read; a null stream is not required. This is not a raw-wire parser. |
| Cancellation | Destroy the active socket and erase owned buffers; no shutdown flush. | Abort the active Fetch request, discard its response and clear the report; no page-exit flush. |

There is no application-level retry. Browser-generated headers and a cross-origin
preflight remain additional traffic and metadata. The
[collector adapter](../../mnemion/product_telemetry/collector.py) now provides a
fixed, credential-free CORS response for `POST`/`OPTIONS`, without reflecting an
origin. This does not qualify public ingress or prove transport metadata anonymity.
Browser lifecycle/cancellation listeners are armed before Fetch. Only policy
lock polling waits for the guarded handoff's Web Lock to release; the sender
does not take a competing post-response policy lock. This preserves pagehide
cancellation while avoiding self-contention. Already handed-off bytes cannot
be recalled by opt-out. The
[client transport report](../validation/2026-10-24-telemetry-client-transports.md)
retains the initial native and browser type-check failures and earlier 11-test
native run. The final native selection passed 32 checks with two Windows-only
skips; 65 browser source checks and corrected native-build/frontend-type checks
passed. The actual Chromium journey passed 22 checks with two new reports and
two real CORS preflights, without request interception. The native collector
journey passed 18 checks with one report and 2,649 charged TLS bytes. Their
isolated profiles/servers were cleaned up; public certificate trust, full wire
cost, resources and installed-owner acceptance remain open.

## Application-owner source checkpoint

The [shared activity controller](../../studio/electron/telemetry-owner.ts) admits
at most one active attempt and throttles eligibility probes for one minute;
explicit resume restores eligibility without starting work. This is
an opportunity limit, not a periodic timer or the delivery allowance: the
seven-attempt rolling week and 24-hour-plus-jitter cooldown still apply. Only a
committed owned observation offers work; inputs/results and missed opportunities
are not retained for retry. Pause/close cancels existing work without a flush.

| Source owner | Opportunity and lifetime |
| --- | --- |
| [Desktop](../../studio/electron/telemetry-activity.ts) | Offers after the shared local measurement transaction closes; the service bridge cancels delivery on quit/suspend and resumes eligibility after resume. |
| [Browser page](../../studio/frontend/src/workspace/telemetry-activity.ts) | Offers after the measurement Web Lock is released; only a visible, already active page can attempt delivery. Pagehide, offline, visibility and connection changes cancel active work. No service worker is added. |
| [Python service/local stdio loop](../../mnemion/product_telemetry/activity.py) | Registers one owner per private installation directory within an existing service or [maintained local stdio](../../mnemion/service/mcp.py) lifespan. Fixed local policy stamps can offer committed work to that loop; closing the lifespan cancels the attempt. A one-shot CLI starts no loop or keepalive. |

The Python owner transports the disclosed local queue; it does not make remote
API/MCP traffic measurable. Unknown native metering still needs a user declaration.
The browser requires supported, fresh pressure and heap observations; unavailable
capabilities refuse delivery. These local gauges are admission controls, not
exported measurements or proof of the full CPU/RAM/wire limits. The complete
owner/lifecycle journeys remain open across supported platforms; the subsequent
browser company-policy refresh is described below. The [source validation](../validation/2026-10-24-telemetry-app-owners.md)
records **105 Python, 40 Electron and 68 browser passes**, with two Windows-only
Electron skips, and a passing frontend build. Its **19-assertion Chromium
journey** exercised the actual Privacy component and normal recording owner,
with two new reports and two real CORS preflights. CPU admission was synthetic;
real heap readings and capability presence do not establish pressure-sensor or
full resource acceptance.

## Native OS-cost admission

The [shared C helper](../../mnemion/product_telemetry/native/network-state.c)
returns only fixed cost and constraint flags through a
[Node-API bridge](../../mnemion/product_telemetry/native/network-node.c) or
[Python loader](../../mnemion/product_telemetry/network.py). These are local
admission inputs, never report fields, network names, addresses or identifiers.
The helper makes no Internet probe and changes no network settings.

| OS source | Admission behavior |
| --- | --- |
| Windows | [`GetNetworkConnectivityHint`](https://learn.microsoft.com/en-us/windows/win32/api/netioapi/nf-netioapi-getnetworkconnectivityhint) on Windows 10 version 2004 or later. Fixed/variable cost, roaming and approaching/exceeded limits are metered; insufficient connectivity is constrained. Older or unavailable support stays unknown. The rejected COM path is not used. |
| macOS | Network framework path `expensive`, `constrained` and satisfaction state. Later Intel/ARM Python/Node component builds and probes passed; installed network-admission qualification remains open. |
| Linux | Private local D-Bus reads of NetworkManager's [`Metered` and `State`](https://networkmanager.dev/docs/api/latest/gdbus-org.freedesktop.NetworkManager.html), without service auto-start. Remote `DBUS_*` overrides are ignored. Explicit `NO` can allow automatic admission; guessed `NO` stays unknown, and guessed `YES` is metered. Missing support stays unknown. |

The Linux core now uses nonblocking pending calls and bounded dispatch, with a
200 ms monotonic limit for each exchange. Messages are capped at 4 KiB, aggregate
receive storage at 8 KiB, and replies carrying file descriptors are refused.
The earlier blocking API did not bound stalled authentication; that failure is
preserved in the validation report. The C core emits no production logs.

Desktop and Python owners first perform a read-only policy/queue/allowance check,
before starting OS or resource gauges. Reservation still rechecks all rules and
is the operation that spends the allowance. The
[native coordinator](../../studio/electron/telemetry-network.ts) and Python
coordinator allow up to one second for the initial OS read and reject readings
at least one second old, measured from **query start**, including reply latency.
Existing active checks may request a refresh after
250 ms; this is not an idle timer or a guarantee that refresh finishes in 250 ms.
The one-second wait does not bound all preparation, which can also need a CPU
delta, or forcibly terminate an OS call.

Cancellation closes the gauges and invalidates late replies; queued work checks
cancellation before invoking the OS. An outstanding OS call can finish, but the
coordinator neither adopts its old result nor overlaps it with a new call.
Losing an OS capability cannot erase a known metered or
constrained observation. An explicit `unmetered` choice resolves unknown cost
only; it cannot bypass constraints or an observed metered path. An optional
additional detector also cannot override the OS's metered result.

The [desktop build](../../studio/electron/scripts/build.mjs) and
[frozen engine builder](../../deploy/build_native_engine.py) bundle the compiled
helper. Source/pip installations without it remain unknown. This is build wiring,
not installed or all-platform acceptance. The
[validation](../validation/2026-10-25-telemetry-native-conditions.md) preserves
the rejected COM and earlier replacement measurements, then records **38 Python
network, 10 Node network and 19 packaging passes** as separate selections.
The Node tests are not Electron app acceptance. Final actual component probes
recorded **2.11 MiB added RSS on Windows Node and 2.23 MiB on Linux Electron**,
both above the full-feature 2 MiB target. The
[reusable probe](../../deploy/probe_telemetry_network.py) checks the actual binary
through Python and Node. The later
[macOS component follow-up](../validation/2026-10-25-telemetry-native-conditions.md#macos-component-follow-up)
records passing Intel/ARM builds and Python/Node probes. Those component results
and the five installed control targets do not qualify all-six installed delivery
or whole-app resource/wire/collector limits; production stays false/null/null.

## Browser company-policy refresh

The [browser policy reader](../../studio/frontend/src/workspace/telemetry-company.ts)
now checks the Studio page's own `/studio/telemetry-policy` origin once after
reservation and before the report POST. It does not contact the selected memory
API, look up a workspace/account, or run when someone reads privacy status.
The [server response](../../mnemion/service/studio_policy.py) exposes only fixed
company restrictions. Collection remains unavailable in the source disclosure.

| Source boundary | Behavior |
| --- | --- |
| Request | Same-origin GET, credentials omitted, no referrer, no cache, redirects refused and keepalive disabled. HTTPS is required outside trusted loopback fixtures. |
| Response | Exact URL, HTTP 200, JSON, `Cache-Control: no-store`, absent or zero `Age`, and a declared length of 1–1,024 bytes. The fixed buffer allows at most eight read steps, including completion, and requires the exact declared length. |
| Shape | Only fixed `state`, `enabled` and allowed `metric_groups` values. Malformed, unavailable or disallowed policy prevents the report. |
| Permission | Intersect with previously observed restrictions in page memory. A relaxed response cannot re-enable a group until reload, override opt-out or acknowledge disclosure. |
| Lifetime | Both requests share the already-spent reservation and original five-second lifetime. The report handoff must occur less than one second after the policy check **started**; that freshness gate is not a separate one-second GET timeout. |

The policy GET and report POST have separate local privacy/environment fences.
Only this owner's short local lock operations are serialized; no network wait
holds the Web Lock. The same active watcher covers both requests. Cancellation
clears the report immediately, retains its token for matching-lease cleanup and
lets the finalizer await that same cleanup. A local cancellation does not mark
company policy unreadable. Rejected reports are discarded without a refund or
re-encoding into another group.

The final fence checks local choice and the last observed company restriction;
it cannot atomically order a remote administrator change after the GET with a
later collector request. The extra policy request, CORS preflight, browser
headers and TLS/TCP/IP overhead still need whole-wire qualification. Both policy
and collector ingress paths need production metadata/log review; response
headers do not suppress proxy or access logs. The
[source checkpoint](../validation/2026-10-24-telemetry-company-refresh.md) preserves
the initial cleanup failure, then **90 browser and 25 Python passes**. Its actual
Chromium journey passed **20 assertions on 25 October**, with seven policy GETs,
one four-byte TLS report, one real preflight and two policy disconnects under
cross-tab opt-out and synthetic CPU pressure. It used the real policy response
function, real heap readings and temporary certificate trust, without request
interception; the full API route was tested separately. The frontend build and
fixture cleanup passed. Public ingress, real pressure sensing, full wire/resource
cost and all-platform acceptance remain open.

## Fixed closed-week output

[AggregateWindow](../../mnemion/product_telemetry/reporting.py) retains signed
coordinate sums and per-view counts, not raw reports or client rows. Its **400
signed coordinates plus 23 counts occupy 3,384 array bytes**; that excludes Python
objects, server/TLS overhead and published output. The source bounds a window to
ten million accepted reports. A window seals once in memory and clears its arrays;
live accumulation is not persisted across restarts. The standard publisher makes
completed weekly documents immutable.

The [ASGI adapter](../../mnemion/product_telemetry/collector.py) accepts only the
fixed four-byte frame at `POST /v1/report`, with bounded body assembly and a
five-second receive deadline. It does not inspect or retain authorization,
cookie, user-agent, referrer or peer fields. It exposes no live statistics or
arbitrary query/filter endpoint. These adapter properties do not qualify the
actual server, TLS terminator, proxy or provider: transport metadata and logs
still require evidence through the complete deployed path.

Weeks are server-owned, fixed Monday-to-Monday windows. Only a closed window is
passed to a publisher callback. The reporting follow-up adds **report schema
version 2** with a root `report_range` containing one global power-of-two volume
range after **at least 64 accepted reports** in that week, for example
`[64, 128)`. Fewer than 64 reports produce no
closed-week document. This is the collector's unverified contribution volume,
not a user/device count, adoption measure or total feature usage. It adds no
live view, filter or exact count.

Each detailed view still needs **at least 4,096 reports of its own**, and
uses power-of-two count ranges such as `[4096, 8192)`. All views may remain
`insufficient_reports` in a document that contains a global volume range.
A rare/noisy cell whose confidence interval includes zero is
`insufficient_precision`, with no
published point estimate or residual. Inconsistent estimates suppress the view.
Published fractions describe sampled categories, not unique users or total
global feature usage.

Report schema v2 is separate from **wire v1**, whose four-byte packet, category
randomization and client allowance remain unchanged. The updated reader accepts
existing immutable v1 reports without rewriting them or inventing a missing
global range. The new volume bucket does not inherit the categorical
`ln(3)` bound as a participation or lifetime privacy guarantee; it remains
subject to the complete privacy and utility qualification.

The [weekly-volume source checks](../validation/2026-10-25-telemetry-weekly-volume.md)
passed **67 tests in 17.87 seconds**, covering wire distribution/privacy,
closed-week publication, legacy report compatibility, malformed/inconsistent
ranges and the actual TLS minimal runtime. This is source/component evidence;
deployment, installed behavior and full V08 qualification remain open.

Clock rollback and shutdown discard volatile state; publisher failure drops the
closed result rather than creating a raw-request backlog. The standard
[ReportStore](../../mnemion/product_telemetry/publication.py) validates complete
closed-week JSON documents and stores them in a private SQLite database, capped
at **eight weekly rows, 64 KiB per report and 1 MiB for the database**. Inserts
cannot replace an existing week's report; there is no upsert or partial
publication. Startup, reads and publication prune expired windows. The active
collector also invokes pruning at week boundaries when no new result qualifies.
The earlier [source checks](../validation/2026-10-24-telemetry-delivery.md) include
publisher tests and a **12-check actual plain-loopback HTTP journey** with
4,096 Python-encoded reports and one Node-encoded report. That isolated journey
verified immutable output, expiry without another qualifying window, empty logs
and graceful erasure/cleanup. It qualifies neither a product sender nor TLS,
provider logging, deployed restart behavior or retention of backup copies. The
publisher does not provide a public report route or configure a collection
destination. The final focused Python rerun after the test-only lint correction
passed **47 tests in 4.52 seconds** for the preceding report format.

## Component resource diagnostic

An actual Linux headless-app probe after `client-ready`, using Electron 44.9.3
and Node 24.22.0, completed **32 encodings of full 512-cell synthetic queues**.
It recorded **11.784 ms elapsed, 19.804 ms process CPU and 126,328 additional
retained JavaScript heap bytes**. Process CPU can include concurrent work and
cannot be attributed solely to the codec. Net RSS fell **405,504 bytes**; treat
that as runtime/GC variation, not memory savings or evidence of zero overhead.
The probe made no sender, network, production-memory or model calls.

This is a component diagnostic, not whole-app or all-platform resource
acceptance. The earlier cold-memory gaps and the unchanged **2 MiB added RSS /
0.5% of one core** limits remain open; this probe does not replace them. The
[validation report](../validation/2026-10-24-telemetry-delivery.md) records its
original evidence; the final Python selection and frontend build passed.

## Material usefulness limit

The conservative simultaneous interval half-width at **4,096 reports per view is
13.495 percentage points**. This threshold is per view, not total reports:
with all groups permitted, the fine-feature view receives weight `16/256`.
The new 64-report global bucket can make coarse closed-week receipt volume
visible during a small launch while every detailed view remains unavailable.
It cannot establish how many people contributed, whether the population is
representative, or which features they used. Open-week loss on restart and
unverified or repeated contributions also limit interpretation.
The [synthetic study](../validation/2026-10-24-telemetry-delivery.md) covered
18 cases with 96 trials each. Two cases had **95/96** simultaneous coverage;
the other 16 had **96/96**. These are finite simulations, not a 100% guarantee.

Rare fine-grained features remain mostly unavailable even at **65,536 reports
per view**. Small deployments at the proposed cadence will not provide precise
fine-grained statistics. Missing or imprecise output must remain unavailable,
not be presented as zero usage or confident small-population estimates.

The remaining work includes shared-budget qualification, installed policy/producer
integration, actual sender cancellation and retry behavior, real transport/log privacy,
publisher/deployment retention qualification, resource/wire measurements, utility and attack
qualification, and all six native targets plus web. No V08 requirement is closed
by this component checkpoint.

## Primary references

- [Acharya, Sun and Zhang, *Hadamard Response*](https://arxiv.org/abs/1802.04705):
  primary background for Hadamard-based local distribution estimation. This
  component's exact support/ratio checks do not inherit every claim of the paper.
- [NIST SP 800-226](https://csrc.nist.gov/pubs/sp/800/226/final): evaluating privacy
  units, composition and practical differential-privacy hazards.
- [RFC 6973](https://www.rfc-editor.org/rfc/rfc6973.html): protocol privacy and
  metadata considerations beyond an application payload.
