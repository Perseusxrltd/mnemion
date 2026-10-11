# Organization deployment and vault security

Mnemion separates the organization, authenticated identity, memory space, source
connection and subject described by a memory. A memory about a person does not
authenticate as that person. One deployment can serve multiple organizations;
PostgreSQL row-level policy enforces tenant and space boundaries.

Start with one organization and create separate spaces for departments, projects,
client engagements and personal work. Grant each employee and integration its own
identity and revocable key. Reader, writer, reviewer and administrator permissions
control each operation; searching multiple spaces still checks every requested
space. Use a shared project space only for knowledge that all its members may read.

Use **Team and applications** in Studio to manage principals, credentials and
grants. API and worker database logins have separate restricted roles; the schema
owner is only for setup, migration and recovery. Do not give assistants an owner
key merely to simplify configuration. MCP HTTP calls retain each caller's identity.

The [OAuth foundation](oauth.md), under development after 4.0.10, adds individually
revocable external identity bindings for one operator-approved workspace per
issuer configuration. Other tenants cannot claim those users. It supplements
existing keys; built-in personal/company sign-in, invitations and the complete
app-managed access and recovery flows remain required work.

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
