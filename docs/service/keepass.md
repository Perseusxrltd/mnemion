# KeePass import and export

Workspace server **4.23 or later** adds KeePass transfer to **Secrets** in web
and desktop Studio. The workspace must already have its
[encrypted credentials vault](secrets-vault.md) enabled and its matching host
key available. The live [release status](../RELEASE_STATUS.md) identifies which
native packages are published.
The 4.23 candidate was withheld for an Intel Mac binary-dependency failure;
4.24 carries the same transfer protocol with a compatible dependency pin.

## Import current credentials

1. As a workspace administrator, open **Secrets → Import KeePass** and select
   a `.kdbx` file. Enter its master password and, if required, select its key file.
   A separate option supports databases that use a key file without a password
   component. An empty password component is distinct from having no password.
2. Choose a name prefix. Leave **Mask account, group and custom-field names**
   enabled to use opaque identifiers in the ordinary credential list. Standard
   field labels such as `password` and `username` remain readable. If masking is
   disabled, the preview uses percent-encoded original names; excessively long
   names require masking or a smaller selection.
3. Choose **Verify file & preview names**. Review entry/credential counts, names
   and omitted history, attachments or recycled entries. Nothing has been
   imported yet. Each nonempty current field becomes a separate credential,
   including standard strings, custom properties and entry CustomData values.
   Empty fields are retained in encrypted mapping for later export.
4. Confirm the current-field import. All credentials commit together. Their
   initial grants belong to your current signed-in person or exact agent key;
   no old KeePass permissions or other workspace grants are copied.

Changing the file, prefix or masking option invalidates the preview. Retrying
the same unchanged import as the same principal returns the existing entries
without duplicates. A changed/deleted earlier import or a name collision is
refused; nothing is overwritten. Use a new prefix for an intentionally separate
copy. Editing or deleting a credential after import does not modify the original
KDBX file.

## Export selected credentials

Select credentials you can read, then choose **Export selected to KeePass**.
Generate a fresh password, save it independently, confirm that it is saved and
download the `.kdbx` file. A custom password must have at least 12 characters and
pass the server's strength check. The app verifies the file's SHA-256 before
offering it as a download. Keep the password separate from the file.

Imported fields retain their original entry identity and grouping where possible.
Export includes only selected, currently readable values. A password-only grant
does not reveal an unselected account title or username: a missing title gets a
neutral placeholder. Empty fields from the original entry can be included; other
unselected values are not fetched. Ordinary Mnemion credentials become KeePass
entries with their label as Title and their value as Password. Export records
per-credential access events without logging values or names.

Use KeePass or KeePassXC to open the downloaded KDBX 4.1 file. Exports use
AES-256, Argon2id at 32 MiB / 3 passes / 1 lane and ChaCha20 protected strings,
with fresh salts, nonces and keys for each file. This is a current-credential
transfer, not a complete reproduction of every KeePass database feature.

## Compatibility and limits

| Item | Supported |
| --- | --- |
| Container | KDBX 4.0 and 4.1; AES-256 or ChaCha20 outer encryption |
| Key derivation | AES-KDF: 1–1,000,000 rounds; Argon2d/id v1.0 or v1.3: up to 64 MiB, 32 passes, 4 lanes |
| Protected strings | Salsa20 and ChaCha20 |
| Key files | XML v1/v2, raw 32-byte keys, 64 hexadecimal bytes, other binary key files hashed by the standard SHA-256 method; at most 64 KiB |
| File size | At most 1 MB encrypted and 2 MB after unpacking |
| Import | At most 100 current KeePass entries, 100 fields per entry and 500 nonempty credential fields in total |
| Export | At most 100 selected credentials per operation; select another page for more |
| Values and names | Values up to 65,536 UTF-8 bytes; group/field names up to 2,048 UTF-8 bytes; mapped display names up to 120 characters; encrypted context up to 32 KiB per credential |
| Groups | Root plus at most 24 nested groups |
| Deliberate omissions | Historical entry versions, recycled/deleted entries and attachments; shown before approval |
| Other database features | Custom icons, Auto-Type, expiry/timestamps, tags, database settings and key-provider plugins are not transported |

Make a separate transfer copy in KeePass if a database exceeds these limits or
uses another cipher/KDF. Reduce the copy's selection or KDF settings; keep the
original backup and its stronger settings. Unsupported files fail before any
credential is written. One conversion runs per service process at a time to
bound memory use; another request may receive a busy response and retry later.
Files identified as XML must be valid KeePass XML key files; arbitrary XML
documents are not supported as binary key files. Deeply nested roots may need
separate exports when combining credentials from different KeePass databases.

## Security, hosting and recovery

The browser sends the encrypted file and unlock components through the current
authenticated workspace connection. Use the workspace's trusted HTTPS address
for remote access. Decryption and conversion take place in the workspace host's
memory. Mnemion creates no plaintext temporary files and does not retain the
import password/key file, but the trusted host handles plaintext during conversion;
process memory, OS paging and crash dumps remain under the host's control.
This is not a client-side zero-knowledge vault.

Stored values and original KeePass grouping/field names use separately bound
authenticated encryption. Masked display labels are identifiers, not a hiding
mechanism for the existence or number of credentials. Neither values nor their
mapping enter memory search, embeddings, the librarian, Obsidian or Git sources.
The regular credential grant, revocation and audit rules apply to every transfer.

Migration **026** adds encrypted mapping columns without changing existing
values or grants. Full host backups preserve them. Deletion clears both value
and mapping; restoration with a newer denial ledger clears both again. Portable
Mnemion vault exports containing mappings use contents version 2 and need 4.23
or later for import. Their encrypted outer envelope is unchanged, and ordinary
exports without a mapping keep contents version 1. Retain the matching software
and independent recovery keys with your backup procedure.

## Apps, scripts and agents

The authenticated HTTP routes are `POST /v1/vault/keepass/preview`, `/import` and
`/export`. Python provides `Client.vault_keepass_preview`,
`vault_keepass_import` and `vault_keepass_export` with typed command/response
models. TypeScript provides `previewKeePass`, `importKeePass`, `exportKeePass`
and `supportsKeePass`. Files/key files are base64 in JSON; a null password means
no password component. Import requires the exact preview's `expected_plan` and
literal `import_current_values: true`.

The [agent control catalog](agent-control.md) exposes `vault.keepass.preview`,
`vault.keepass.import` and `vault.keepass.export`. These require the CLI's private
`--input` and `--result-file` paths. Keep passwords out of command arguments,
stdout, chat transcripts, shared documents and regular memory tools. The generic
MCP control surface refuses these sensitive transport operations; the separately
enabled explicit vault tools remain available under their normal policy.
