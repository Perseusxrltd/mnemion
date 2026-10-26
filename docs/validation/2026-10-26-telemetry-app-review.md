# Source-app report review and approval handoff — 26 October 2026

The working patch based on `4b8e8a3e407970c271600be803e387b0143a70c7`, intended
for 4.46.28, fixes an observed approval handoff failure. The authoritative
`source-qualification.json` in the private `2026-10-26-telemetry-app-review`
evidence set binds **2,172 source and compiled input files** to the completed
journey. This is source-app evidence, not release or installed-platform acceptance.

## Observed failure and corrected owner

The original app journey completed seven review/choice checks and all three
memory cycles, but its approved report remained unconsumed. Successful
observations had already used the shared owner's automatic 60-second preflight
slot; approval reused that throttled path. The deterministic old-owner test
then reproduced the missed second check with `1 !== 2`.

[TelemetryActivity](../../studio/electron/telemetry-owner.ts) retains the existing
automatic one-per-awake-minute cadence and permits at most one additional
explicit approval preflight per minute. It copies only the original policy
revision/generation into one pending slot while active work finishes cancellation
and cleanup. Pause or close clears that slot. It retains no new packet or timer,
adds no idle wake, and still requires fresh eligibility, consent, spending,
sensor admission and transport checks before delivery.

The [native caller](../../studio/electron/telemetry-activity.ts) and
[browser approval action](../../studio/frontend/src/workspace/telemetry-policy.ts)
use this explicit path. Approval remains permission for one eligible attempt;
it does not establish successful delivery or change allowance limits.

## Completed qualification

| Evidence | Result and scope |
| --- | --- |
| `handoff-checks/approval-handoff-followup.json` | Electron build passed; 24 owner/delivery tests passed in the actual local Electron binary running Node mode, with zero failures/skips. |
| `handoff-checks/browser-inspection.log` | 14 browser-source inspection tests passed, zero failures/skips; no actual web-browser journey is credited. |
| `journey-r5/review-result.json` | Nine review checks passed in the compiled, unpackaged Linux x64 app, Electron 44.9.3 / Node 24.22.0, using actual sandboxed IPC, the copied-source CLI over private stdin and loopback TLS. |

The nine checks cover required disclosure, manual choice before permission,
app disclosure acknowledgement, repeat inspection preserving exact bytes,
native opt-out invalidating review, re-enable starting empty, discard without
spending, approved delivery of the inspected body, and opt-out/manual-mode
persistence across restart.

The completed journey used **two app launches** and **three synthetic
save/fetch/recall cycles**, with nine memory API operations and 12 successful
HTTP requests. It made no model calls. Exactly **one four-byte TLS report** was
accepted and matched the inspected body; the fixture collector recorded zero
forbidden metadata. The private ledger retained one spent attempt and 65,536
reserved bytes after restart; the lease and queue were clear. This reservation
is not a measured whole-wire cost. Opt-out and manual mode persisted.

Cleanup removed the isolated profiles and certificate profile, stopped the
collector and left production disclosure unchanged. `source-qualification.json`
retains receipt/input hashes; the completed result's SHA-256 is
`4a73a8d739051f707f8f49984ce76d5ef79e7e449e09c20bbba2c4c9d4bad8e5`.

The three initial probe errors remain in `journey/review-failure.json`,
`journey-r2/review-failure.json` and `journey-r3/review-failure.json`. The actual
approval failure remains in `journey-r4/review-failure.json`, with its cause and
planned correction in `approval-handoff-plan.json`. The expected failing
old-owner reproduction remains in
`cooldown-reproduction/ignored-manual-approval.log`. Later passes do not erase
those failed attempts.

## Reusable diagnostic

The [existing workflow](../../.github/workflows/telemetry-renderer.yml) now has a
separate review mode. Replace the placeholder with the full reviewed 40-character
source SHA:

```sh
gh workflow run telemetry-renderer.yml -f source="<full-reviewed-sha>" -f review_journey=true
```

Do not combine `review_journey=true` with `attribution=true`; the workflow rejects
that combination. The new review mode has not yet been exercised remotely.
The result above came from the local source-app diagnostic.

All 66 requirements and states remain unchanged. V08 remains Building, with
collection unavailable, destination/route null and release authorities empty.
Actual web-browser delivery, six installed targets, whole-wire cost and
provider/privacy qualification remain open. No new resource run was selected;
the [scoped-trust resource result](2026-10-26-telemetry-scoped-trust-results.md)
still fails the unchanged 2 MiB gate, and the 0.5% CPU gate remains unqualified.
No full V08 or release-readiness claim follows from this journey.
