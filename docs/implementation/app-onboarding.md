# Complete setup and operation through Studio

Acceptance requirement added on 2026-10-11: a person starting with a supported
clean computer must be able to install, configure, operate and recover Mnemion
through the app. A terminal command or an external setup guide is not the
completion path for a required onboarding step. Operating-system permissions
and provider sign-ins belong in the flow at the step that needs them.

This is work in progress. The published client currently joins an existing
service and does not provision its database or server runtime.

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

Published 4.0.9 adds OS-protected saved desktop connections, verified
reconnection, durable disconnect and device-only forgetting. Local real-service,
UI and all six native encrypted-restart gates passed. This foundation does not
complete installation or host setup.

1. The connection screen assumes an administrator has already installed a server.
   Build the complete first-run navigation and a native operator bridge with
   fixed, typed operations rather than arbitrary shell execution.
2. PostgreSQL, Python and source runners need manual installation. Build and
   validate signed native runtime packages, including the database's vector
   extension, and make staging resumable with bounded resources. The
   [native database foundation](native-local-runtime.md) now has a source-pinned
   builder and a passing local Linux runtime probe; the complete platform
   matrix, signed installer integration and portable service remain required.
3. Host-only settings currently require environment files or CLI commands.
   Add authenticated operator workflows for model/provider approval, source
   runners, server lifecycle, update adoption, diagnostics and recovery.
4. Remote sharing and hosted OAuth remain open roadmap work. Expose only tested
   connection methods and finish their identity, consent and revocation flows.

A guide-only link, disabled “create workspace” button or successful mock response
does not close any of these gaps. Native runtime availability is a release gate;
do not substitute an obsolete database or bypass role separation to make a
platform appear supported. Docker Desktop cannot be a mandatory free-company
dependency. Existing databases and organization-hosted services remain options.

The native-host branch now protects startup, shutdown and RAM-policy writes from
overlapping with a desktop replacement. Shutdown waits for an existing policy
write, prevents a start that was waiting on inspection, and preserves control if
the engine does not finish within the shutdown deadline. Agent changes refresh
the policy revision shown in Studio without replacing unsaved form edits. Five
focused lifecycle regressions and the existing desktop suite pass locally
(52 tests, 2026-10-11); these checks do not establish packaged native hosting on
Windows or macOS, which remains a release prerequisite.

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
