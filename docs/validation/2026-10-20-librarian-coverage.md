# Librarian coverage and update diagnostics — 20 October 2026

Source 4.40 adds scoped, revision-aware librarian coverage and measured local
app inactivity. It does not add a database migration or change update policy.

Five focused PostgreSQL/API/SDK cases passed: an empty or unconfigured space,
completed/skipped/attempted outcomes, changed revisions, quarantined/deleted
records, separate space and profile histories, recorded usage and current
reviewer authorization. A real librarian runner exercised the existing HTTP
contract fixture; it did not call an external model. Reading coverage issued
no new generation request. Downgraded and revoked reviewers were denied.

The coverage query uses one SQL statement so its counts share a database
snapshot. It reads metadata and observation/run counters without selecting
memory text. The service and SDK expose matching typed responses. This is
processing evidence, not a quality benchmark, exhaustive pairwise review or a
promise that all pending inputs fit a model's context.

A disposable PostgreSQL service and the actual Electron service bridge passed
the new dashboard at 1280px and 500px, with no horizontal overflow or console
errors. The app's real JSON download contained the expected space, revision
coverage and usage counts, with no memory text or bearer credential. The fixture
seeded distinguishable observations; it made zero model calls and changed no
personal workspace configuration. The SDK, web/desktop frontend and Electron
builds passed.

All **17 existing desktop update-controller cases** passed after extending the
agent status case with changing idle time and an unavailable measurement. The
same tests retain draft/transfer guards, administrator policy, interrupted
shutdown, one deliberate restart and ordinary automatic restart behavior.

The actual user's Windows installation separately completed its guarded
4.33 → 4.37 restart on 20 October, preserving its personal administrator login,
bookmarks, automatic updates, background operation and login startup. Continuous
reported computer activity had held the normal idle restart; an authorized
`app.update-restart` completed it with the normal work guards. This was an
explicit restart request, not proof of unattended inactivity on that PC.
Shared imported-source revalidation and broader live acceptance remain open.

Full native release and public update checks are reported by the automated
[release status](../RELEASE_STATUS.md) and
[maintenance board](../MAINTENANCE_STATUS.md). Local source/app checks do not
substitute for those platform gates.
