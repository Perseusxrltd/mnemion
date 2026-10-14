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

## Later 4.3.0 observation

The same host's retained update history records staging 4.3.0 at **19:45:06 UTC**
as requiring a schema upgrade, followed by the 4.2.5 → 4.3.0 transition at
**19:47:08 UTC** with migration `016_hosted_oauth.sql` and a pre-update backup.
No database restore was recorded. A later operator inspection found the host
ready on 4.3.0, automatic updates enabled, no pending recovery, and its one
managed connector running a successful 4.3.0 scan.

The initiating operator was not observed in this session. A concurrent upgrade
preflight correctly refused its obsolete 4.2.5 assumption before staging or
changing anything. This evidence does not label the schema upgrade automatic.

At **19:57:21 UTC**, three bounded authenticated Windows reads verified the
independent human administrator, the restricted contributor's single granted
space and service version 4.3.0. Both protected connection profiles remained
byte-identical; no memory was written and no model was called. This verifies
preserved API access, not a new desktop installation or named-provider OAuth
acceptance. [All six public 4.3.0 upgrade checks](releases/4.3.0-status.json)
passed separately.

## Actual Windows unattended desktop update

A passive observer subsequently recorded the installed desktop changing from
4.2.3 to 4.2.5. At **20:21:46 UTC**, the old application processes had exited.
At **20:22:31 UTC**, the installed archive reported 4.2.5. At **20:23:16 UTC**,
new application processes were running with fresh process creation times.
The recorded system-idle interval increased continuously through the transition.
No installer, restart command, update-check button or UI input was sent by the
observer. This establishes an unattended installation and relaunch on the
actual Windows desktop, separate from the CI update rehearsals.

At **20:27:54 UTC**, three bounded reads again verified the independent human
administrator and restricted contributor against the unchanged shared 4.3.0
service. Their protected profiles were byte-identical, with no memory writes
or model calls. Desktop preferences still enabled automatic updates, startup
and background operation. The 4.3.1 Windows installer was already cached;
download availability alone does not prove its installation. Further updates
remain subject to the normal idle, draft, activity and focus safeguards.

## Limits

The schema transition required independent host-operator access and explicit
migration acceptance. A workspace administrator credential cannot power on an
offline computer or operate its hosting provider. This observation does not
complete all workspace continuity, corporate identity or desktop onboarding
requirements. Private host addresses, credentials, identities, backup paths and
screenshots are excluded from this public record.
