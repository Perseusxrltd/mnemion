# macOS installed-upgrade startup diagnosis

Recorded **2026-10-12**. This is unresolved acceptance for the unpublished
4.1.0 candidate; 4.0.14 remains the published release.

Both macOS targets timed out when reopening the preceding install's workspace.
The [focused ARM64 run](https://github.com/Perseusxrltd/mnemion/actions/runs/38200421201)
also timed out. Its bounded status probe was unavailable; no database PID file
or pre-migration archive existed at the observation. This does not establish
whether the app, its credential provider or the diagnostic connection blocked.

The next diagnostic distinguishes HTTP, page discovery, debugger connection and
IPC completion. On an isolated macOS CI host it can sample the already launched
app, exporting only a fixed allowlist of OS/function names and whether the OS
security-agent process was present. Raw samples, paths, arguments, credentials,
profiles and backups remain private on the disposable runner. The existing
startup marker is retained, including the tray-ready state.

All **25** inventory, execution-boundary and diagnostic-privacy checks passed.
The real native rerun remains required. Initial model setup retains its twelve-
minute allowance; reopening this small, already indexed synthetic fixture has a
five-minute deadline. This changes no production startup or migration timeout.
