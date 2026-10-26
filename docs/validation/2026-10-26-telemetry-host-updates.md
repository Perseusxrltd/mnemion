# Managed-host update telemetry

**26 October 2026; source implementation following
`5d2a79ff21e3c13c07c5c0c5cf935f073d86480e`.** V08 remains Building.
Collection/destination/route remain **false/null/null**. This report qualifies
the source checks below, not an installed host or production telemetry.

## Ownership and observed outcomes

The dedicated automatic updater now owns fresh headless `update.download`,
`update.apply` and `update.rollback` under its **own OS-account acknowledged
installation policy**. The original supervised updater child and isolated
standalone watch executable both establish this boundary. Starting either does
not create, repair or acknowledge a telemetry choice. A remote operator's app
preference, API credentials or update permission cannot supply it.

Reusable/manual/API operations do not establish this owner. A cached ready
runtime adds no download observation; current, incompatible or held apply paths
do not invent an attempt. Verification/retries belong to fresh staging. Only a
fixed action enters the observer, which records permitted workflow, coarse timing
and fixed outcome/reason values. Versions, paths, credentials, labels, request
and result objects, exception details and operational journals stay outside it.
Shared-host resource totals are not measured.

The updater remains alive through service readiness and records successful apply
only after normal cutover completes. A candidate failure is confirmed after its
rollback fully returns. Other exceptions remain unconfirmed, including an
uncertain rollback. Interrupted unfinished work contributes nothing. A later
watcher observes a rollback it performs now; it never reconstructs an earlier
apply from private recovery history. Database rollback behavior is unchanged.

## Delivery within existing waits

During its existing five- or ten-second waits, the watcher can inspect fresh
delivery eligibility at most once per minute in that lifetime. This is an
opportunity limiter, not a separate timer or a global limit across restarts.
It can offer the bounded product queue or a still-valid approved held report,
even when ordinary pending records are zero. A new watcher need not wait for
the next six-hour update check to offer such a report.

The temporary delivery context cancels and closes its attempt, socket and gauges
before synchronous updater work resumes. The original wait deadline remains
the limit; ordinary optional errors preserve the remaining wait, and shutdown
adds no flush or keepalive. This is not a guarantee of transmission within a
minute: current choice, company policy, revision/generation, report approval and
expiry, pressure, metering, shared spending and final-send checks remain in force.

## Source validation and retained failures

The first recorded selection passed **146 cases** and failed two. The first
failure was a test wrapper that omitted the `root`/`policy_path` arguments used
by final read-only inspection; the opportunity/sleep assertions had passed.
The other was the normal Studio integrity guard: a leftover **4.46.6** staged
bundle did not match the **4.46.22** source package. Private API logs identified
`validate_bundle` before server startup. Neither required a product workaround.

The test wrapper was restored before final inspection. The normal bundle recipe
rebuilt and staged matching Studio: **658 files, 5,864,173 bytes**, in 25.598 s.
An isolated selection of the two corrected cases, a new unacknowledged-host
case and the changed preview checks passed **18 cases in 22.15 s**. Together,
**164 distinct Python cases passed**; unchanged passing cases were not repeated.
The real PostgreSQL API/worker crash-and-recovery journey passed with the
original readiness timeout and integrity guard.

The checks cover both owner entrypoints, fresh/cached staging, normal apply,
confirmed restoration, uncertain rollback, interruption followed by fresh
recovery, mid-cutover opt-out, company restriction, store recreation and optional
measurement failure. Original scheduling, busy-lock retries, migration/runtime
guards and update recovery tests also passed.

Four actual local TLS cases exercised successful delivery, wait-deadline
cancellation, opt-out and an approved held report with an empty ordinary queue.
Each sent one four-byte request and returned only after clearing the report body,
lease, activity owner and conditions. Admission gauges were controlled fixtures;
this does not qualify actual sensors, Internet/provider behavior or whole-wire
cost. The synchronous wait was driven beside the fixture's TLS peer; production
adds no worker thread.

Electron built in **7.193 s** from the actual `studio/electron` package. An earlier
build command mistakenly selected `studio/`, which contains no package manifest;
npm exited before starting a build. Its failed receipt remains retained, and only
that unstarted build was corrected. Source lint and generated coverage checks
passed. Private original logs/receipts remain under
`mnemion-completion/2026-10-26-telemetry-host-updates`; credentials from disposable
integration fixtures are not published here.

## Inventory and remaining qualification

The generated inventory now has **88 mapped and six unmeasured categories out of
94**. Its **628 declared actions/fixed variants** contain **351 mapped,
270 excluded, seven delegated and zero unmeasured among represented declarations**.
Five interfaces remain independently enumerated; host update routes are reviewed
source declarations, not a sixth interface. These counts do not establish complete
call-site, sensor, screen or platform coverage.

The batch also follows the separately qualified
[native transaction metadata change](2026-10-26-telemetry-query-ownership.md).
That change reduces statement/row allocations within current authority checks;
neither it nor these functional checks establishes RSS or CPU savings.

The **2 MiB RSS / 0.5% of one CPU core** ceilings, whole-wire limits, installed
update/rollback and privacy controls, provider/ingress/monitoring/backup assurance,
attack resistance and useful aggregate output remain open. Catalog, wire,
disclosure and route bytes are unchanged. All 66 requirements remain retained;
no completion notification or production activation is justified by this batch.
Publication and native qualification are tracked by
[release status](../RELEASE_STATUS.md).
