# Windows installed backup connection observation

**Source follow-up, 26 October 2026.** The 4.46.11 candidate's
[Windows x64 job 121355505641](https://github.com/Perseusxrltd/mnemion/actions/runs/40254768233/job/121355505641)
in [run 40254768233](https://github.com/Perseusxrltd/mnemion/actions/runs/40254768233)
failed during the first encrypted-backup preflight. Its frozen source was
`8a81ce68f0060cb06693cb44c0f381e907911cd6`. The candidate remains unreleased;
the source refinement below has focused checks, with corrected installed
Windows acceptance still pending. See [release status](../RELEASE_STATUS.md)
for current availability.

## Original observation

The retained artifact records `passed: false`, phase `backup-capture`, stage
`installed-local-hosting` and last stage `startup-error`. The private job log
additionally records the fixed diagnostic `category: database` and
`database_reason: timeout`, at these frozen-source locations:

| Module | Function | Recorded line |
| --- | --- | --- |
| [mnemion.local_workspace](https://github.com/Perseusxrltd/mnemion/blob/8a81ce68f0060cb06693cb44c0f381e907911cd6/mnemion/local_workspace.py#L714) | `dispatch` | 714 |
| [mnemion.local_backup](https://github.com/Perseusxrltd/mnemion/blob/8a81ce68f0060cb06693cb44c0f381e907911cd6/mnemion/local_backup.py#L524) | `dispatch` | 524 |
| [mnemion.local_backup](https://github.com/Perseusxrltd/mnemion/blob/8a81ce68f0060cb06693cb44c0f381e907911cd6/mnemion/local_backup.py#L250) | `capture` | 250 |

Identity checks had completed; opening the separate PostgreSQL connection for
the size estimate timed out **before snapshot creation began in this call**.
The original uploaded JSON omitted the backup diagnostic, which remains in the
preserved job log. No SQLSTATE was recorded. The evidence does not establish
the timeout's underlying cause, an engine crash or data loss. The artifact's
null app-child exit/signal fields do not establish that the app exited.

This is distinct from the earlier
[4.46.10 model-restart failure](2026-10-26-windows-host-restart.md), which occurred
later in `backup-resume` and recorded a database diagnostic with exit
`3221225477` (`0xC0000005`). That earlier failure retains its own unproven cause.

## Source refinement and checks

[Local backup admission](../../mnemion/local_backup.py) now reads tenant identity
and the database-size estimate through the same existing authenticated
connection. This reduces preflight TLS connections from **three to two**; it is
a source connection-count change, not a measured timing improvement or proof
that the original Windows cause is fixed.

The existing server-path, TLS-peer and native-process verification remains,
along with tenant identity checks, **five-second connection and statement
limits**, and disk-space admission before capture. Ledger-only capture skips
the size calculation. The
[installed smoke recorder](../../studio/electron/scripts/smoke-installed-hosting.mjs)
now retains a revalidated, classified `backupDiagnostic` in the failure artifact,
without publishing raw driver errors, credentials or private paths.

The [focused Python backup selection](../../service_tests/test_local_backup.py)
passed **10 tests in 26.28 seconds**, including real PostgreSQL identity/size
admission, ledger-only behavior and encrypted backup/recovery coverage. The
native process/TLS boundary in the new admission test is supplied by its fixture;
this does not constitute a fresh installed Windows check. The desktop local
backup and hosting-diagnostic selection passed **18 tests**, with zero failures
or skips, in **697.717325 ms**. The Electron build and Ruff check passed.

The original failed job and artifact remain preserved. The corrected candidate
still needs broader native, publication and installed backup/recovery
acceptance. All **66 requirement texts and states** remain unchanged; V08 stays
Building with production collection unavailable.

## Later fixture guard, 26 October 2026

A separate [source follow-up](2026-10-26-telemetry-sqlite-cleanup.md#windows-fixture-guard)
changes the installed Windows probe's pre-install guard to recognize
version-suffixed `Mnemion Studio` display names. A read-only registry observation
confirmed the installed name `Mnemion Studio 4.46.6`; the app was not started or
changed. This protects existing installations during future fixture execution.
It does not diagnose the backup timeout, constitute a new installed acceptance,
or change the already-frozen 4.46.12 candidate.

## SHA-256 provenance

| Retained evidence | SHA-256 |
| --- | --- |
| Original failure interpretation receipt | `b47ca4c0ee0a92114da3c73bffbc3e53bcca47c73be41a010b9b34c19898a8bd` |
| Original private job log | `7c9212ec17d7eaf59030b43f8e2e93810ab54a63807b4319018f20fc3605a814` |
| Original bounded artifact JSON | `358d05ba37c7a31727817a7765bf24fe81d7efe70f3eb34f9ce91989a71ef3ca` |
| Focused Python backup checks | `0c8af5df8e316a8270ee320b5672398ea4129bec1177655517b545b2f3d6349c` |
| Focused desktop backup/diagnostic checks | `6e4705278bc3255abd265cefe07a463dd0fac2f1a2fc02e1c526742f07e7e757` |
| Electron build | `79564d514f53d1df3388b9485184a597755d8307c86270f0b5435dcc90255ee6` |
