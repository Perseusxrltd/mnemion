# Encrypted credentials vault

**Secrets** is available in desktop and web Studio, with matching HTTP,
Python, TypeScript and agent controls. Source **4.46.46** adds exact-key metadata
auditors and a separate metadata-only MCP setting. Check [release status](../RELEASE_STATUS.md)
for published installers. Credentials are stored separately from memory;
Obsidian remains the Markdown view of ordinary memories.

## Set up a desktop-owned host

1. Open **Setup & this device → Encrypted credentials vault → Set up vault**.
2. Generate a vault key. Save an independent copy in your existing password
   manager or another private location, then confirm that the copy is saved.
3. Enable app/API access. For agents that need to inspect names, versions and
   access logs, enable **Let agents inspect permitted credential names, versions
   and access logs through MCP**. Enable the separate secret-value tools only
   for agents that should explicitly retrieve credentials. Host exposure options
   remain disabled until configured; upgrades do not turn them on.
4. Save. A running local workspace briefly stops and reopens with the same
   organization, memories and credentials.
5. Open **Secrets**, create a credential and grant the required people or agent
   keys access. Use a name that contains no sensitive value.

Host controls act on the local workspace named in the panel, even when Studio
is connected to another server. Remote organization administrators cannot change
the host key through the memory API. Independently hosted deployments use their
authorized host operator and the environment configuration below.

The app keeps the root key in its private `vault-access.json` host file, protected
by the owning OS account's file permissions. Ordinary status includes only its
fingerprint. **Show host recovery key** is a separate explicit local operation;
its display clears after a minute or loss of focus. After copying, the clipboard
remains under the user's control.

## Access and everyday use

| Grant | Recipient's access |
| --- | --- |
| List only | Name, ID and version; no value. |
| Read | List and explicitly reveal/export the current value. |
| Write | List and replace the current value using its current version; no implicit read. |
| Read and write | Read and replace the value. |
| Remove grant | Revoke that person or key's access. |
| Metadata auditor | All credential names, IDs, versions and access events in this organization; no value or management permissions. Assigned to an exact key, separately from entry grants. |

Administrators manage names, grants, creation and deletion. They do not implicitly
receive plaintext access but can explicitly grant it to themselves. This separates
administrative duties; it does not protect against a malicious administrator or
host operator. A creator receives an initial grant to their signed-in person, or
their exact current key when using machine-key access.

A **person** grant follows current password/company device sessions. It does not
automatically apply to their separately issued API keys or hosted assistant
connections. A **key** grant applies to that exact key, not every key owned by
the same person/application. Expiry, revocation and disabled people are checked
on each request. Memory-space grants remain independent.

Explicitly revealed values stay in transient component state and clear after a
minute or loss of focus. They do not enter the query cache, browser storage,
search, embeddings, context packs, the librarian or Obsidian exports. Replacing
a value requires its observed version; concurrent changes require a refresh.
There is no plaintext value history. Deletion purges the current encrypted value
and retains its deletion denial.

The audit view is available to administrators and explicitly granted metadata
auditor keys. It records action, outcome, time, principal/key and entry IDs,
without values or credential names. Auditor-grant changes also record the target
key ID. Auditors can inspect events for deleted credentials. Vault operations and authenticated
authorization denials are recorded. Requests rejected before vault admission,
such as invalid authentication or malformed input, are outside this vault audit.
The service refuses to release a value when its audit write cannot commit.

## Give an agent metadata access

1. As an organization administrator, open **Secrets → Metadata auditors**.
2. Choose the agent key or paste its **key ID**. This is the UUID shown by the
   agent's `vault.status` as `current_key_id`, not its private bearer token.
3. Choose an expiry and select **Grant metadata access**. The app defaults to
   seven days; **When revoked** leaves the grant without a time limit.
4. If the agent uses MCP, the host operator must also enable metadata in vault
   setup. Remote administrators control the grants; the host operator controls
   exposure and the root key.
5. The agent can inspect `vault.status`, `vault.list` and `vault.audit`. It receives
   permitted metadata only. Use **Change** to renew or adjust the expiry, and
   **Revoke** to remove the role.

Auditor access covers all credential metadata in this organization, including
future credentials; names can themselves reveal operational information. For
only a few credential names, retain the existing per-entry **List only** grants.
Those grants do not provide the organization-wide audit log.

Auditor grants do not follow a replacement or sibling key. A disabled owner,
revoked key, expired key or expired auditor grant loses auditor access on the
next request. Every change checks the current grant revision, so competing
administrators cannot silently overwrite each other. Removing an auditor grant
does not remove independently assigned credential read/write/list grants.
An organization supports up to 1,000 auditor records, including revoked records.

## Backups, exports and recovery

| Key | Opens |
| --- | --- |
| Workspace backup key (`mnm_bk_…`) | An encrypted full snapshot or recovery ledger. |
| Host vault key (`mnv_…`) | Credential values inside that workspace database. |
| Portable export key (`mnv_…`) | One separately encrypted credentials export; generate a fresh key for each export. |

Full database backups include vault ciphertext, metadata and audit records,
**not the host vault key**. Keep the required keys independently from snapshots.
After [independent workspace recovery](native-backups.md), choose **Restore an
existing key** in vault setup and supply the original host vault key. The current
ledger preserves credential deletions made after the snapshot. Recovery clears
historical per-entry grants and disables historical auditor grants, advancing
their revisions; an administrator must review and grant fresh access.
A snapshot containing vault entries requires a vault-aware recovery ledger.

Missing, damaged or mismatched keys close secret-value access while ordinary memory
remains usable. When the vault API is enabled, permitted metadata and audit
inspection remain available to diagnose and repair the key. Host disablement
still closes metadata listing and auditor access; administrators retain the
existing API audit view. Supplying a new key does not re-encrypt existing values. Explicit
key repair retains prior private key files in the host's recovery directory;
these copies are not automatically pruned. Managed key rotation and external KMS
integration are not included in this release.

Use **Export selected**, generate and save a separate export key, then download
the encrypted JSON. Exports contain only entries you can currently read. Store
the file in your own Git, Drive, cloud or backup system as needed; a downloaded
file does not prove independent delivery or durability. Keep its key elsewhere.

Import requires an administrator, the encrypted file and its export key. It
creates new IDs with fresh creator grants. A name collision rejects the entire
import without overwriting existing credentials. Each operation allows at most
100 entries, each value at most 65,536 UTF-8 bytes, and each export at most 1 MB
of plaintext. The app lists 100 entries per page and labels its filter as applying
to that page. A workspace supports up to 10,000 active credentials and each
credential up to 1,000 explicit grants.

Managed file/Git/rclone and Drive imports reject the native vault key filename,
generated vault-key material and recognized portable vault envelopes. This is
not universal secret detection for unrelated documents or values deliberately
pasted into ordinary memory. Keep credentials out of capture folders. Optional
KeePass interoperability is available from source **4.23** through
[Import KeePass / Export selected to KeePass](keepass.md), including reviewed
current-field mapping, default name masking and in-memory conversion. Check
release status for native availability. History, attachments and recycled
entries are deliberately omitted and shown in the preview. Portable Mnemion
exports that contain these encrypted mappings require 4.23 or later to import.

## Independently hosted service

Apply the current migrations, including **020** for vault storage and **036**
for metadata auditors, through the existing [deployment/upgrade](deployment.md)
procedure. Store the generated key as `MNEMION_VAULT_KEY` in the API host's private
environment or secret store, then set its access options:

```text
MNEMION_VAULT_ENABLED=1
MNEMION_VAULT_MCP_METADATA_ENABLED=1
MNEMION_VAULT_MCP_ENABLED=0
```

Generate a key with `mnemion.service.vault_crypto.new_vault_key()` and write it
directly to a private file/secret store without logging or command-line arguments.
Desktop setup provides the same generator without requiring Python. Do not give
the root key to indexing workers, clients or source runners. Existing explicit
environment configuration appears as externally managed in the app and is not
overwritten. Restart the API to apply policy changes.
The example enables metadata-only MCP. Set the metadata flag to `0` to keep it
closed. Full secret-value MCP also permits metadata operations, while all
per-key/per-entry authorization checks remain in force.

AES-256-GCM encrypts values with fresh nonces and authenticated organization,
entry, name and version identity. Names, IDs and timestamps are not encrypted.
Database row-level policy and current application authorization enforce tenant
and grant boundaries. This is server-side encryption: the API and authorized
host operator can access the root key. It is not end-to-end or zero-knowledge
encryption. Use HTTPS remotely and protect host files, backups and administrators.

## Agent and SDK controls

The [reviewed operation catalog](agent-control.md) adds `vault.status`,
`vault.list`, `vault.get`, `vault.put`, `vault.grants`, `vault.grant`,
`vault.delete`, `vault.export`, `vault.import`, `vault.audit`, `vault.auditors`
and `vault.auditor`. Discover each
live schema before writing. Secret-bearing inputs use the control CLI's private
`--input` file; plaintext reads require `--result-file`. Root-key configuration is
absent from this network API. Inspect the current entry after an interrupted
write before retrying; version checks prevent overwriting a later change.

Python's `mnemion.sdk.Client` provides the same operations with underscores, for
example `vault_get` and `vault_put`. TypeScript provides typed counterparts, such
as `vaultValue` and `putVaultValue`. Only explicit value reads return plaintext;
listings and write receipts contain metadata. Do not log sensitive inputs/results.

To configure a metadata auditor without the app:

- Read `vault.auditors` with `parameters.key_id` set to the exact key UUID. It is
  an administrator-only, paged operation (`offset`, `limit`, optional `key_id`).
- Call `vault.auditor` with `parameters.key_id` and a body containing
  `expected_version`, `enabled` and optional `expires_at`. Use version `0` only
  if the filtered list is empty; otherwise use its current `version`.
- An enabled grant's expiry must be a future timestamp with a timezone.
  Omitted or `null` expiry means no time limit. Set `enabled: false` to revoke.
  Revocation retains the row and advances its version. After a conflict or lost
  response, read the current record before deciding whether to submit a new change.
- Equivalent HTTP endpoints are `GET /v1/vault/auditors` and
  `PUT /v1/vault/auditors/{key_id}`. Python exposes `vault_auditors` and
  `vault_auditor`; TypeScript exposes `vaultAuditors` and `setVaultAuditor`.

The status fields `metadata_available`, `audit_access` and
`mcp_metadata_enabled` distinguish metadata availability, the calling key's
audit permission and host MCP exposure. `available` continues to mean that the
vault can perform authorized secret-value operations.

Private vault CLI input/results accept up to the service's 2 MB JSON boundary.
An exported `--result-file` is a portable vault envelope that Studio can import
directly; it does not contain a connection key or unencrypted credential values.
Ordinary inline agent response limits remain unchanged.

With app/API access and **secret-value MCP tools** enabled, full and compact MCP profiles
advertise `vault_list`, `vault_get` and `vault_put`, using the requesting key's
current grants. Explicit MCP reads put the requested value into the receiving
agent/model's context. With only metadata MCP enabled, the generic tools allow
`vault.status`, `vault.list`, `vault.audit`, `vault.auditors` and `vault.auditor`;
the last two still require an organization administrator. `vault_list` is also
available, while `vault_get` and `vault_put` are absent. Both metadata and full
MCP disabled blocks vault operations through the gateway, including generic
tools. These host settings cannot prevent an external program from
wrapping separately authorized REST access. Disable app/API access or revoke
the key/grant to close that access.

The [private desktop catalog](desktop-operator.md) adds `local.vault` and
`local.vault-key` under the owning OS account. Use current
`expected_workspace_id`, `input.workspace_id` and vault `expected_revision` from
status. Configuration includes `action` (`configure` or explicit `restore`),
`enabled`, `mcp_enabled`, optional `mcp_metadata_enabled`, and a private
`recovery_key` plus `key_saved` for initial
setup/restore. Unsaved app edits block agent-requested restarts. Key retrieval
requires a private result destination and never alters public status. These
operations use the existing authenticated local pipe on Windows, macOS and
Linux; memory credentials alone confer no host authority.
Older local records default to metadata MCP disabled. Omitting the new field
when changing a configured host preserves its saved metadata choice.
