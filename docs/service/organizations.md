# Organization deployment and vault security

Mnemion separates the organization, authenticated identity, memory space, source
connection and subject described by a memory. A memory about a person does not
authenticate as that person. One deployment can serve multiple organizations;
PostgreSQL row-level policy enforces tenant and space boundaries.

Start with one organization and create separate spaces for departments, projects,
client engagements and personal work. Grant each employee and integration its own
identity and either personal sign-in or a revocable application key. Reader, contributor and reviewer space grants, plus
organization administrator authority, control each operation; searching multiple
spaces still checks every requested space. Use a shared project space only for
knowledge that all its members may read.

Use **Team and applications** in Studio to manage principals, credentials and
grants. API and worker database logins have separate restricted roles; the schema
owner is only for setup, migration and recovery. Do not give assistants an owner
key merely to simplify configuration. MCP HTTP calls retain each caller's identity.

From 4.0.13, **Setup & this device** shows separate app and authenticated service
versions. Members can refresh the server observation without receiving host
privileges. Organization administration, explicit space grants and the host's
operator account remain separate authorities; see the [update guide](updates.md).

Service 4.1.0 adds [scoped author withdrawal](withdrawal.md): contributors can
withdraw their own ordinary, unverified memories only when nobody else has
revised them. It does not grant access to reviewer-only content or permit an
agent to delete another author's work. This change requires the checked service
migration; an earlier shared server retains its earlier permission contract.

## Establish independent administrators

Version 4.0.11 exposes **Organization role** in **People & apps** and lists
organization identities separately from space grants. An authenticated
administrator can open People & apps, Connections, Setup and documentation even
without a memory-space grant. Administration no longer requires creating a
private space merely to get past the welcome screen.
From 4.8.0, the same access rule includes the [Recovery directory](recovery-directory.md).

1. Open **People & apps**, enter the person's name, choose **Person**, then
   explicitly choose **Organization administrator**. The default is an ordinary
   member, including for assistants. Review the authority and select
   **Create administrator**.
2. Create that person's individual key. The app selects the new identity in the
   key form; preserve the displayed key privately and give it only to that person.
   Do not distribute the original administrator's key. With service and Studio
   4.2.0, use a [private invitation](sign-in.md) so the person can choose their
   own password. Keep an independently held recovery key and host access.
3. Verify a fresh connection using the new key, preferably from another device.
   Confirm that People & apps is available before retiring the original agent or
   credentials. An active identity in the roster alone does not prove sign-in.
4. In **Memory space to administer**, explicitly select the compartment and
   grant only the required role. Organization administrators can manage grants
   without reading that compartment's contents; they can explicitly grant access
   under the organization's policy. New administrators receive no content grant
   automatically. Source-managed compartments retain their connector policy.

Trusted administration agents can receive administrator authority through the
same explicit choice. Other agents should retain their assigned space roles.
The existing `principals.create` API/CLI/MCP operation accepts
`{"name":"Second administrator","kind":"human","administrator":true}`;
`keys.create` writes the new secret to a private result file. See
[agent controls](agent-control.md). Non-administrators cannot use that flag to
promote themselves, and an organization's admin cannot issue another tenant's
keys.

This establishes independent **workspace administration while the service is
reachable**. Starting an offline computer, repairing its tunnel and restoring a
database still require independently held host/operator access. Keep a verified
backup and current recovery ledger outside that host. Version 4.0.11 includes
[offline saved-workspace details](../validation/2026-10-11-offline-workspace-details.md).
Version 4.8.0 adds [shared host/recovery references, protected desktop copies and
an independent encrypted kit](recovery-directory.md). These preserve the
information needed to reach separately authorized operators when the service is
unavailable. Delegated host actions and complete independent recovery remain
under the [continuity requirements](../implementation/workspace-continuity.md);
a Git source mirror is not a complete database backup or proof of current
workspace authority. The [actual Windows administration and test-lab report](../validation/2026-10-12-workspace-administration.md)
records a separate human join/reopen and explicitly mapped Git reader access.

### Retire an identity and retain administrator access

Version 4.0.11 adds **Disable** beside other active identities in People &
apps. Review the named confirmation before disabling a person or application.
Its API keys and linked sign-ins stop granting access; recorded memories and
history remain. Disabling is permanent through the application: future access
requires a new identity with explicit grants. You cannot disable your own
identity in that session. Use another independently enrolled administrator.
The existing `principals.disable` API/CLI/MCP operation and TypeScript
`disablePrincipal(id)` provide equivalent controls.

The same release protects removal of the last currently usable organization
administrator credential. A rejected operation returns HTTP `409` with
`last_administrator_access`; create and verify replacement access first. A bare
administrator identity with no key, a disabled identity, and an expired or
revoked key do not provide a fallback. Key rotation and repeated revocation of
an already revoked key remain supported. API-key and OAuth-binding revocation
share a tenant-level database lock, so concurrent requests cannot each remove
the other's fallback. Authority and real-time expiry are rechecked after waiting.

This check establishes current database authorization. It does not prove that
somebody has retained the other key, that a configured OAuth issuer is online,
or that a future expiry will be renewed. Keep independently held human access
and a protected recovery key, test them before retiring an agent, and monitor
expiry. A host/database operator can still carry out emergency recovery or
revocation through the existing operator procedures. These application controls
do not invent host privileges, bypass an offline server, or grant memory access.

## Identity providers and source access

The [OAuth foundation](oauth.md) in service 4.0.11 adds individually
revocable external identity bindings for one operator-approved workspace per
issuer configuration. Other tenants cannot claim those users. It supplements
existing keys. The 4.2.0 source adds [personal passwords, invitations and device
sessions](sign-in.md), with release validation tracked in [current status](../RELEASE_STATUS.md).
Complete company identity-provider onboarding, hosted-agent consent and
app-managed host recovery remain required work.

Each source connection belongs to a space, has an explicit provider configuration,
tracks a checkpoint and runs under an authorized identity. Git, local folders,
Google Drive, Slack, rclone storage and custom adapters use the same ingestion,
revision, review and deletion pipeline. Connecting a provider does not automatically
grant every organization member access. Provider credentials stay on the ingestion
host. Preserve upstream access restrictions when choosing a destination space;
source ACLs are not an automatic replacement for the space grant policy.

Studio can run on an employee's laptop while the service and embedding worker run
on organization hardware or a cloud VM. The small local vault client does not load
the service's embedding model. Shared ingestion and retrieval use bounded queues,
durable receipts, idempotency keys, leases and explicit readiness. A failed or
busy worker leaves observable work to retry rather than silently losing memories.

Obsidian exports contain only currently authorized content. They remain portable
Markdown with source links and a refresh manifest, and can be placed in a chosen
local or synchronized folder. **Exported files are plaintext copies.** Revoking a
service key cannot remove an unmanaged copy on somebody else's disk. Use encrypted
devices and approved vault storage, and keep exported private data out of public
Git repositories. Mnemion does not claim end-to-end encrypted search or automatic
retroactive erasure of external copies.

For a team deployment, terminate HTTPS at the approved ingress, keep PostgreSQL
private, use encrypted disks and backups, and keep credentials outside the source
tree. The default Compose listener is loopback-only. Review/deletion controls apply
to search, context, exports and evaluation labels; recovery reconciles later
revocations/deletions before publication. Follow the [recovery runbook](recovery.md)
and rehearse it with your own data size before production adoption.
