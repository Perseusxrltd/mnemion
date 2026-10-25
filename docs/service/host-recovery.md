# Recover a supervised workspace host

From 4.15.0, recovery also pauses [Git journal publication](git-journal.md).
Its registry can be retained as a private package asset, but the new host must
enroll its own paths and Git credentials. Restoration does not activate scanner
programs from the old host. An administrator must approve publication again.

From **4.13.0**, a Linux or macOS host operator can save one encrypted package
containing the database and the settings needed to rebuild its Mnemion service.
The restore creates a new database, retains organization and memory identities,
provisions separate database logins, and prepares the API, worker, updater and
selected source runners together. It does not run `bootstrap` or silently create
a replacement organization.

This is an operator and agent CLI workflow for a
[supervised service](supervision.md). The guide is also available in the app's
documentation. Windows, macOS and Linux desktop-owned workspaces retain their
[native backup and recovery UI](native-backups.md). From 4.30, that app can also
[inspect a server package and recover its database into a separate local workspace](desktop-host-recovery.md)
on all three operating systems. Provider/host configuration stays in the original
encrypted package for separate review. Full Windows/Compose host adoption and
guided remote-provider reconstruction remain on the roadmap.

## What you need independently of the original agent

- Access to the replacement computer through its actual hosting provider or OS
  account. A workspace API key cannot start a stopped computer.
- An encrypted host package and its independently saved recovery key. Copy the
  current encrypted access ledger separately when it is newer than the package.
- A supported Mnemion installation, PostgreSQL with pgvector available, and the
  authority to create databases, database roles and the extension there.
- The source storage, provider permissions and any external TLS/tunnel account
  that the organization wants the replacement to use.

Keep the [recovery directory](recovery-directory.md) current with these locations
and contacts. A directory entry or a cloud-synchronized local folder does not
prove that a remote recovery copy was uploaded successfully. Verify provider
delivery and exercise restoration from an independently retrieved copy.

## Prepare the installed tools

Use Python 3.12–3.14, or 3.12/3.13 on Intel Macs, under an unprivileged service
account. The official release wheel includes web Studio; installing that wheel
does not require Node. The separate Node build is for source checkouts.

```sh
python3.13 -m venv "$HOME/.local/share/mnemion/runtime"
"$HOME/.local/share/mnemion/runtime/bin/python" -m pip install \
  './mnemion-4.13.0-py3-none-any.whl[supervision]'
```

Download the wheel from the [official release](https://github.com/Perseusxrltd/mnemion/releases).
The examples below assume this environment's `mnemion-service` command is on
`PATH`. You can also invoke its Python with `-m mnemion.service.cli`.

For managed automatic updates, install the currently pinned free **uv 0.12.24**
package manager and supply its executable with `--uv` when it is not on `PATH`.
The managed setup retains its own reviewed copy. Supply `--pg-bin` if PostgreSQL
client tools are not on `PATH`. PostgreSQL must be the same major version as the
backup or newer; use client tools suitable for the source and destination server.
The package records the source server version. The restore checks schema and
content before publishing the new database.
From 4.27, new snapshots verify stored memories across database locale changes
while PostgreSQL regenerates its keyword index. For an older snapshot, supply
`--database-locale` with the source's installed libc locale when necessary; all
legacy hashes still have to match. See [locale compatibility](recovery.md).
Ledger capture supports the API-key schema that predates individual sign-in;
databases with session keys still exclude those keys from application continuity.

The host package does not install OS packages or provision a hosting subscription.
Existing [deployment](deployment.md) and [managed update](managed-updates.md)
requirements still apply. No paid model or service is added.

## Save a recovery key and full package

Create the key in a private directory. The command writes the secret to the file
and prints only its path and fingerprint:

```sh
mnemion-service host key --output /private/office-recovery.key
```

Save another protected copy independently of the host and backup storage.
Losing every copy of this key makes its encrypted packages unusable. Rotating to
a new key does not re-encrypt old packages; retain keys for copies you keep.

Create a package from an existing Supervisor state directory:

```sh
mnemion-service host snapshot \
  --state-dir /private/mnemion-service \
  --key-file /private/office-recovery.key \
  --output /recovery/office-2026-10-19.mnemion-host \
  --plan-output /recovery/office-2026-10-19-plan.json
```

On a manually updated Supervisor host, also provide
`--admin-credentials /private/database-owner.json`. That private JSON file uses
`admin_database_url` and must identify the same database as the service's API
and worker logins. Managed installations use their existing private owner file.

Starting with [4.46.8](../releases/4.46.8.md), managed snapshot/ledger capture
uses the existing operator lock to wait up to five minutes for active scans
to finish; this bounds lock acquisition, not the entire capture. A controller's
existing lease is retained. After waiting, capture rereads settings/credentials,
checks for changes in management mode and the complete active runtime record,
and rechecks snapshot destinations. A stable compatible older runtime is still
allowed. Check [release availability](../RELEASE_STATUS.md) for your installed
version and the [validation evidence](../validation/2026-10-25-host-backup-capture.md)
for the scope of the checks.

The full package contains:

- A verified database snapshot covering every organization in that database.
- A deletion/access ledger captured after the snapshot, including eligible
  application-key identities. Raw application keys are not added to the ledger.
- The saved service environment and explicitly referenced private provider files.
- Registered source-runner configurations and their required token files.
- An identity-bearing recovery plan and content integrity records.

The package uses authenticated streaming encryption. Its public plan contains
versions, identifiers, counts, provider types and update/route flags, without
database logins, token values, memory content or private source locations.
Treat even this organizational inventory as information to share deliberately.

An additional source runner can be included with a repeated
`--connector-config /private/source.json`. It must belong to this database and
match its registered provider. Runners already registered with Supervisor are
included automatically. Use `--include-file /private/extra.json` for another
required private file. Provider JSON references such as `api_key_env` and
`file_env` must resolve when the package is created; missing references fail the
operation rather than producing an incomplete package silently.

The saved environment's absolute `*_CONFIG`, `*_FILE` and `*_BUNDLE` references
are included. Included JSON file references are rebound to the new protected
asset directory during restoration. Model caches, weights and broker sockets
are excluded. These belong to the replacement hardware. A custom shell command,
executable override or host startup script is not imported and executed.

Up to 64 distinct source runners and 128 private files are supported per
package. Each private file is bounded to 8 MiB, their combined content to 64 MiB,
and the host recipe to 1 MiB. The database archive retains the normal bounded
[recovery format](recovery.md).

## Copy the latest access state more frequently

A smaller encrypted ledger can preserve newer revocations and deletions between
full snapshots:

```sh
mnemion-service host ledger \
  --state-dir /private/mnemion-service \
  --key-file /private/office-recovery.key \
  --output /recovery/office-access-2026-10-19T1200.mnemion-ledger
```

The response includes the ciphertext SHA-256, key fingerprint and observation
time. Store that receipt with the ledger. Use a unique destination for every
run; existing files are preserved. An unmanaged host also needs
`--admin-credentials` here.

Schedule these commands through your existing OS or company scheduler and copy
their successful outputs to independently controlled storage. There is no
built-in host-package scheduler or verified cloud-upload agent in this release.
Desktop schedules remain available through the native app.

Recovery can enforce only access state known to the supplied ledger. Changes
made after the most recent independently saved copy cannot be reconstructed
from an older package. Choose snapshot and ledger intervals for the company's
accepted recovery window, and retain their keys outside the failed host.

## Inspect the selected copy

```sh
mnemion-service host inspect \
  --package /recovery/office-2026-10-19.mnemion-host \
  --key-file /private/office-recovery.key
```

Review organization IDs, snapshot/ledger dates, provider inventory and the
reported `sha256`. `authenticated: true` verifies the encrypted package and its
outer content integrity. `database_restore_verified: false` is deliberate:
inspection does not claim that PostgreSQL has restored the inner database.
The restore performs that separate validation.

## Restore into a new database and private directory

Supply the replacement cluster operator through a private JSON file with an
`admin_database_url` field. It needs provisioning authority for databases, roles
and pgvector. Keep the file owned by the service account and mode 0600. This
connection is used for provisioning; its password, passfile, client private key
and session-role overrides are not copied into the new service logins.

```sh
mnemion-service host restore \
  --package /recovery/office-2026-10-19.mnemion-host \
  --key-file /private/office-recovery.key \
  --expect-sha256 '<SHA-256 returned by inspection>' \
  --operator-credentials /private/replacement-postgres.json \
  --database office_restored \
  --destination /private/office-restored \
  --database-host 127.0.0.1 \
  --port 7892 \
  --public-url https://memory.example.com \
  --start
```

`--database-host` selects the endpoint used by the new password-authenticated
owner, API and worker accounts. It is especially useful when the cluster
operator uses a Unix socket with peer authentication. Configure PostgreSQL to
permit those password logins. Add `--database-port` if required; omit both to
use the operator connection's network/socket route. Server certificate trust
settings are retained. A separate endpoint must reach the same restored
database; the tool verifies its recovery identity before preparing the service.
`--host` and `--port` instead select Mnemion's HTTP listener.

For a legacy backup made on a `C.UTF-8` database, for example, add
`--database-locale C.UTF-8` if the replacement cluster uses a different default.
This option requires 4.27 or later and an installed libc locale. A reviewed
locale becomes part of the idempotent recovery selection: retry with the same
choice, or use a fresh directory and database for a different selection. New
portable snapshots normally need no locale override.

To use a newer independently copied ledger, add both:

```sh
  --ledger /recovery/office-access-2026-10-19T1200.mnemion-ledger \
  --ledger-sha256 '<SHA-256 from its saved receipt>'
```

The ledger must authenticate with the supplied key, cover every backed-up
organization, and be at least as recent as the snapshot. The default uses the
package's embedded ledger. An altered package or ledger is rejected before a
destination database is created.

If source storage moved, provide explicit absolute path mappings:

```sh
  --path-map /old/shared-notes=/mnt/company/shared-notes \
  --path-map /old/git-cache=/private/source-cache
```

These rewrite matching saved paths; they do not copy the source storage itself.
Review provider scopes, local mounts and source permissions before reconnecting
the external route. An inbound Git source contains only its own committed
documents, not every native Mnemion save or its current access/deletion state.
See [source scope and write-back limits](connectors.md).

## Choose the access policy deliberately

The default, `--access-policy rotate_all`, invalidates backed-up API keys and
human sessions. It produces fresh recovery-owner credentials in the private
`recovery-credentials.json` file. Eligible included source runners receive new,
scoped application keys in their private files so they can run after review.
A source key revoked in the current ledger is never replaced automatically.

For a controlled relocation with trusted independent access custody, use
`--access-policy preserve_applications`. Only non-administrator application keys
present and eligible in both the backup and supplied ledger survive. Human,
session, administrator, disabled, revoked and expired access is excluded. Key
expiry cannot be extended. Current space permissions and denial state still
apply. Fresh recovery-owner credentials are always created.

Both policies reset historical credential-vault grants, invalidate old human
sessions and reconcile later memory/credential deletions. Provider ACLs require
fresh observation and restored librarian outbound activity remains paused as
described in [database recovery](recovery.md). Application-key continuity does
not silently restore access to credential values.

If the host used a [Secrets vault](secrets-vault.md), its encryption key must be
recoverable too. A vault key already in the saved host environment or an included
private referenced file is encrypted inside the package; an externally supplied
key is not magically recovered. Keep independent custody and review fresh vault
grants before enabling agent access.

## Re-run safely after interruption or another host reset

Run the same restore command with the same package, ledger, database name,
destination, paths and access policy. The private journal identifies the
operation. It resumes a committed database/setup step without bootstrapping new
organizations or minting another set of owner credentials. Different existing
files, credentials or unrelated databases are refused and preserved.

If the home directory survives but the database or installed runtime disappears,
the same recipe can rebuild the missing part using a newly installed supported
Mnemion environment. Known old service processes must stop cleanly before repair.
Previous service state is retained privately. A later database loss restores data
as of the selected package and ledger, not unsaved subsequent changes.

For an ordinary repeat after successful restoration, `already_restored: true`
identifies the existing installation. `--start` can start it without repeating
database restoration. A different snapshot or changed recovery selection uses a
new destination so the prior installation is not overwritten.

## Updates, source runners and startup

Managed automatic updates are the default. An explicitly paused source policy
remains paused; a later repair also preserves the replacement's saved pause.
Use `--manual-updates` only when another operator-managed deployment mechanism
owns updates. `host status` and `supervise status` show the actual managed/manual
mode and enabled state. Damaged update settings are reported as unknown rather
than being treated as enabled.

Registered runners start and restart with Supervisor. Each gets its own source
credential and only its explicitly required provider environment. Managed
runners follow the verified active runtime and coordinate scans with updates.
They do not receive the database owner's connection or unrelated vault/provider
credentials as environment variables. They still run under the same OS account;
use separate users/containers for stronger process isolation.

```sh
mnemion-service host status --destination /private/office-restored
mnemion-service supervise status --state-dir /private/office-restored/service
mnemion-service updates status --state-dir /private/office-restored/service
```

The restore and status responses include `startup.boot_command`, `cron_entry`,
`launchd_file` and `launchd_label`. Register the returned entry through the
[Linux cron or macOS launchd procedure](supervision.md#linux-boot-with-cron).
`startup_registration_restored: false` means this command has not registered an
OS boot/login task. Keep its bootstrap Python installed at its selected path.

The public HTTPS origin is restored or overridden by `--public-url`, but external
DNS, TLS certificates, proxy/tunnel processes and provider accounts retain their
own lifecycle. `external_transport_restored: false` and
`remote_access.transport_verified: false` make that boundary explicit. Validate
the public connection before returning users and agents to the service. Local
API readiness alone cannot prove that the original tunnel is online.

## Agent and security contract

All operations use `mnemion-service host --help` and return structured JSON.
Secret inputs use private files; results identify private output files without
printing credentials. Failures use bounded diagnostics, exit 2 for an operation
failure, or exit 75 for an active conflicting operation. A requested start that
does not become ready returns exit 2 with the service status for inspection.
The provisioning connection can alternatively come from
`MNEMION_RESTORE_DATABASE_URL`, falling back to `MNEMION_ADMIN_DATABASE_URL`.

A workspace administrator and a host operator are distinct authorities. These
commands require the hosting account, provisioning authority and independent
recovery key. They are not exposed as generic memory tools or granted merely by
membership in an organization. Full company recovery-custodian delegation,
verified off-host delivery, guided app recovery and safe multi-host takeover
remain tracked in the [product requirements](../PRODUCT_REQUIREMENTS.md).
