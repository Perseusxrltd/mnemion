# Shared telemetry delivery budget — V08

**Unreleased source checkpoint, 26 October 2026; V08 remains Building.** The
[full contract](anonymous-product-telemetry.md) retains its scope. The
[Python delivery component](../../mnemion/product_telemetry/delivery.py) and
[native TypeScript component](../../studio/electron/telemetry-delivery.ts) now
share private reservation accounting and cancellation fences. The focused
[native/Python source checks](#source-validation) passed. A later
[browser origin budget](#browser-origin-budget) now has focused and actual-browser
[component evidence](../validation/2026-10-24-telemetry-browser-delivery.md).
The subsequent [Python TLS transport](../validation/2026-10-24-telemetry-transport.md)
now has source/runtime and isolated loopback component evidence. The later
[native and browser transports](../validation/2026-10-24-telemetry-client-transports.md)
also exist in source: the final Electron selection passed **32 checks with two
Windows-only skips**, and **65 browser source checks** passed. Actual loopback
TLS/collector journeys passed **22 browser checks and 18 native checks**.
The subsequent [application-owner batch](../validation/2026-10-24-telemetry-app-owners.md)
adds connection controls, live environment checks and opportunistic delivery
wiring in source. Its source checks and actual Chromium owner fixture passed;
CPU admission in that fixture was synthetic, and full sensor/resource/platform
acceptance remains open. **Production collection remains disabled** with
`collection_available: false`, `destination: null` and a null route. Installed
production-delivery qualification remains open.

The later [release-owned TLS trust follow-up](../validation/2026-10-26-telemetry-scoped-trust.md)
uses route version 2 with at most two public CA certificates, each at most
4 KiB. Native/Python senders require this explicit trust before connecting;
browser TLS is unchanged. The current unavailable route has a null address and
empty authority list. This changes no reservation, allowance, approved packet,
destination/address binding, deadline or consent/generation fence, and adds no
CA digest to reports. Passing local source checks do not qualify whole-wire
cost, installed delivery or the unchanged 2 MiB / 0.5% resource gates.

The [completed scoped-trust resource result](../validation/2026-10-26-telemetry-scoped-trust-results.md)
retains six functional cases with 2,053 matched source files each and passing
cleanup. Both enabled main matched maxima and endings remain above 2 MiB.
All roles, opted-out controls and earlier failures remain retained; differing
ambient fixture trust across revisions prevents a causal savings comparison.
Combined CPU remains descriptive, the resource gate fails, and no repeat
measurement or budget change is selected.

The later [cold-start allocation corrections](../validation/2026-10-26-telemetry-cold-start.md)
avoid materializing the general TLS certificate list during sender import and
throwing exceptions for an absent optional company policy. Release trust and
fresh permission checks remain unchanged, with no positive permission cache.
Two ordinary-Node tests and 95 actual Electron checks passed, with two platform
skips and a passing Electron build. The fixed two-case source-app follow-up
completed with matched inputs and cleanup; its lower weighted JavaScript
allocation samples establish no RSS/CPU saving or resource acceptance. All
earlier failures and the 2 MiB / 0.5% budgets remain retained.

The later [metadata-allocation follow-up](../validation/2026-10-26-telemetry-metadata-allocation.md)
reuses fixed path/URI strings and owner-local validation of copied release trust;
group filtering shares strict decoding with full preview/wire descriptions.
Filesystem/ACL, SQLite, policy, endpoint and TLS checks remain fresh. URL
derivation/filter description/certificate decode counts are 1/0/1 against
original 5/3/130, with unavailable trust still zero. Actual Electron passed
100 checks with two Windows-specific skips;
134 browser-source tests, all-coordinate Python comparison and both builds
passed. No RSS/CPU saving is established. One fixed six-case changed-source
comparison is selected after integration, with its result pending and all prior
resource failures and budgets unchanged.

The later [five-target installed-control qualification](../validation/2026-10-26-telemetry-preview.md#five-installed-native-targets-qualified)
verified Linux and Windows x64/ARM64 plus macOS ARM64 against **64 required true
fields each**, including fixed format preview, app/native choice parity and
opt-out persistence across restart. Windows ARM64 used x64 engine/database
components under emulation. The overall 4.46.12 run failed on Intel Mac and
remains unpublished. Controls now show the fixed synthetic example `AQAHAA==`;
actual-body fields remain null/zero with `outbound_state: "not_inspected"`.
[Exact-next-packet inspection](anonymous-product-telemetry.md#proposed-outbound-schema-and-payload-preview)
and installed production delivery remain unqualified.

This follows the [codec/collector/publisher checkpoint](anonymous-product-telemetry-delivery.md).
Its earlier passing checks do not qualify these new budget components, actual
wire usage or installed sender cancellation.

## One private native/Python allowance

[Policy storage version 6](../../mnemion/product_telemetry/policy.py) retains the
seven-slot attempt ledger and delivery-state row introduced in version 4, and
the version-5 `connection_mode` preference. Version 6 adds one bounded private
review row and fences older senders. Native and Python processes using the same OS account
and configured store serialize reservations with the same database transactions
used for choice changes. This is not a person-wide allowance across independent
installations, browser profiles or copied stores. The public control schema
version is unchanged.

The later [native storage-slot change](../validation/2026-10-26-telemetry-storage-slot.md)
adds one nonwaiting process-wide claim before asynchronous permission/SQLite
work, held until actual connection closure. Competing optional samples decline;
an unrelated caller cannot release the claim. Shared SQLite still coordinates
other processes, with the same current-policy and durable-spending fences.
Windows permission-helper ownership separately lasts until actual process
exit, even after a refusal deadline. The source checks do not qualify installed
platforms or resources; this follow-up is excluded from frozen 4.46.14.

| Source reservation bound | Meaning |
| --- | --- |
| Seven attempts per rolling week | Each committed reservation spends one slot, regardless of its later outcome. |
| At least 24 hours plus jitter between attempts | The next eligible time adds a fresh random delay from zero through one hour. There is no scheduler or idle wake. |
| 65,536 reserved bytes per attempt | Fixed reservation; actual transport upper bound remains unqualified. |
| 262,144 reserved bytes per rolling day | The 256 KiB daily guard applies to the same shared ledger; it does not qualify a transport's actual cost. |
| Five-second prepared-report validity | Both the shared wall-clock lease and a process-local monotonic deadline must remain valid. This is not a network-completion guarantee. |

Reservations require current disclosure and enabled policy, matching revision
and private `store_generation`, a permitted metric group, usable queued cells,
and admissible connection/resource conditions. The later owner components supply
current local gauges at admission and during the active attempt. Their source
wiring does not establish all-platform sensing or resource acceptance.

The later [native OS-admission source change](../validation/2026-10-25-telemetry-native-conditions.md)
adds a read-only eligibility check before desktop/Python owners start gauges.
Unavailable collection, stale choice, an empty queue, exhausted allowance or
cooldown can refuse that work without an OS probe. This precheck does not spend
or promise a reservation; the normal transaction still rechecks every rule.
The initial network-read wait and reading freshness are each bounded to one
second; freshness starts at query initiation, so reply latency consumes that
allowance. Only existing active checks can request a refresh after 250 ms, and
an outstanding OS call is never overlapped. Cancellation prevents a queued probe
from starting, rejects late replies and closes gauges. The separate five-second
report lease and spending rules are unchanged. Focused network and packaging
checks passed. Later
[macOS ARM64/x64 compiled-probe results](../validation/2026-10-25-telemetry-native-conditions.md#macos-component-follow-up)
passed in Python and Node 22.23.2; they do not qualify Electron, the complete
delivery path, installed platforms or full resource acceptance.

The [producer-overhead follow-up](../validation/2026-10-25-telemetry-producer-overhead.md)
lets native/Python producers decline repeated work after observing explicit
opt-out or an exhausted scope. That checkpoint checked the private file version,
day and a monotonic interval of at most 60 seconds; expiry is lazy, with no idle
timer or positive consent cache. Every accepted observation, reservation and
final handoff still uses the full current-policy/storage fences. Contribution
limits and spent allowance are unchanged. The scoped diagnostic still exceeded
the 2 MiB full-feature RSS target in both opted-out and enabled variants.

The next [native denial-allocation follow-up](../validation/2026-10-25-telemetry-memory-profile.md)
merges exhausted scope hints only for the same file version/day, preserving the
original expiry rather than renewing it. Fixed desktop workflow propagation
allows that refusal before a UI snapshot opens SQLite. It changes neither
accepted-work fences nor contribution/delivery allowance. Both completed
diagnostic modes retained one spent reservation and cleared the enabled lease;
the real-memory and synthetic measurements do not establish resource acceptance.

The later [denial-I/O follow-up](../validation/2026-10-25-telemetry-denial-io.md)
reuses known negative file observations for at most **250 ms** during work.
File changes may remain unseen until the next refresh; re-enabled work can lose
optional samples during this interval. Choice/status, admitted writes,
reservations and final handoffs retain fresh checks. Day/original-expiry checks
remain in force, Python scope merges preserve that expiry, and no timer or
positive consent cache is added. Delivery accounting is unchanged.
The latest native snapshot path returns known refusals synchronously; eligible
work still uses the fresh asynchronous private-store read. Its final source
checks and component burst passed; full resource/platform acceptance remains
open, and existing reservation/handoff checks are unchanged.

| Persistent connection choice | Delivery admission |
| --- | --- |
| `auto` (default) | Unknown metering refuses the attempt; Wi-Fi/Ethernet alone does not prove an unlimited plan. |
| `unmetered` | An explicit declaration resolves unknown metering only. Detected data limits, offline state, pressure and privacy restrictions still refuse delivery. |
| `metered` | Delivery is paused regardless of the observation. |

App/native processes share this choice in their private OS-account store;
browser choice remains local to its origin/profile. It is not tied to a network
name or address and persists until changed. Explicit configuration clears queued
measurements and the lease while preserving spent attempts/cooldown. A stale
opt-out preserves a newer connection choice; an omitted field also preserves it.
Editing the connection choice does not acknowledge an unseen disclosure.

The [new headless Windows cost reader](../validation/2026-10-26-telemetry-headless-network.md)
can supply the same OS admission flags when the packaged helper is absent;
it does not bypass a present broken or unreadable helper. Linux/macOS source
installs without the helper remain unknown. A completed valid unknown probe
does not itself assert a constraint: the existing explicit unmetered choice
can resolve unknown cost, while automatic mode and all other vetoes remain
unchanged. The Windows component pass is not installed/resource acceptance.

Explicit native/Python `configure` permits up to **250 ms per busy SQLite lock**
after a brief-reader regression exposed a failed opt-out. This is not a total
250 ms bound for the entire action or a guarantee that a persistent lock can be
overcome. Producers and delivery retain zero lock waiting; no retry queue or
spending refund is added.

Backward wall-clock movement refuses reservations rather than pruning spending
or restoring allowance. The ledger reader also checks that its latest attempt
matches the saved time, cooldown is 24–25 hours later, any live lease ends five
seconds after that attempt, and an empty ledger has only pristine initial state.
Busy, damaged, unsafe or unsupported storage fails closed. Reading status does
not initialize or migrate a store; older supported controls stores report
`upgrade_required` for delivery accounting. Supported
Python policy writes migrate them within the existing transaction, preserving
the choice, generation rules and any existing spent ledger. Adding the version-5
connection preference defaults older stores to `auto`; it does not grant a new
allowance. This is not automatic repair of
damaged settings.

## Reservation consumes the queue

In default automatic mode, within one write transaction, reservation rechecks policy, clock, cooldown,
active lease and both spending limits. It selects permitted bounded cells and
prepares one [four-byte randomized body](anonymous-product-telemetry-delivery.md).
Encoding and entropy must succeed before spending is committed. The transaction
then records the attempt and reservation, sets the cooldown and private lease,
and consumes the entire pending measurement queue.

Every returned reservation is spent. Failure, cancellation, crash, a lost result
or an unused report does not refund it or restore the queue. An explicit opt-out
clears pending measurements, local contribution counters and the stored lease,
but **retains spent attempts and cooldown**. Re-enabling cannot revive those
measurements or buy a fresh delivery allowance. The attempt ledger is private
control accounting, not product usage data.

The local [status interface](../guides/product-telemetry-controls.md) exposes
bounded attempt counts, reserved-byte totals and fixed states through
`delivery_budget`. It does not expose exact attempt times or lease tokens.
Those values and the local generation never enter the report body or analytics
identity. Counters describe reservations, not successful uploads; `ready` is an
accounting state and does not enable collection.

## Optional review before reservation

The [new source controls](../validation/2026-10-26-telemetry-report-review.md)
allow manual mode to be selected before collection permission. Staging itself
requires current permission, disclosure, a configured route, usable observations
and available delivery allowance. It reads no performance gauges and spends no
attempt. [Inspection](../../mnemion/product_telemetry/inspection.py) stores one
fixed four-byte reviewed report under the
[current selection contract](../validation/2026-10-26-telemetry-review-selection.md)
and consumes only that pending snapshot. Repeated inspection changes neither
its bytes nor its original expiry.

Approval changes that report's state; a later eligible owner reserves the
**same bytes** once, with the existing five-second lease and spending rules.
The report's original review lifetime, policy revision/generation, metric groups,
disclosure, catalog, wire version and destination binding are checked again at
handoff. New observations produced during review remain pending, and contribution
limits and spent budgets are not reset. The staged snapshot is never restored
after discard, expiry, invalidation or an unsuccessful delivery attempt.

The [approval handoff correction](../validation/2026-10-26-telemetry-app-review.md)
keeps automatic app/browser preflights at their existing once-per-awake-minute
cadence and permits at most one additional explicit approval preflight per
minute. Native and browser approval callers use this shared owner path. A single
copied policy stamp can wait for active cancellation/cleanup; pause or close
discards it. Every attempt still needs current eligibility, consent, spending,
sensors and transport checks. This creates no timer, wake or extra allowance.

Native/Python storage uses private SQLite schema **6**. Browser choice schema
**5** and budget schema **2** retain spending and use a write-ahead pending-entry
clear under the origin lock. These versions fence older senders from bypassing
a newly selected hold. Status reads do not migrate storage or reveal packet
bytes. Manual mode remains selected after expiry, discard and consumption;
returning to automatic is an explicit action that clears the held report.
Production collection stays false/null/null, and this unreleased implementation
has passing source and isolated Chromium control checks. Interactive privacy,
utility, full resource and installed acceptance remain open.

The later [compiled Linux app journey](../validation/2026-10-26-telemetry-app-review.md)
passed nine review checks and delivered exactly one accepted four-byte TLS body
matching inspection. Opt-out/manual mode and one spent attempt survived restart;
cleanup passed. Its 24 Electron-runtime and 14 browser-source tests passed
separately. These results qualify the recorded source fixture, not actual
web-browser delivery, installed targets, provider privacy or resources.

## Review-clock foundation

The later [source checkpoint](../validation/2026-10-26-telemetry-preview.md#review-clock-foundation)
adds [Python](../../mnemion/product_telemetry/review_clock.py) and
[portable TypeScript](../../studio/electron/telemetry-review-lifetime.ts) review
lifetime validation. The maximum is **15 minutes**, shortened by the supplied
observation expiry. Checks retain the original creation/expiry values and reject
missing or changed epochs, backward clocks and either elapsed or wall-time
expiry. This is separate from the existing **five-second delivery lease**;
it neither reserves an attempt nor changes spending or queued observations.

The [native reader](../../studio/electron/telemetry-review-clock.ts) uses the
shared C clock through Node-API or Python. Linux/macOS source reads an OS boot
epoch and suspend-inclusive elapsed time; Windows source uses an explicitly
initialized volatile per-user epoch and interrupt time. Ordinary native reads
cannot initialize or repair the Windows marker. These epochs are private local
control only and must never enter telemetry or its wire body. Linux, Windows
x64 and later macOS Intel/ARM runtime component checks passed; Windows ARM64
and installed review acceptance remain open.

For headless Python without a packaged helper, the
[direct OS reader](../../mnemion/product_telemetry/review_clock_system.py) uses
the same review clock without a compiler. An existing broken helper or an
unavailable helper result is never bypassed. Actual Linux/Windows x64 comparisons
matched the helper; the [later macOS Intel/ARM64 comparison](../validation/2026-10-26-telemetry-report-review.md#compiler-free-headless-review-clock)
also passed with Python 3.12.10 and Node 22.23.2. Whole-CI, installed and resource
qualification remain separate. This fallback changes no delivery allowance,
permission or network-admission rule.

[BrowserReviewClock](../../studio/frontend/src/workspace/telemetry-review-clock.ts)
uses only live same-origin pages, a short Web Lock and bounded BroadcastChannel
discovery. It creates no worker or persistent storage. `read()` opens no channel,
waits for nothing and cannot initialize an epoch. Explicit `ensure()` can create
one or join a still-live matching epoch; losing all peers prevents revival of
an old lifetime. The new report-review source connects this clock to staging,
approval and handoff without changing its original lifetime. It is not in
released 4.46.13, and clock component checks do not establish the new review
path's full rollback, resource or platform acceptance. V08 stays Building and
collection remains unavailable.

## Cancellation and the final handoff

A prepared report is a process-local, one-use body with a private lease and the
originating revision/generation. Revalidation checks current choice, disclosure,
company groups, clock and lease deadline. A process-local monotonic deadline
also limits eligibility to five seconds from preparation's start, so stalled
wall time cannot extend it. Cancellation retains the token for
matching stored-lease cleanup while clearing the reusable local report. Invalid
checks and failed or expired handoffs use that same cancellation path after
closing their transaction. Spending remains consumed. Busy or unreadable storage
can prevent immediate durable cleanup, but an expired lease does not authorize a
later handoff.

The final `guarded_write` / `guardedWrite` operation takes the SQLite write lock,
rechecks permission and consumes the local handle before invoking one reviewed
**synchronous, nonblocking socket handoff**. That same lock serializes an explicit
choice change. DNS, TLS setup, response waiting, arbitrary callbacks and awaited
work do not belong inside this critical section. The source currently has no
production transport wiring. The Python and native TLS components perform connection
setup outside this lock. Bytes already handed to a transport cannot be recalled
by a later opt-out; installed cancellation still requires its own proof.

The subsequent source change claims each report's application handoff once
before competing callers can proceed. A losing handoff returns without writing
again or cancelling the winner. All three implementations now erase the used
body but retain the lease after successful handoff, so the active attempt can
still be cancelled. Its owner must call `cancel()` on completion, including a
successful response. Python's `claim_transport()` and the native/browser
`claimTransport()` separately claim the full attempt before setup or cleanup
ownership, so a duplicate cannot connect or cancel the winner. The earlier
[Python checks](../validation/2026-10-24-telemetry-transport.md) and later
[client transport checkpoint](../validation/2026-10-24-telemetry-client-transports.md)
record their separate evidence; the older results below retain their earlier scope.

The optional watcher checks the current report at a nominal 25 ms interval only
during an already active attempt. It can request abortion when permission or the
lease is lost. It is not an idle task, a scheduler, a shutdown flush or a substitute
for the final handoff check. Transport components own watcher cleanup on
success and cancellation; installed delivery during owner shutdown remains unqualified.
The interval alone is not a measured
cancellation-latency guarantee. A throwing synchronous abort callback is
suppressed without a retry or second invocation; report cleanup still runs.

## Browser origin budget

**Source component checkpoint, 24 October 2026.** The browser
[budget schema](../../studio/frontend/src/workspace/telemetry-budget.ts),
[delivery component](../../studio/frontend/src/workspace/telemetry-delivery.ts)
and [privacy policy](../../studio/frontend/src/workspace/telemetry-policy.ts)
coordinate tabs of the same browser origin. They do not share native/Python
SQLite accounting, another origin, another browser profile or a remote host's
allowance. No account, device or cross-origin identifier joins those stores.

| Boundary | Native/Python | Browser |
| --- | --- | --- |
| Durable state | Existing private SQLite policy database, storage version 6 | Origin-local localStorage choice version 5, separate budget version 2 and the existing aggregate queue |
| Serialization | SQLite transaction shared with explicit choice changes | The same privacy Web Lock for choice, producer writes, reservation and final handoff; delivery refuses an unavailable or busy lock |
| Queue consumption | Attempt accounting and queue deletion commit together | Spending and a clear intent are written first; queue cleanup must finish before new work is admitted |

The browser uses the same seven-attempt rolling week, minimum 24-hour spacing
with up to one hour of jitter, 65,536-byte reservation and 256 KiB rolling-day
guard. It also checks both a wall-clock lease and a local monotonic deadline for
five-second report validity. The budget parser accepts at most 8,192 characters,
seven attempt entries and fixed fields; it rejects inconsistent times, leases
and generations. These are source accounting controls, not measured network
bounds or browser resource acceptance.

Because localStorage does not provide a multi-key transaction, reservation first
persists spending and a `clear: entries` marker. Under the same Web Lock, cleanup
empties pending measurement entries while retaining contribution counters, then
resets the marker to `none`. An interrupted clear remains recorded. The next
owned mutation completes it before admitting another observation or reservation;
status reads never repair it, and pending cleanup keeps collection ineffective.
A failed or lost attempt does not refund the reservation or restore its queue.

For an explicit choice change, the same tab first invalidates its owned reports.
Opt-out is saved before cleanup; enabling is saved only after `clear: all` has
removed the pending queue and contribution counters. Both choices preserve
spent attempts and cooldown and revoke the lease. Even if only the choice key
was removed, surviving budget state is retained rather than reset. On a write
failure the session fails closed and tries to remove the old acknowledgement;
it never deletes the spending ledger as a repair shortcut. Missing budget state
for a current choice or a mismatched generation is unreadable, not a fresh
allowance. GPC, company restrictions, disclosure and missing Web Locks continue
to gate effective collection.

The final browser handoff rechecks policy and both deadlines under the privacy
Web Lock, accepts only a synchronous nonblocking callback and erases the body
after one use. A successful browser handoff keeps its private lease cancellable
until completion or abort; the owner must finish it with `cancel()`. The later
native/Python handoff now follows this same rule. The new application-handoff
claim prevents competing calls from sending twice or cancelling the winner;
the later transport report records its separate component evidence. The later
browser owner is wired in source but remains inactive. Bytes already handed to
a transport cannot be recalled.

Only an owned active attempt installs the transport watcher's storage-change and page-hide listeners,
same-tab invalidation and nominal 25 ms checks. Cancellation removes these
listeners and timers, clears the report and attempts matching-lease cleanup.
An abort callback fault is suppressed without a retry. There is no idle watcher,
shutdown flush or background sender. The
[dedicated browser validation](../validation/2026-10-24-telemetry-browser-delivery.md)
records **44 focused passes and 20 actual Chromium checks**, including cross-tab
reservation, final fencing, one active loopback fetch aborted by opt-out, and
quota/crash recovery. Cleanup of three isolated contexts, the browser session
and server was verified. These component results do not qualify actual whole-wire
cost, production transport, resources, all platforms or released telemetry. The
native/Python evidence below remains separate. The later
[transport checkpoint](../validation/2026-10-24-telemetry-transport.md) records
**21 fresh actual Chromium checks**, including competing handoffs that preserve
the winner's live lease, and verified cleanup; it does not replace the earlier receipt.

The subsequent [browser Fetch sender](../../studio/frontend/src/workspace/telemetry-transport.ts)
claims the full attempt before starting work, uses the remaining report lifetime,
and creates one four-byte request inside the final Web Lock fence. It omits
credentials and referrers, refuses redirects and disables keepalive, with no
application-level retry or page-exit flush. Lifecycle and cancellation listeners
are installed before Fetch; only policy lock polling waits for the guarded
handoff to release its Web Lock. This avoids competing with the attempt's own
lock without leaving a pagehide gap. There is no competing post-response lock
read. Success requires status 204, the exact destination, no redirect and
`Content-Length: 0` within the active deadline; the response body is never read.
Its source selection passed **65 checks**, and the actual-browser TLS journey
passed **22 checks**, recorded with cleanup and retained failures in the
[client transport checkpoint](../validation/2026-10-24-telemetry-client-transports.md).
Fetch does not expose TLS/TCP/IP byte counters or a response-header cap; browser
headers, cross-origin preflight and connection behavior remain separate wire and
privacy qualification work. The 65,536-byte reservation is unchanged and is not
a proven bound on that traffic.

The subsequent [company-policy refresh](../validation/2026-10-24-telemetry-company-refresh.md)
adds a separately fenced same-origin policy GET before the report handoff, after
spending the reservation. It consumes the same five-second lease; refusal or
timeout does not refund spending, restore the queue or choose another report
view. The final report also requires a policy check started less than one second
earlier. The fixed reservation is not a measured bound for the policy request
plus report, preflight and connection traffic.

The browser serializes at most four pending short lock operations from the same
owner, while other tabs still face nonwaiting Web Lock admission. Network work
does not hold that lock. Company invalidation clears the owned body immediately
and shares one awaited matching-lease cleanup with its finalizer; it does not
discard the cleanup token early. A local abort does not fabricate unreadable
company policy. Focused checks and the **25 October, 20-assertion Chromium
journey** passed, including retained spending and lease cleanup after policy
refusal, cross-tab opt-out and synthetic CPU pressure. Its seven real policy
reads, one report and one preflight are component evidence, not whole-wire or
platform acceptance. Fixture cleanup was verified. The older native/Python
evidence below is unchanged.

The later [browser pressure corrections](../validation/2026-10-26-telemetry-browser-pressure.md)
allow up to three seconds for the first nominal signal **before reservation**
and measure the unchanged two-second freshness ceiling from `PressureRecord.time`,
not callback arrival. Invalid, future, negative and expired sample times refuse
admission. Heap/network/visibility gates, cancellation, privacy, spending and the
five-second report lease remain unchanged. Nine unit tests and the separately
completed frontend build passed. The final-source real browser refused at
3,002.1 ms without a usable signal; its cause is unknown, cleanup passed and no
report or model call occurred. The earlier 2,089.3 ms pass is historical for the
startup-only source. That checkpoint selected no further pressure trial and left
nominal-browser, full-app/delivery and 2 MiB / 0.5% acceptance open.

The later [browser admission and review follow-up](../validation/2026-10-26-telemetry-browser-admission.md)
received a real nominal sample at 2,414.2 ms with age 0.6 ms; the earlier timeout
remains unexplained. Browser ownership now propagates cancellation through
eligibility, sensor startup and cleanup without changing admission or spending
bounds. All 134 browser-source tests and the frontend build passed. The compiled
Chromium app then passed ten review checks across two launches and nine memory
operations, with one approved four-byte TLS report matching inspection and a
real nominal sample aged approximately 0.7 ms. Final fixture cleanup passed;
the original missing Python cleanup receipt remains unqualified. Its disposable
certificate SPKI exception does not qualify production browser trust. Prior
resource failures, 2 MiB / 0.5% limits and other platform/privacy gates remain open.

## Source validation

These results cover the preceding **native/Python** batch, before the browser
budget and subsequent TLS/handoff-ownership changes. No acceptance of those later
changes is inferred from them.

| Final source check | Result and scope |
| --- | --- |
| Python | **55 passed in 10.95 seconds** across delivery, policy, aggregate and MCP cases. |
| Actual Electron 44.9.3 / Node 24.22.0 on Linux | **19 passed, two Windows-only ACL skips**, 21 total, in 8.908 seconds: ten delivery and nine existing store successes. |
| Native source build | Passed; no installed-package or all-platform acceptance follows. |

The focused checks cover shared reservations between real Python and Electron
processes, crash/restart spending, contention, opt-out before the final callback,
one-use handoff, lease cleanup without refunds and a stalled wall clock bounded
by the monotonic deadline. Both watcher outcomes now run: a successful abort
callback and one that throws, with no second invocation or forwarded fault.
They use synthetic queues and controlled callbacks, not an installed sender or a
qualified network transport. The preceding **54 Python / 18 Electron** results
and earlier **44/53 Python passes and 17 Electron passes with two Windows-only
skips** remain historical;
the initial TypeScript row-narrowing compile failure is also retained. Selected
Ruff checks passed before this final callback follow-up. The final runtime runs
include cleanup, ledger-invariant, monotonic-deadline and abort-fault handling.

| Original evidence | SHA-256 |
| --- | --- |
| Final Python abort-fault selection | `161c843074568c4d6d00d58062bcbee724c32069f66b571025760dca4524599d` |
| Final actual Electron abort-fault selection | `a7720ea447a021eb1356cde90b28557cf533b8b3eb589bee0f66c9196ba8cfcf` |
| Final native source build | `873b841c25f2b8da83857d248087de185ea22e1986b5fb6eb43f96e70e00896b` |
| Earlier Python monotonic-deadline selection | `399a76b383d7cd5934aca5b04f55951bbf6b17bdf6c8c00fe735f6883d6559a2` |
| Earlier actual Electron monotonic-deadline selection | `e48f9dd09639bf1df24149ea9449cb8c4cfa74410096d480e5fab09408bc8e85` |
| Earlier Python cleanup selection | `d6bb33fb1f37c75435e7c716b5b47c3590d1fa435527754f7c8d68a85f040112` |
| Earlier actual Electron selection | `e15ec9ff989c8cec7ef1fc9365fe21f2fd5432bc8caf8c0e30a974cb73864d9c` |
| Original TypeScript compile failure | `7887ed8c125489e4ef87d5857d704c8b123148b4b337f1d80aed2dbc86ba46a6` |

## Remaining acceptance

The conditional per-report `ln(3)` bound still protects only the sampled category
in a chosen permitted view. A seven-report composition bound depends on every
actual attempt using this shared allowance; the source owner checks do not yet
qualify every installed path. These local controls do not establish participation, policy-choice,
person-wide or lifetime privacy. They do not recover spending after a store is
lost or recreated, or detect an unobservable whole-machine snapshot rollback.
Rejection of an older prepared report after recreation has a
[source test](../../tests/test_product_telemetry_delivery.py). That
is distinct from recovering lost allowance: the generation/disclosure rules
cannot reconstruct a missing attempt ledger.

Qualification of the new canonical-owner wiring, browser release/resource acceptance,
actual sender integration and cancellation, conservative accounting of all
connection/retry overhead, qualified ingress and retention, and all six native
targets plus web remain open. Earlier component resource diagnostics do not
qualify the unchanged **2 MiB added-RSS** and **0.5% of one core** limits. The
codec's small-population utility limits are unchanged. No requirement is closed
by these source components.
