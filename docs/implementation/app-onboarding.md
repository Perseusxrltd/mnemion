# Complete setup and operation through Studio

Acceptance requirement added on 2026-10-11: a person starting with a supported
clean computer must be able to install, configure, operate and recover Mnemion
through the app. A terminal command or an external setup guide is not the
completion path for a required onboarding step. Operating-system permissions
and provider sign-ins belong in the flow at the step that needs them.

The complete requirement remains in progress. Earlier 4.0.10 joins an existing
service; 4.0.11 adds the native local engine, PostgreSQL packaging and guided
workspace creation. Each release requires its complete installed-platform gates.
Use the [official product page](https://www.perseusxr.com/mnemion) for published
installers; source availability alone is not publication.

## Entry paths

1. **On this computer:** create a private workspace with a managed local database,
   service and worker. Install verified runtime packages, check disk/memory,
   generate restricted credentials, initialize one workspace and verify an
   indexed memory before declaring setup complete.
2. **Join a workspace:** validate the address and identity, explain available
   spaces and permissions, securely remember the connection when the operating
   system supports it, and reconnect after an update without asking for a key
   again. Never save credentials as plaintext browser storage.
3. **Set up an organization:** guide the operator through an owned local or remote
   host, database/storage selection, organization and compartment creation,
   administrators, members and scoped agent identities. Keep operator authority
   separate from ordinary organization access.
4. **Recover or move:** select a backup, verify it, show its contents and recovery
   limits, restore into a separate destination, reconcile deletion/access state,
   validate the result and switch the connection. Retain the previous workspace.

## Guided configuration

| Step | Required behavior |
| --- | --- |
| Location and resources | Recommended defaults, measured hardware/disk checks, an explicit data location and an explanation of where memory lives. Joining a team does not install a model on every device. |
| Workspace and access | Clear organization/space names, private initial access, role previews, scoped keys, invitations and revocation. Read-only source spaces and writable team memory are visibly distinct. |
| Sources | Pick local folders or connect Git, Drive, Slack, rclone/custom storage; acquire provider approval, preview mapped access, install/run the required source worker and show the first sync result. |
| Memory models | Choose a suitable local CPU or approved external profile, review download/egress requirements, prepare it and verify real retrieval. Keep advanced resource budgets available. |
| Librarian | Choose and test a local/cloud model, review its allowed changes, decide whether to enable schedules, and set budgets. Inspect proposals and undo from the same app. |
| Agents and programs | Create a scoped identity, select target assistants, configure the supported connection, test authenticated MCP/API access and show usable spaces. Hosted-agent OAuth and remote access are explicit dependencies. |
| Obsidian | Choose the visualization vault, preview the managed files, perform the first export and preserve personal annotations. Do not put a live database in a cloud-synced vault. |
| Background and updates | Show client and server versions separately, enable supported startup/background/update behavior, inspect checks and failures, pause/resume, apply a verified update and recover a failed start. |
| Backups and recovery | Set a destination and retention, create and verify a backup, explain what it covers, schedule it and rehearse recovery without replacing current data. |
| Readiness | Report the actual results for database/API/worker, model, selected sources, agent connection, backup and update checks. A running process alone is not a completed setup. |

Optional steps may be skipped deliberately and revisited from **Workspace setup**.
Failed required steps retain progress, explain the specific remedy and offer a
safe retry. Restarting the app must not create another organization, database or
key. Switching configuration preserves existing memories and prior working state.

Multi-workspace onboarding and operation must also satisfy the
[multiple-workspace isolation and agent-parity requirements](multiple-workspaces.md).
Personal and company memberships remain independent. Joining, switching,
concurrent work, sharing and recovery must preserve the selected workspace and
acting identity without carrying credentials or agent context across boundaries.

## Current gaps and implementation order

Source 4.30 adds [desktop database recovery from a server package](../service/desktop-host-recovery.md).
People and local agents can authenticate the complete package, review an included
or newer ledger, create a separate native database and select the verified copy.
Original organization/memory identities and current denials survive; fresh access
and separate provider/host configuration are explicit. This advances recovery
without claiming complete remote-provider reconstruction or in-place resume.

Source 4.28 gives trusted local agents the same key/password desktop connection,
saved-account, disconnect and local-selection paths through
[private desktop controls](../service/desktop-operator.md#select-a-team-workspace-from-a-local-agent).
Observed revisions, live identity checks, unsaved-work protection and the OS
credential store retain their app semantics. This advances agent setup while the
app is in the background; provider enrollment, complete host import and fleet
onboarding remain separate work. Native acceptance is required before publication.

Published 4.0.9 adds OS-protected saved desktop connections, verified
reconnection, durable disconnect and device-only forgetting. Local real-service,
UI and all six native encrypted-restart gates passed. This foundation does not
complete installation or host setup.

1. Published 4.0.11 and 4.0.12 provide first-run local/remote choices and a fixed,
   typed native operator bridge. Installed creation, real model save/search,
   shutdown, automatic reopen and occupied-port recovery passed on all six
   targets. [The 4.0.12 release and public update checks](../validation/2026-10-11-v412-release.md)
   are complete. Broader OS versions and managed-device policy still need testing.
2. Published installers bundle the Python service, CPU model drivers, PostgreSQL and
   vector extension. The pinned database builds passed on all supported host
   architectures, including explicitly disclosed Windows ARM compatibility.
   Combined installer and public update acceptance passed. Source-runner provisioning
   remains a separate app workflow; a bundled database does not finish it.
3. Host-only settings currently require environment files or CLI commands.
   Add authenticated operator workflows for model/provider approval, source
   runners, server lifecycle, update adoption, diagnostics and recovery.
4. Source 4.4.0 adds [guided local-host remote access](../service/remote-access.md),
   managed ngrok supervision, existing HTTPS proxy checks, public invitation
   addresses and the 4.3.0 hosted OAuth flow. The
   [real local TLS/controller walkthrough](../validation/2026-10-15-native-remote-access.md)
   covers configuration, restart and outage/recovery. Live provider acceptance,
   guided remote-host adoption and company SSO remain open.
5. Source 4.11.0 adds [company-provider setup in the app](../service/company-sign-in.md):
   the known local workspace, copied HTTPS callback, bounded OIDC discovery,
   client registration review, private client-secret handling, company CA bundles,
   session duration, provider removal/repair and local agent parity. A status
   read finishing after restart no longer causes a needless discovery retry.
   Organization-wide hosting, provider registration at the company, automatic
   provisioning, company-only policy and fleet/provider acceptance remain open.

Source 4.0.13 adds separate app/server version reporting and a fresh authenticated
server check in Setup, with explicit older-server and failed-check states. This
visibility does not complete managed host adoption or its recovery workflow.

A guide-only link, disabled “create workspace” button or successful mock response
does not close any of these gaps. Native runtime availability is a release gate;
do not substitute an obsolete database or bypass role separation to make a
platform appear supported. Docker Desktop cannot be a mandatory free-company
dependency. Existing databases and organization-hosted services remain options.

Published 4.0.11 protects startup, shutdown and RAM-policy writes from overlapping
with a desktop replacement. Shutdown waits for an existing policy write,
prevents a start that was waiting on inspection, and preserves control if the
engine does not finish within the shutdown deadline. A cancelled update reopens
only a workspace it actually stopped; an explicit user stop cancels that intent.
Agent changes refresh the policy revision shown in Studio without replacing
unsaved form edits. Address writes use the same lifecycle protection. The combined
desktop suite passed **66 tests** on 2026-10-11; these checks do not establish
packaged native hosting by themselves.
See the [integration report](../validation/2026-10-11-native-integration.md).

## RAM-policy recovery

Published 4.0.11 includes a fixed local operator `memory-repair`
command and matching app recovery controls on both the local welcome flow and
**Setup & this device**. Corrupt JSON no longer prevents status inspection.
Damaged or missing policies pause model admission, preserve the running
engine's previous budget, and block a new local start until an explicit repair.
Repair binds the observed damage to a token, preserves its private bytes, and
refuses stale or already-valid replacements. The desktop serializes repairs
with shutdown and updates. Read [RAM recovery](../service/memory-resources.md)
for agent examples and the explicit unsafe-storage/256 KiB boundary.

This closes recovery for an ordinary damaged local RAM-policy record. Complete
packaged installation/model checks also passed in the release gates; backup
restoration and moving the local data folder remain separate work.

## Local address recovery

Published 4.0.11 adds an app recovery screen and a typed local operator `port`
command for a stopped workspace whose API port is occupied. Automatic or explicit
port selection retains its identity, credentials, memories, models and RAM
policy. An external agent's change requires refresh before saving a stale form;
a saved repair requires explicit Resume. See [the app and agent procedure](../service/local-workspaces.md)
and [validation scope](../validation/2026-10-11-local-address-recovery.md).
This does not change the private database port or configure remote exposure.

## Release evidence

Run clean-install walkthroughs on Windows, macOS and Linux, x64 and ARM64. Record
the actual runtime architecture, including any explicitly disclosed emulation.
Verify setup, restart/reconnection, update, interruption/resume, permissions,
source removal, backup and recovery with real processes and scoped credentials.
Test narrow layouts, keyboard focus, progress/error announcements and offline
help. Keep fixtures separate from live-provider and hardware evidence.

Every required operation must retain API/CLI/MCP or a documented local operator
equivalent so agents can also handle it end to end. Ordinary memory credentials
must never acquire host administration merely by opening the setup screen.
