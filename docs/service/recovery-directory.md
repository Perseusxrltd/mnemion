# Recovery directory and independent kit

Service and Studio **4.8.0** add an organization recovery directory. Check the
[published release status](../RELEASE_STATUS.md) before requiring that version.
It records how independently enrolled administrators can reach the host,
find recovery material and contact the right people when an agent is unavailable.

## Configure it in the app

Sign in with your own organization administrator account and open **Recovery
directory**. You do not need a memory-space grant to use it.

1. Record concise recovery instructions and, optionally, the HTTPS address of a
   recovery page hosted independently of the memory server.
2. Add primary, recovery or ingestion hosts. Record the workspace address, the
   provider's console address and the responsible operator. An entry records
   where to sign in; it does not grant provider or operating-system authority.
3. Add recovery locations. Choose **Database backup**, **Access & deletion
   ledger**, or **Source mirror**. Local paths, Git repositories, cloud storage
   and company storage can be described without connecting to them. A verification
   date is the administrator's reported observation, not an automatic check.
4. Add independent contacts, then select **Save recovery directory**. Another
   administrator's intervening edit produces a conflict; reload and review it
   before saving again. Unsaved edits prevent automatic desktop restarts.

Only current organization administrators can read or update the directory. The
service isolates tenants, checks current authority again after waiting for an
administration lock, and records the editor, revision and entry counts in the
audit trail. Free-text references stay out of the audit event details.

The directory allows up to 16 entries of each kind and 6 KiB of UTF-8 metadata.
Link to longer runbooks. Keep credentials in a separate credential store:
credential-bearing URLs and obvious key/DSN patterns are rejected, but this is
not a universal secret detector. Nothing here becomes a searchable memory,
embedding, source import or automatic librarian/context input. An explicitly
authorized administrator agent can read it through the operation described below.

## Keep access to the information when the host is offline

Remembering an administrator connection in the desktop app captures a dated
copy inside the existing OS-protected credential storage. Successful supported
reconnections refresh it; a temporary failure or older server preserves the last
valid observation. A current non-administrator connection drops the cached
directory. Locked secure storage reveals no protected recovery details.

From the welcome screen, choose **Details & recovery** beside the saved workspace.
Reading these details does not contact, select or reconnect to its server. The
saved role and directory describe an earlier observation and cannot authorize
current changes. **Refresh protected offline copy** is available to a remembered,
connected administrator. Its failure preserves the last valid copy unless the
server has explicitly denied directory access. Large optional metadata cannot
replace the saved credential or enlarge the old per-connection format boundary.

For another device, use **Download encrypted recovery kit** and choose a separate
passphrase of at least 15 characters. Several unrelated words work well. The
app encrypts the directory locally and downloads one HTML file. Saved login
credentials, backup keys and memory data are not automatically included.

Open the file in a current browser, or serve it from your organization's
independently controlled HTTPS site. Unlocking it needs no Mnemion service,
agent session or online decryption service. Viewing the kit makes no network
requests; following a displayed link opens that provider in a separate tab.
Keep the passphrase separately and test it before relying on the kit. Replace
the kit when the configuration changes. Existing downloaded or cached copies
cannot be remotely revoked. Protect the delivery location: encryption protects
the directory, but does not authenticate changes to the HTML viewer itself.

## Agent and application controls

The reviewed operations are `recovery.directory` (read) and
`recovery.configure` (write), available through HTTP, the control CLI and generic
MCP discovery/execution. They enforce the same administrator checks. The
TypeScript SDK provides `recoveryDirectory()` and
`configureRecoveryDirectory(expectedRevision, directory)`.

`GET /v1/recovery-directory` returns a tenant-bound record. Revision zero means
unconfigured. `PUT /v1/recovery-directory` accepts
`{"expected_revision": 0, "directory": {"instructions": "Company runbook"}}`;
omitted collections start empty. Existing records must use their current revision.
Both successful reads and writes return the complete validated record.

Agents can save a private record and create the same independent viewer locally:

```sh
mnemion-control --credentials /private/workspace.json call recovery.directory --result-file /private/recovery-record.json
mnemion-service recovery-kit --record-file /private/recovery-record.json --passphrase-file /private/kit-passphrase --endpoint https://memory.example.org --workspace-name "Company memory" --output /private/company-recovery.html
```

Use appropriate private paths for your OS. The record and passphrase files must
belong to, and be readable only by, the current OS account. The command accepts
the control CLI's result envelope or a raw API response, makes no network calls,
and exclusively creates a private output file; it never overwrites an existing
kit. The verified workspace address and name are supplied explicitly because
the result file does not prove a host's current identity.

The shared viewer uses AES-256-GCM with independent random salt/nonce, PBKDF2
SHA-256 with 600,000 iterations, and authenticated format metadata. Neither the
passphrase nor a saved workspace credential is sent to an API to create it.
The viewer uses bounded, allowlisted data and text rendering, with no external
scripts or resources. Its template and canonical logo are shared by both exporters;
`npm --prefix studio/electron run generate:recovery-kit` regenerates the checked
template after edits.

## Recovery scope

A source mirror can recover its tracked documents. Complete restoration needs a
verified database backup and the current access/deletion ledger; see
[desktop backups](native-backups.md) and [database recovery](recovery.md).
Directory metadata is included in database backups and remains subject to the
restored workspace's current administrator policy.

This directory does not create replicas, upload or verify backup contents,
restart hosts, delegate provider authority or coordinate failover. Those controls,
recovery-custodian policy and company identity onboarding remain in the
[continuity contract](../implementation/workspace-continuity.md).
