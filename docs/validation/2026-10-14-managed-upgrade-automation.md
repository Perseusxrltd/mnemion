# Managed schema upgrade and maintenance automation, 14 October 2026

Source version: 4.2.4. Publication is tracked separately in
[release status](../RELEASE_STATUS.md).

The first focused run passed **28 checks** of the new upgrade state machine,
existing compatible patches and the actual 013/014 → 015 PostgreSQL migrations.
The latter retain existing keys, grants, memories and original row contents and
now also reject a changed expected ledger before modifying schema.

**Eight further checks** passed for backup/runtime retention and a real managed
Supervisor service. They verify API/worker readiness while the updater is
intentionally stopped, successful restart, private role separation, a real
verified PostgreSQL backup and continued enrolled source scans. The initial
attempt to launch this check did not run because the WSL user bus disconnected;
it ran successfully after that service connection was restored.

One real signed, locked candidate installation crossed a minor-version/schema
boundary through the new operator command. Its separate candidate process ran a
synthetic appended SQL migration against PostgreSQL, selected the installed
runtime, restarted all managed children, retained the existing authentication
key and completed an enrolled source scan with the same memory identities. This
is a migration-protocol fixture, not a public 4.3.0 release. That check and the
machine-readable busy-command check passed together (**two checks**, 53.59 s).
The production release adds no migration after 015.

Recovery checks cover failed backup before any stop, uncommitted migration
failure and startup failure after commit. The last preserves accepted writes,
pins its recovery record and resumes without repeating the migration. It does
not claim automatic database rollback or test restoration by discarding data.

The new maintenance snapshot and integration scripts retain review boundaries:
issue text is never executable, truncated inventories cannot imply closure,
foreign or superseded workflow observations cannot become current evidence,
and dirty source, incoming code changes or frozen release branches cannot be
pushed/rebased automatically. Live publication of 4.2.3 had already completed
through the scripted pipeline, with all 30 release jobs, independent uploaded
verification, live website checks and six public automatic-upgrade targets
passed; its receipts were retained automatically.

The automation, integration guard and older-bootstrap handoff suite passed
**29 checks**. The maintenance script also ran against current GitHub state using
standard Python, recording seven remaining open issues and the published
4.2.3 workflows without starting another build. Version preparation regenerated
the contracts and passed validation; repository lint and formatting checks passed.

No claim is made here that the original Grokbot host or the user's Windows app
has installed 4.2.4. Actual host adoption, source observations and public release
gates keep their own evidence. Provider OAuth, shared-model ownership and the
remaining product requirements remain on the roadmap.
