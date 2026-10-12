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

## Native finding and source correction

The [second focused ARM64 run](https://github.com/Perseusxrltd/mnemion/actions/runs/38201793754)
reached `tray-ready` and then stopped responding to the diagnostic HTTP probe.
The native sample contained `SecItemCopyMatching` and
`SecKeychainItemCopyContent`, with the OS SecurityAgent process present. No
database PID file or pre-migration backup existed at that observation. This
locates a Keychain wait during startup; raw trace data was not published.

The connection-status path called Electron's synchronous secure-storage
availability method. The source now uses the supported asynchronous macOS
provider, whose blocking Keychain work runs on a worker thread. Availability
has a two-second deadline; encryption/decryption has a fifteen-second deadline.
An outstanding native request stays coalesced after a UI timeout, preventing
retries from accumulating callbacks or plaintext encryption requests. A late
result cannot write a connection after the original operation has failed.

Saved-workspace storage awaits the actual availability boolean. A Promise is
never treated as permission to encrypt or decrypt. Destination/identity binding,
fresh server authorization and existing encrypted records are retained. The
connection screen displays locked bookmarks and **Retry secure storage**, and
does not attempt automatic saved-key authentication while the store is locked.

All **90** desktop unit checks passed, including six new asynchronous-provider
regressions and the existing connection, offline-recovery, update/relaunch and
local-host controls. The tests cover denied access, late completion, coalesced
pending work, unchanged old records and exclusion of provider error strings.
These are deterministic provider fixtures. Native Keychain behavior, installed
schema migration and real encrypted reconnection still require their separate
acceptance; the original 4.1.0 draft is not the corrected package.

At **04:23:10 UTC**, the built frontend passed a separate synthetic desktop-
bridge check at 1440 px and 390 px. Locked bookmarks stayed visible, automatic
saved-key resume was not called, and no storage-reset action appeared. Retrying
after the fixture unlocked enabled the existing connection without opening it
implicitly. An explicit Open reached the administrator landing page without a
memory-space grant. Both views were inspected visually, with no horizontal
overflow, browser errors or external network requests. The browser and its
disposable static server were closed afterward. This is UI evidence; it does
not substitute for native Keychain permission or real service authorization.
