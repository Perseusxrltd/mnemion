# Browser telemetry admission source checks

30 October 2026. Astra review of Grok's implemented
[browser admission policy](../implementation/telemetry-browser-admission-2026-10-30.md).
Browser source checks are qualified within the scope below. Actual
Firefox/WebKit, installed report delivery, resources and production acceptance
remain open.

## Implemented behavior

Python, desktop and browser admission permit bounded automatic attempts on an
unknown network, while known metering and explicit metered mode still refuse.
Unavailable pressure/heap APIs do not fabricate measurements. Supported sensors
retain freshness, validation and pressure checks. Hidden/offline pages,
data saving, cancellation and observed restrictions remain restrictive.

The reviewed corrections preserve a known cellular restriction when the network
becomes unknown or mixed, reject malformed effective network types, and refuse a
null live condition rather than reusing an earlier admissible observation.
Timer and property fixtures were corrected to exercise these decisions without
stale fixture state or timing assumptions. Disclosure version 3 requires fresh
explicit acknowledgement; connection edits cannot grant it. Opt-out, manual
review, company restrictions and spent budgets remain preserved.

The real silent-peer transport check measures the remaining lifetime of the
original reservation using both its wall-clock and monotonic deadlines. It
requires entry into the actual handshake, no HTTP request, and expiry of the
original deadline by either clock. Elapsed send time must be less than the
remaining lifetime plus 0.5 seconds. There is no artificial lower elapsed bound
and no new five-second window at send time.

## Retained evidence and scope

Evidence root:
`/home/jorqu/mnemion-completion/automation/astra-grok/telemetry-browser-admission/`.
Logs and adjacent intent/source-input/qualification receipts bind individual
runs; they do not constitute a full final-source rerun.

| Evidence relative to that root | Result and interpretation |
| --- | --- |
| `browser-astra-checks/python-delivery-policy-regressions.log` | Original selection: 80 passed, one timing assertion failed. Failure retained. |
| `browser-remaining-checks/electron-build.log`, `frontend-typecheck.log` | Original Electron build and frontend typecheck passed. |
| `browser-remaining-checks/browser-telemetry-regressions.log` | Original full browser selection: 169 passed, three failed out of 172. Failures retained. |
| `reviewed-correction-checks/browser-conditions-and-reservations.log` | Corrected focused selection: 83 passed. Combined with 89 untouched cases passed in the original full selection; no full rerun claimed. |
| `two-clock-deadline-check/original-lease-expiration.log` | Corrected real original-reservation deadline check: one passed. Combined Python qualification is 81 distinct cases across the original 80 and this corrected case. |
| `reviewed-correction-checks/native-delivery-choice-regressions.log` | 85 passed in 60.817 seconds. |
| `reviewed-correction-checks/frontend-typecheck.log` | Updated frontend typecheck passed in 19.82 seconds. |
| `reviewed-correction-checks/browser-reviewed-corrections.json` | All three recorded correction checks passed. |

Earlier failed attempts, including the original timing assertion, remain in the
evidence root. Corrections do not erase them or reclassify resource results.

## Remaining qualification

Real Firefox and WebKit journeys must use their actual capabilities without fake
sensors. WebKit-engine evidence will not qualify an installed native Safari app.
The installed diagnostic candidate
`42808919d7177619c6b06cd25e5ccde14ee2b3ae` received bounded read-only review;
it has not completed its first real six-target installed run.

The [current resource decision](../implementation/telemetry-resource-budget-2026-10-30.md)
sets an 8 MiB added-RSS allowance per participating process for new installed
acceptance and retains 0.5% CPU. Historical 2 MiB outcomes remain intact and
unrescored. Source checks do not establish resource, whole-wire, operated
collector privacy or useful fleet-report acceptance.

Production collection/destination/route remain false/null/null with empty
release certificate authorities. V08 and requirement acceptance states remain
unchanged.
