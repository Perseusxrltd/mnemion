# Set up and operate Mnemion with an agent

Mnemion's setup uses native commands and discoverable operations. A trusted
local agent can configure the app through its private OS-account interface;
an authenticated remote agent manages the shared workspace through HTTP, MCP
or the SDKs. Their authority is separate.

## Start with discovery

Install and start the published app for the computer's OS and architecture.
Use **Setup & this device → Agents on this computer → Copy local agent setup**
to obtain its installed executable and discovery requests. This contains no
credentials. A source installation exposes the same interface as:

```sh
mnemion-service desktop-control
```

Pass a JSON request on stdin, beginning with `{"action":"catalog"}`, then
`{"action":"status"}` and `{"action":"workspace.status"}`. The catalog is
the installed version's authority for operations, fields and sensitive results.
Use an argument array, not an interpolated shell command. A WSL agent managing
the Windows app invokes the Windows engine from the copied configuration.

For a service without Studio, follow the native [deployment](deployment.md),
[host operator](host-recovery.md) and [supervision](supervision.md) commands.
The desktop interface requires Studio to be running; the independently managed
service and installed agent launcher do not require a Studio window.

## Supported setup surfaces

| Setup task | Native agent entry point |
| --- | --- |
| Create and run a local workspace | `local.create`, `local.start`, `local.stop`, `local.open` |
| Join a team as the intended person or application | `workspace.verify`, `workspace.sign-in`, `workspace.connect`, `workspace.restore` |
| People, invitations, applications, spaces and current grants | Discover the [workspace administration catalog](agent-control.md) through `mnemion` or `mnemion-control` |
| RAM and local lifecycle settings | `local.memory`, `local.port`, `local.preferences`, `app.preferences` |
| Public HTTPS access and hosted-agent sign-in | `local.remote`, `local.remote-check`; independent-host configuration in the [OAuth guide](hosted-agent-sign-in.md) |
| Company sign-in | `local.company-discover`, `local.company`, plus the workspace's company-access operations |
| Embeddings and librarian models | `local.models`, followed by the selected spaces' processing permissions |
| Folder, Obsidian, conversation, Slack and Drive sources | `source.status`, `source.configure`, `source.pause`, `source.sync`, `source.remove` |
| Install supported local MCP clients | `agent.status`, `agent.preview`, `agent.install`, `agent.remove`; independent [mnemion-agent setup](agents.md) |
| Export a named agent connection package | `agents.package` in the authenticated catalog, or standalone `mnemion-service agent-package`; [formats and publisher](agent-packages.md) |
| Git journals and source delivery | `local.journal` plus the workspace's journal/publication operations |
| Encrypted vault and recovery keys | `local.vault`, `local.vault-key`, `backup.key`, with private result files for sensitive material |
| Backup, inspect, restore and select a recovered workspace | `backup.*`, `recovery.list`, `recovery.use`, or the independent host CLI |
| Update policy, immediate check and guarded relaunch | `app.status`, `app.preferences`, `app.update-check`, `app.update-restart`; managed-service update commands |

The [desktop operator guide](desktop-operator.md) defines input fields and
version requirements. Inspect the current workspace ID, selection revision and
relevant settings revision before a mutation. Submit the observed confirmation
values; refresh after a conflict instead of overriding it. Setup requests use
the same draft, permission, identity, RAM and restart checks as the app.

Keep credentials on private stdin or in protected files and use private result
files when a command returns a new secret. A memory key does not grant local OS,
cloud-provider or host-operator access. Choose dedicated application principals
and only the needed spaces for ordinary assistants.

## Required coverage and remaining work

Every new setup/configuration workflow must include a discoverable native
operation with structured input/output, a clear privilege boundary, safe
conflict/retry behavior and an app equivalent where relevant. Screen automation
is a way to test a third-party client; it is not Mnemion's native setup API.

The full F08 requirement remains partial. Complete provider/host provisioning,
delegated recovery and named-client onboarding still need implementation and
actual acceptance. Cloud account authentication, provider consent, MFA and
administrator policy remain controlled by those providers; the native workflow
must surface their required handoff and resume clearly.

Named integration work includes **Grok/Grokbot, Claude, Hermes, OpenClaw,
OpenAI/ChatGPT/Codex and Dot**. Existing Grok Build TOML support is separate from
Grokbot. The [requirements](../PRODUCT_REQUIREMENTS.md) track each platform's
configuration, capture and acceptance gaps. All connector/app/plugin packages
use [Perseus XR authorship](../BRANDING.md#connector-and-plugin-authorship).
