# macOS installed-upgrade Keychain diagnosis

Recorded **2026-10-12**. Resolved in published **4.1.0**, source `4b5df29`.
Both macOS architectures passed the complete installed upgrade, restoration
and final exit. The investigation below preserves the earlier failed candidates;
the final acceptance is recorded at the end.

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

## Installed migration and remaining exit failure

Candidate `cbea13f` passed its full release build and independent native gates.
The [six installed-upgrade executions](https://github.com/Perseusxrltd/mnemion/actions/runs/38206660021)
passed on Windows x64/ARM64 and Linux x64/ARM64. Both Macs passed startup,
schema migration, scoped withdrawal and isolated backup restoration, then
exceeded the final 120-second exit deadline. Their diagnostic markers were
`hosting-ready`; no database PID file remained. Native samples still showed
Keychain calls and SecurityAgent. This is an exit failure after the database
drained, rather than the earlier blocked startup.

The next correction runs the same Electron safeStorage APIs in a dedicated
process with the installed application's identity and a private temporary
profile. Its bounded pipes accept only availability, encryption and decryption.
Credentials never appear in arguments, environment variables or logs, and it
cannot write saved connections, start a service or access a workspace database.
The parent retains coalesced two-/fifteen-second deadlines and existing record
validation. A denied provider is discarded so a later retry can observe an
unlocked store. The helper's reported memory, with a conservative startup
reservation, is included in desktop RAM accounting.

Final `will-quit` terminates only the disposable credential helper. The existing
cancellable database/update shutdown path finishes first; no database process
is forcibly stopped. The helper also exits if its private parent pipe closes.
All **102** desktop checks passed, including twelve helper subprocess checks.
These cover blocked consent, process reuse/reaping, denied access,
protocol bounds, lost pipes, provider-error privacy and late results that must
not write a saved connection. At this source checkpoint, native installed Mac
acceptance remained required before publishing the corrected packages.

## Final installed acceptance and publication

Source `4b5df29131566e26b802ca8e4ef3fa77f06fc57e` passed the complete
[release build](https://github.com/Perseusxrltd/mnemion/actions/runs/38208553562)
and independent native checks. The [installed upgrade and recovery matrix](https://github.com/Perseusxrltd/mnemion/actions/runs/38211935149)
passed all six targets. Mac ARM64 completed at **06:21:04 UTC** and Mac x64 at
**06:22:49 UTC**. Each used the real 4.0.14 installer/model and final 4.1.0
installer, migrated the existing local workspace from schema 13 to 14, preserved
its access and memories, withdrew a contributor's note, restored the verified
backup with the current ledger and exited cleanly. The former final-exit failure
did not recur. These checks retained the production shutdown and permission paths.

The independently verified final packages were [published at 06:45:13 UTC](2026-10-12-v410-release.md).
An OS-locked Keychain can still require its normal unlock/approval. The app keeps
that state visible and offers retry or a temporary connection; publication does
not imply that OS consent can be bypassed.
