# Multiple workspaces, isolated access and complete agent operation

Requirement recorded on **2026-10-11** from the product owner's instructions.
This is a core implementation requirement, not a statement that the complete
feature is shipped. Version 4.0.9's saved workspace connections are a foundation;
they do not establish all the isolation, sharing and agent-parity guarantees below.

Source 4.28 adds [private desktop connection operations](../service/desktop-operator.md#select-a-team-workspace-from-a-local-agent)
with observed-selection revisions, expected person/tenant checks, protected
saved accounts and the existing draft/mutation guard. The app follows the chosen
identity after an agent switches it. [Focused and native acceptance](../validation/2026-10-20-desktop-workspace-control.md)
remain separate from the wider concurrent-session, context-isolation and
cross-workspace transfer contract below.

## Intended experience

One person can use personal, employer, client and project workspaces in the same
app. Some agents work only with a company, some only with personal memory, and
some are explicitly authorized for both. Joining and switching must remain
straightforward without combining permissions or mixing their information.

A workspace is an independently governed memory boundary, identified by a stable
workspace/tenant identity and its service endpoint. A space is a compartment
inside that boundary. Display names and URLs alone are not workspace identities:
different tenants can share a host, and different workspaces can share a name.

| Scenario | Required behavior |
| --- | --- |
| Personal and company membership | Both are available in one app, with independent identities, permissions, connections and settings. |
| Company-only agent | The agent can access only its assigned company workspaces and spaces. |
| Personal-only agent | The agent cannot discover company memory through another saved connection. |
| Agent authorized for both | Each operation selects an explicitly authorized workspace; credentials and execution context remain separate. |
| Several companies or clients | Each organization independently administers its own membership and policies. |
| A workspace is offline | Its connection status and recovery guidance remain visible; other workspaces remain usable. No operation silently moves to another workspace. |

## Identity and permission boundaries

- Maintain distinct memberships and credentials for each workspace. The same
  person or logical agent may have different roles in different organizations.
  Linking accounts for convenient navigation must not merge their authority.
- Company administrators control their organization's people, agents, devices,
  sessions, grants and revocations. This authority does not expose or administer
  an employee's personal workspace or another organization's workspace.
- Separate human sign-in, delegated agent access and host administration. An
  agent receives an identifiable, scoped credential rather than an owner's
  shared password or unrestricted administrator key.
- Enforce access on the server for every operation. UI selection, saved
  bookmarks, client-supplied workspace IDs and agent instructions are not grants.
- Recheck authorization when queued or scheduled work executes and when a
  connection resumes. Revocation must stop future access, with any session or
  cache propagation interval explicitly documented and tested.
- Joining links and invitation flows must identify the intended workspace and
  show the resulting identity and access. Never place long-lived credentials in
  shareable URLs or expose private membership details before authentication.

## Explicit operation targeting

Every save, search, import, export, evaluation, librarian task and background job
must bind to its originating workspace, acting identity and authorized spaces.
The app shows the active workspace and identity wherever a user can act.

Switching workspaces must not redirect an in-flight request, a draft, a queued
write, a retry or a scheduled task. Capture the target when work is created and
revalidate its authority before execution. Restore that same target after
restart or an automatic update; ask for reconnection when it is unavailable.
Never fall back to a different saved credential or workspace.

Search defaults to the selected workspace. Searching several workspaces requires
an explicit selection and authorization for each one, and labels every result
with its origin. The existing `all_accessible` search option must not become an
implicit search of every personal or company connection saved on the device.

## Isolation beyond database rows

Namespace and isolate credentials, sessions, request handles, UI drafts, query
caches, model context, retrieval results, vectors, citations, attachments,
Obsidian exports, evaluation data, notifications and background jobs. Include
workspace identity and the applicable access context in cache and artifact
boundaries. The same URL, document ID, space name or agent name must not cause a
collision between workspaces.

Keep agent context separate when changing workspace. A company conversation,
summary or cached tool result must not become context for a personal task merely
because the same agent handles both. Apply the same rule to librarian work,
recommendations and model-provider requests.

Give each workspace its own source mappings, model/egress policies, export
destinations, retention and audit controls. Workspace-specific deletion,
revocation, disconnect and forgetting must not alter another workspace's state.
An organization may have stricter policies than the user's personal defaults;
switching workspace cannot bypass them.

## Deliberate transfers and shared work

Authorization to read two workspaces does not itself authorize a transfer
between them. A server-mediated transfer must:

1. Identify the source, destination, acting identity and exact selected content.
2. Check source export/egress rules and destination write/import rules.
3. Show a preview and obtain any confirmation or approval required by policy.
4. Preserve provenance and record the transfer in each applicable audit trail
   without exposing unrelated private content or membership information.
5. Handle failure, retry and revocation without duplicating content or changing
   the destination. Revalidate permissions before committing the transfer.

These controls cover Mnemion's own operations. An external agent legitimately
given readable data from both workspaces can copy that data outside Mnemion;
dual membership alone cannot provide a data-loss-prevention guarantee. When a
company prohibits mixed context, use separately scoped agent sessions/workers
and enforce the relevant execution and egress policies. Document this boundary
instead of promising isolation that a shared external process can bypass.

## Every app workflow must be agent-operable

Every supported app workflow must have an equivalent documented, discoverable
API, CLI, MCP or typed local-operator operation. This includes initial setup,
workspace discovery and selection, invitations, membership and access changes,
agent/device management, configuration, diagnostics, backups and recovery.
Expose status and operation results so an agent can verify completion, safely
retry, and resume interrupted work.

People and agents use the same authorization rules and policy checks. Agent
operation does not mean bypassing required approvals, exposing arbitrary shell
execution, granting host administration to a memory key, or silently increasing
an agent's permissions. Where a provider or OS requires a human sign-in or
confirmation, provide a clear handoff and a resumable operation.

Keep API/CLI/MCP schemas and the app in parity. A workflow requiring an agent to
click through an otherwise undocumented screen is an implementation gap.

## Acceptance and regression evidence

Before declaring this requirement complete, record tests with at least one
personal workspace, two independent organizations and agents with single and
multiple memberships. Include two tenants on one service origin and repeated
display names and resource identifiers across independent deployments.

- Prove that unauthorized content and metadata cannot cross boundaries through
  search, citations, errors, caches, drafts, notifications, exports or model
  context. Include adversarial workspace/tenant ID substitution.
- Exercise concurrent windows and agents, delayed responses, workspace switching
  during writes, retries, queued work, restart and automatic updates. Every
  operation must retain its intended target and acting identity.
- Test membership/key/session revocation during active and queued work. Retained
  bookmarks, cached permissions and old handles must not restore revoked access.
- Test explicit multi-workspace search and permitted/denied transfers, including
  a source policy that forbids export despite the agent being a member of both.
- Verify that company administration cannot discover personal membership,
  credentials or memory, and that a personal agent cannot inherit company access.
- Verify that an unavailable workspace or expired credential does not interrupt
  unrelated connections or trigger fallback to another workspace.
- Run representative complete workflows through the app and through agent
  interfaces, using ordinary, delegated and administrator identities. Record
  parity gaps and required human/provider handoffs explicitly.
- Test supported Windows, macOS and Linux credential storage and lifecycle
  behavior, as well as browser sessions. Keep real-provider evidence separate
  from fixtures and do not describe planned controls as released functionality.

Related requirements: [complete app onboarding](app-onboarding.md),
[independent administrators and offline recovery](workspace-continuity.md),
[workspace connections](../service/workspaces.md),
[organizations and security](../service/organizations.md),
[agent administration](../service/agent-control.md), and
[the product roadmap](../ROADMAP.md).
