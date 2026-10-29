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
open starts `process.execPath` with `--mnemion-keychain-helper`. While that
child stays healthy, later seals and opens reuse it until final `will-quit`.
An unavailable result, denial, timeout, or pipe failure discards the child, and
the next call can start another. Electron 44.9.3 requests the async
`safeStorage` encryptor once per process
(`EnsureAsyncEncryptorRequested`); later `encryptStringAsync` /
`decryptStringAsync` calls in that process use that in-memory key. Chromium's
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
Allow** (trust this app from then on). After successful access, a healthy
running helper reuses its encryptor, so later connections in that run do not
each prompt. Allow asks again on the next launch. A helper restart, a failed
approval, a locked keychain, or a changed OS access policy can require another
prompt. Always Allow normally permits the unchanged binary while that
permission remains valid. The next update or re-sign changes the cdhash, so
that exact-binary trust does not carry over. The free signing policy does not
add a Team ID. This implementation's current ad-hoc app identity changes across
builds and does not preserve that exact-binary trust. This batch adds no
cross-update credential migration.

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

## Handoff follow-up, 30 October 2026

Astra reviewed `6b825566d00c997af9fb3b7f2d6e3a9c205fd963`. The focused
two-connection regression and comment-only source changes are accepted. The
original 19-test pass stays valid and was not rerun for this copy correction.
The sections above keep the 29 October report, source notes, and open
acceptance list. Item 2 is the healthy-helper case: a replaced helper can
prompt again in that same launch.

The once-per-launch wording is the normal case only. After successful access, a
healthy running helper reuses its encryptor. CredentialProcess can discard and
replace the child after an unavailable result, denial, timeout, or pipe
failure. A helper restart, failed approval, locked keychain, or changed OS
access policy can require another prompt. Always Allow normally permits the
unchanged binary while that permission remains valid. Allow versus Always
Allow, and the expected prompt on the next update, remain as written above.

The withdrawn claim is that no code change can ever preserve approval across a
new cdhash. This implementation's current ad-hoc app identity changes across
builds and does not preserve that exact-binary trust. This batch adds no
cross-update credential migration. The persistent helper is current behavior;
this note does not date that lifetime to 4.1.0.

Issue 50 stays open. Normal-helper source and 19 fixture checks are the
evidence linked from the issue plan. Actual affected-Mac acceptance is still
open. No Mac keychain was unlocked, no installed Studio was modified, and no
version was bumped.
