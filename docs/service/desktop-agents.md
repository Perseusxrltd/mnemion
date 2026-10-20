# Install an agent connection from Studio

Published **4.32.0** adds **Agents → Connect an agent on this computer**.
[Release status](../RELEASE_STATUS.md) identifies published versions and native
acceptance; a source version alone does not mean its installers are available.

1. Connect to the intended workspace. In **People & apps**, create a dedicated
   application and grant the spaces it should use. Keep administrator identities
   separate from background application keys.
2. Open **Agents** and choose its client profile and application. Studio supplies
   the current OS's configuration path. Choose another file for a custom profile.
   Use a distinct connection name for each workspace, such as `mnemion-office`.
3. Review the generated entry and target file. An administrator may leave the key
   blank to issue a new dedicated key at installation. Other users supply their
   assigned application's ID and key.
4. Close the target agent, confirm its permissions and approve installation.
   Replacing an existing entry of the same name requires a separate confirmation.
   Changed files invalidate an old preview. Other servers and policy settings
   remain, and the previous complete settings receive a private backup.
5. Reopen the agent and verify its memory tools. Configuration being installed
   does not prove that the agent has loaded the connection. Tool calls enforce
   the application's current workspace permissions.

The configuration invokes a private copy of the included standalone Mnemion
engine. It needs no separate Python installation and can connect while Studio
is closed, provided the workspace is running and reachable. Agent setup does
not enable conversation capture; choose capture sources separately in
**Connections**.

## Runtime updates and portable installations

Studio copies its bundled engine after checking each file against the packaged
inventory. Copies contain no model weights and require at most 768 MiB each.
The launcher stays outside the application bundle, so closing a Linux AppImage
does not remove its command and a running Windows agent does not lock Studio's
installed engine during an app update.

On startup and every five minutes while running, Studio refreshes the private
runtime from its own installed version. New agent sessions use that version.
Existing sessions retain their immutable engine files until they finish; reopen
the agent to load a hotfix immediately. No client configuration rewrite is needed.
Old inactive copies are reclaimed automatically. Interrupted copies are removed
on retry; a failed copy retains the previous working pointer and an attention
message appears in the app. Installation and copying have bounded deadlines and
block an app restart while in progress.

Windows uses its included PowerShell with a process-only `RemoteSigned` policy
and a byte-preserving pipe launcher. It does not change the machine's execution
policy. A company-enforced policy can still prohibit this local launcher; use
the supported company MCP setup in that case. Unix uses the system shell.

## Credential custody and removal

Each installation has its own directory and application credentials file,
restricted to the current OS account. Windows uses explicit private ownership
and DACLs. Agent configuration includes only that file's path. Unlike saved
Studio login/source keys, these standalone credentials are not OS-keychain
encrypted; the agent must be able to read them independently of Studio. Use a
dedicated application with appropriate grants and revoke its key if the device
is lost. Do not put these files in a shared repository or unencrypted backup.

**Agent connections on this computer** is available in setup and before signing
in. Its status is derived from the actual agent file. Removal deletes the
matching entry and this installation's private key file. A differently edited
entry is preserved. Manually copied configurations referencing the removed file
will stop working. Server keys are not silently revoked; an administrator can
revoke unused keys in **People & apps**. Other devices retain their own setup.

The app does not overwrite invalid or duplicate-key settings, unsupported JSON
comments or linked files. From 4.38, Hermes YAML retains comments and quotes;
OpenClaw JSON5 accepts comments and is saved as ordinary JSON with an exact
private backup. Editing a YAML alias does not change other settings sharing it.
Use the agent's own supported configuration editor to resolve such a file, then
review a new preview. Completed or interrupted setup remains inspectable; a lost
response is not a reason to blindly replay an old settings revision.

## Profiles and boundaries

Profiles cover Codex, Grok Build, Claude Code/Desktop, Cursor, Gemini CLI, Zed,
Devin Desktop, legacy Windsurf and an explicit generic MCP file. From 4.38,
Hermes uses `mcp_servers` in its active YAML profile; OpenClaw uses nested
`mcp.servers` in JSON/JSON5. Hermes honors `HERMES_HOME`; OpenClaw honors
`OPENCLAW_CONFIG_PATH`, `OPENCLAW_STATE_DIR`, `OPENCLAW_HOME` and named
`OPENCLAW_PROFILE` defaults. Choose an explicit file for a profile selected
inside a different running client. Grok Build's
TOML profile is based on the installed native CLI's `mcp add --help` and current
configuration contract. Its support is distinct from a Grokbot plugin or hosted
Grok service. [Perseus XR packages](agent-packages.md) supply supported plugin,
native OAuth configuration or connection-guide formats. Actual cloud/provider
acceptance and catalog publication remain separate work.
Hosted ChatGPT uses the [OAuth flow](hosted-agent-sign-in.md), not this local
file installer.

WSL and Windows use separate profiles. Run setup where the agent runs. A client
must support the selected local stdio MCP format; this does not install the
agent itself or claim support on operating systems its vendor does not support.
Packaged application updates retain the private launcher location. Uninstalling
Studio leaves existing private agent copies without further refresh; remove
their installations or revoke their keys when decommissioning the computer.
Source/development builds may directly invoke their configured engine and do not
claim the portable packaged-runtime behavior.

## Private agent controls

The owning OS account's [desktop interface](desktop-operator.md) exposes
`agent.status`, `agent.preview`, `agent.install` and `agent.remove` without
requiring a local database. Read the catalog for the accepted input fields.
Preview returns the exact setup, generated entry and configuration hash; install
must supply those same values, the dedicated key and explicit confirmation.
Removal requires the current observed configuration hash and confirmation.
Credentials travel through private stdin, never command-line arguments.

The standalone `mnemion-agent` command retains preview/apply/remove behavior,
adds `--server-name` for independent named connections, and accepts `--standalone`
when `--python` points to the packaged engine rather than a Python interpreter.
