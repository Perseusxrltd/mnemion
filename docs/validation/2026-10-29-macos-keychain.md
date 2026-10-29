# macOS login-keychain prompts for one Studio identity

Recorded 29 October 2026 against source `02de57f6def7646aaf08df516f7de7b683937baf`
for [issue 50](https://github.com/Perseusxrltd/mnemion/issues/50). No version
bump. Issue 50 stays open. No Mac keychain was unlocked and no installed Studio
was modified.

## What the report shows

Studio 4.46.49 on macOS 27.2 asks for the login-keychain password for the
existing item `mnemion-studio Safe Storage` / `mnemion-studio Key`. The login
keychain was already unlocked. `security dump-keychain -a` shows trusted
ad-hoc cdhashes from earlier signatures, not a Team ID. The installed file's
designated requirement was a different cdhash (`Signature=adhoc`,
`TeamIdentifier=not set`). A local re-sign that got past the issue 49 launch
failure created yet another cdhash, and the dialog returned.

## What this source already does

`workspaceCipher()` on macOS returns one `CredentialProcess`. The first seal or
open starts `process.execPath` with `--mnemion-keychain-helper`. Later seals
and opens reuse that process until final `will-quit`. Electron 44.9.3 requests
the async `safeStorage` encryptor once per process
(`EnsureAsyncEncryptorRequested`); later `encryptStringAsync` /
`decryptStringAsync` calls use that in-memory key. Chromium's
`KeychainPassword::GetPassword()` itself calls the keychain on every lookup, so
a new process is a new lookup. The helper is the same executable as Studio, so
it is not a second keychain identity.

A focused store test seals two saved connections, opens both, and requires one
helper process. The existing helper tests still cover consent that never
answers, denial, cleanup, and a late result that must not rewrite a saved
connection. Those checks do not open a real login keychain.

## What cannot be promised

[Electron's safeStorage documentation](https://www.electronjs.org/docs/latest/api/safe-storage)
says that without a consistent signature, macOS may prompt again on every
update. Electron maintainers closed the same report as not a bug in
[electron/electron#43233](https://github.com/electron/electron/issues/43233):
the access list is the designated requirement, which for a Developer ID signature
is the bundle id plus Team ID, and for this ad-hoc build is the cdhash.

[Apple's keychain prompt](https://support.apple.com/guide/keychain-access/if-youre-asked-for-access-to-your-keychain-kyca1243/mac)
distinguishes **Allow** / **Allow Once** (this retrieval only) from **Always
Allow** (trust this app from then on). Allow therefore covers every saved
connection in the running helper and asks again on the next launch. Always
Allow covers later launches of that same binary only. The next update or
re-sign changes the cdhash, so Always Allow does not carry over. The free
signing policy does not add a Team ID. No code change can make one approval
survive that new cdhash.

## Acceptance still open

1. On the reporter's Mac, one Always Allow for an unchanged published build
   must cover opening a saved connection, sealing another, restarting that same
   build, and the helper.
2. Allow Once must ask again on the next launch and must not ask for a second
   connection in the same launch.
3. Installing the next published build must ask once for the new cdhash, then
   stay quiet for that build after Always Allow.
4. Saved ciphertext from the previous build must still open. Nothing here
   replaces it.
