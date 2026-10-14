# Shared host upgrade and independent Windows access

Observed on **14 October 2026** on an existing Linux workspace host and a
Windows desktop. This is real deployment evidence, separate from the
[automatically recorded release gates](releases/4.2.5-status.json).

## Guided schema upgrade

The host was running 4.1.7. Its operator used the existing provider console and
the upgrade helper from the verified 4.2.4 source
`44e4ebdc80d8811a1314305500b87a765caa30af`.
The reviewed plan required migration `015_individual_sign_in.sql`. A backup
preceded the explicitly accepted migration and single managed-service cutover.
The upgrade completed at **14:00:10 UTC** with recovery inactive and the saved
connector configuration unchanged. The existing bootstrap installation was
preserved.

## Automatic compatible update

The same host's managed watcher subsequently discovered the published 4.2.5
update. It staged the update at **14:01:43 UTC** and completed the automatic
4.2.4 → 4.2.5 cutover at **14:03:51 UTC**, with a fresh pre-update backup and
without restoring the database. Final status reported 4.2.5, ready, automatic
updates enabled and no pending recovery.

The one enrolled connector was running and reported a successful 4.2.5 scan.
The verification did not create a second production stack or make cloud-model
requests.

## Independent Windows access

Bounded authenticated reads verified a separate human administrator and a
restricted contributor on the same workspace. Their saved, protected
connection profiles remained byte-identical. The installed Windows app then
opened the administrator's saved workspace and refreshed **Setup & this device**;
the server version was visibly **4.2.5** at **14:18:09 UTC**. The app returned to
the background with its connection and preferences preserved.

The desktop binary in this observation was **4.2.3**. Successful server access
does not establish that this particular desktop has updated; desktop update
acceptance is recorded separately. Release 4.2.5's public-upgrade matrix passed
for Windows, macOS and Linux on both x64 and ARM64.

## Limits

The schema transition required independent host-operator access and explicit
migration acceptance. A workspace administrator credential cannot power on an
offline computer or operate its hosting provider. This observation does not
complete all workspace continuity, corporate identity or desktop onboarding
requirements. Private host addresses, credentials, identities, backup paths and
screenshots are excluded from this public record.
