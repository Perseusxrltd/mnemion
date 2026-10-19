# Encrypted credentials vault

Source **4.12.0** adds **Secrets** to desktop and web Studio, with matching HTTP,
Python, TypeScript and agent controls. Check [release status](../RELEASE_STATUS.md)
for published installers. Credentials are stored separately from memory;
Obsidian remains the Markdown view of ordinary memories.

## Set up a desktop-owned host

1. Open **Setup & this device → Encrypted credentials vault → Set up vault**.
2. Generate a vault key. Save an independent copy in your existing password
   manager or another private location, then confirm that the copy is saved.
3. Enable app/API access. Enable MCP tools separately only for agents that should
   explicitly retrieve credentials. Both options are disabled initially.
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

The administrator's audit view records action, outcome, time, principal/key and
entry IDs, without values or credential names. Vault operations and authenticated
authorization denials are recorded. Requests rejected before vault admission,
such as invalid authentication or malformed input, are outside this vault audit.
The service refuses to release a value when its audit write cannot commit.

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
historical vault grants; an administrator must review and grant fresh access.
A snapshot containing vault entries requires a vault-aware recovery ledger.

Missing, damaged or mismatched keys close credential access while ordinary memory
remains usable. Supplying a new key does not re-encrypt existing values. Explicit
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
KeePass interoperability remains follow-up work. The supported KDBX 4 workflow
must map entries, standard fields and custom properties, support masked names,
verify value preservation, and avoid plaintext temporary files. The operator's
[manual migration report](https://github.com/Perseusxrltd/mnemion/issues/32#issuecomment-6264307829)
does not mean `.kdbx` import/export is already available in the app.

## Independently hosted service

Apply migration **020** through the existing [deployment/upgrade](deployment.md)
procedure. Store the generated key as `MNEMION_VAULT_KEY` in the API host's private
environment or secret store, then set its access options:

```text
MNEMION_VAULT_ENABLED=1
MNEMION_VAULT_MCP_ENABLED=0
```

Generate a key with `mnemion.service.vault_crypto.new_vault_key()` and write it
directly to a private file/secret store without logging or command-line arguments.
Desktop setup provides the same generator without requiring Python. Do not give
the root key to indexing workers, clients or source runners. Existing explicit
environment configuration appears as externally managed in the app and is not
overwritten. Restart the API to apply policy changes.

AES-256-GCM encrypts values with fresh nonces and authenticated organization,
entry, name and version identity. Names, IDs and timestamps are not encrypted.
Database row-level policy and current application authorization enforce tenant
and grant boundaries. This is server-side encryption: the API and authorized
host operator can access the root key. It is not end-to-end or zero-knowledge
encryption. Use HTTPS remotely and protect host files, backups and administrators.

## Agent and SDK controls

The [reviewed operation catalog](agent-control.md) adds `vault.status`,
`vault.list`, `vault.get`, `vault.put`, `vault.grants`, `vault.grant`,
`vault.delete`, `vault.export`, `vault.import` and `vault.audit`. Discover each
live schema before writing. Secret-bearing inputs use the control CLI's private
`--input` file; plaintext reads require `--result-file`. Root-key configuration is
absent from this network API. Inspect the current entry after an interrupted
write before retrying; version checks prevent overwriting a later change.

Python's `mnemion.sdk.Client` provides the same operations with underscores, for
example `vault_get` and `vault_put`. TypeScript provides typed counterparts, such
as `vaultValue` and `putVaultValue`. Only explicit value reads return plaintext;
listings and write receipts contain metadata. Do not log sensitive inputs/results.

Private vault CLI input/results accept up to the service's 2 MB JSON boundary.
An exported `--result-file` is a portable vault envelope that Studio can import
directly; it does not contain a connection key or unencrypted credential values.
Ordinary inline agent response limits remain unchanged.

With app/API access and **MCP tools** both enabled, full and compact MCP profiles
advertise `vault_list`, `vault_get` and `vault_put`, using the requesting key's
current grants. Explicit MCP reads put the requested value into the receiving
agent/model's context. Disabling MCP blocks vault operations through Mnemion's
gateway, including generic tools. It cannot prevent an external program from
wrapping separately authorized REST access. Disable app/API access or revoke
the key/grant to close that access.

The [private desktop catalog](desktop-operator.md) adds `local.vault` and
`local.vault-key` under the owning OS account. Use current
`expected_workspace_id`, `input.workspace_id` and vault `expected_revision` from
status. Configuration includes `action` (`configure` or explicit `restore`),
`enabled`, `mcp_enabled`, and a private `recovery_key` plus `key_saved` for initial
setup/restore. Unsaved app edits block agent-requested restarts. Key retrieval
requires a private result destination and never alters public status. These
operations use the existing authenticated local pipe on Windows, macOS and
Linux; memory credentials alone confer no host authority.
