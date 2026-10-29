# Connect and remember a workspace

Open Mnemion and choose **Join a workspace**. With service and Studio 4.2.0,
use an [individual login or invitation](sign-in.md); a scoped workspace key is
also available for existing deployments and applications. Mnemion checks the
service and your identity before opening its memory spaces. A remote workspace needs HTTPS; local services can
use a loopback address such as `http://127.0.0.1:7892`.

The address is the service's base address. Leave `/v1`, `/mcp` and individual
API routes off the end. An organization can provide a base path, for example
`https://memory.example.com/team`; desktop requests stay within that API path.
Do not put a key in an address or share a key in public messages.

## Remember a connection using a key

From desktop version 4.0.9, **Remember this workspace on this device** saves an
encrypted connection using Windows protection, the macOS Keychain, or a
supported Linux keyring. Mnemion rechecks your identity and reconnects after an
app restart. No embedding or language model is installed just to join a team.
The main process holds the real key; the interface receives a temporary handle
that can only call the selected workspace API.

On Windows, protection is bound to your Windows account. The bundled local
helper calls the operating system directly so an unexpected shutdown cannot lose
a newly saved profile key. Keys never enter command-line arguments or temporary
plaintext files. This does not protect against another program already running
with your Windows account's privileges.

Leave the option unchecked on a shared device or for a temporary connection.
If the operating system's secure store is locked or unavailable, the app
explains this and offers a session-only connection. There is no plaintext key
fallback. Unlock the OS store before opening a previously saved workspace.

On macOS, credential checks use the asynchronous Keychain API in one helper
process of the same Studio executable. After successful access, a healthy
running helper reuses its encryptor, so later saved connections in that run do
not each prompt. A helper restart, a failed approval, a locked keychain, or a
changed OS access policy can require another prompt. The helper is not a
second app and does not have its own keychain identity. A prompt must not
freeze the window or prevent the local workspace from starting.

The dialog is macOS asking whether this copy of Studio may read the existing
item `mnemion-studio Safe Storage`. It is not a Mnemion workspace password and
not an Apple ID password. It can appear while the login keychain is already
unlocked. Existing encrypted bookmarks stay as they are. Resetting saved
connections is not required.

**Allow** (shown on some macOS versions as **Allow Once**) permits that
retrieval. After successful access, a healthy running helper reuses its
encryptor, so later connections in that same run do not ask. The next launch
is a new process and asks again. A helper restart or a failed approval can ask
again before quit.

**Always Allow** normally permits the unchanged binary while that permission
remains valid. This free build has no Apple Team ID. The requirement is the
ad-hoc code-directory hash (cdhash) of that binary. The same unchanged Studio,
including a healthy helper, can then launch and use saved connections without
asking again. A locked keychain or a changed OS access policy can still
require a prompt.

The next Studio update, or any local re-sign, produces a new cdhash. macOS
treats that file as a different app, so **Always Allow does not carry over**.
The new build asks once. **Always Allow** on that build then covers it until
the following update, while that permission remains valid. This app's current
ad-hoc identity changes across builds and does not preserve that exact-binary
trust. This batch adds no cross-update credential migration. Do not locally
re-sign Studio to silence the dialog. That creates another cdhash and the
dialog returns. After the prompt, choose
**Retry secure storage** and **Open** beside the saved connection. If you chose
**Deny**, quit Studio and open it again, then approve the prompt.

The connection list shows each workspace, address and identity. Select **Open**
to reconnect. **Disconnect** immediately clears the active connection and pauses
automatic reconnection, including on the next launch. The encrypted bookmark
remains available for an explicit **Open**. **Forget** removes that bookmark
from this device after an in-app confirmation; it does not delete memories or
revoke the server key. An administrator can revoke that key in **People & apps**.

Browser Studio keeps the key in the current window's memory. Reloading or
disconnecting clears it. Both clients may remember the service address locally.
Desktop session-only connections last until disconnect or app exit; reloading
the interface alone does not exit the desktop app.

Personal password sessions have separate sign-out, expiry and revocation
behavior. See [remembering a login and managing sessions](sign-in.md#sign-in-and-remember-a-device).

From desktop 4.28, a trusted agent on this computer can perform the same key or
password connection, saved-account inspection, reopening, disconnect and
forgetting through [private desktop controls](desktop-operator.md#select-a-team-workspace-from-a-local-agent).
It confirms the current selection and intended identity, retains OS-protected
storage and refuses to discard unsaved work. This can operate while the app is
in the background; a workspace API key alone does not grant these local controls.

## If a connection fails

- Check the address and that the service is running. A client update does not
  install a missing server.
- An expired or revoked key needs a current key from your administrator. A saved
  key that now identifies a different person or workspace is not resumed.
- A locked keyring needs to be unlocked in the operating system. In 4.1.0, use
  **Retry secure storage** after unlocking it. Connect without remembering the
  workspace if secure storage is unavailable.
- During automatic reconnection, choose **Use another workspace** to stop it and
  enter another address. A delayed response cannot undo that choice.
- Saved connection data that is corrupt, linked elsewhere or unsafe to read is
  rejected. Mnemion does not overwrite it with a new connection automatically.
  Use **Reset saved connections**, then confirm **Forget all and reset** to
  clear damaged device bookmarks and reconnect. This leaves server memories
  intact and requires current keys. The reset can repair the app's own file
  permissions; it refuses links or files owned by another OS account.

## Creating a new installation

The complete desktop installers include a local database and the model/runtime
setup introduced in 4.0.11. Choose **Create on this computer**, review the model
and RAM allowance, and open the new private workspace. See
[local workspaces](local-workspaces.md). Source-provider sign-in, company-host
onboarding and complete guided host recovery remain in the
[app-setup acceptance requirements](../implementation/app-onboarding.md).
Operator installation is described in the
[service guide](README.md) and [deployment guide](deployment.md).

Device encryption protects the saved key, not exported memory. Obsidian exports
remain ordinary Markdown. See [privacy and data handling](privacy.md).
