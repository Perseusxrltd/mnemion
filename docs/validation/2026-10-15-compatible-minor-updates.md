# Compatible minor updates for managed servers

The 4.7.1 source permits automatic application of a newer minor release in the
same stable major series when migration hashes and embedding generations remain
identical. This addresses the observed operator-only 4.3.2 → 4.4.0 boundary on
the shared host, whose verified plan contained no new migrations.

## Focused checks

The final service-update and managed-upgrade subset passed **40 tests**. Coverage
includes authenticated manifests, replay protection, immutable versions,
backup-before-stop ordering, accepted-write preservation, retained operator
migration safeguards and cached eligibility re-evaluation. A cached negative
decision from the older patch-only policy no longer blocks a compatible minor
release. Conversely, a cached positive decision cannot bypass a current major,
schema or model mismatch.

The existing enabled/paused scheduling test was then extended to a signed minor
release. Its two cases passed: the enabled watcher stages and applies it; the
paused watcher makes no update network calls. Existing clock-correction and
connector-lease scheduling checks remain in the focused subset.

The 4.7.0 release gate exposed a three-second supervisor socket timeout during a
real restart, before a start request was sent. The corrected transition retries
temporary timeouts within its original 60-second start or 90-second stop budget.
Nine focused cases cover connection/observation delays, a lost acknowledgement
after a named process action, delayed readiness, an exhausted deadline and an
identity mismatch. Each retry reconnects through the existing private socket and
instance checks. Idempotent role commands avoid duplicate transitions; identity
errors still fail immediately. The unpublished 4.7.0 candidate was superseded by
the 4.7.1 batch, preserving its source and failed gate evidence.

## Real installed runtime and failure recovery

The existing installed-service test's current-protocol case now crosses a minor
boundary before exercising a failed following patch. Its legacy-readiness case
retains the existing patch transition, avoiding another duplicate installation
matrix solely for the version label.

After the restart correction, the actual role-restart/verified-backup test and
the current-protocol installed-update case both passed: **two tests in 78.83
seconds** using real PostgreSQL 18, isolated credentials, signed fixture archives,
installed Python environments and live Supervisor/API/worker processes. The first update retained
the administrator, accepted memory, enrolled source identity and source
configuration. The next candidate deliberately failed worker readiness after
accepting a write; rollback retained that write in the live database. Installed
package tampering was refused. The fixture was stopped and its isolated database
removed afterward.

This process group was limited to 1.5 GiB and 1.5 CPU cores, with model downloads
disabled. It did not modify the user's shared workspace or invoke a cloud model.
The six-target release pipeline retains the complete installation and update
gates; their results and public availability are in
[release status](../RELEASE_STATUS.md).

## Boundaries

This change does not authorize automatic database migrations, new model
generations, major-version changes, unadopted hosts or fleet policy. Initial
0.x development versions retain the same-minor rule. Explicitly paused updates
stay paused. A stopped or suspended provider still needs its independent
host-management channel. U06 remains partial in the full product requirements.
