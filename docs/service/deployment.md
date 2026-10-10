# Deploy and operate Mnemion

The included Compose deployment runs PostgreSQL 17 with pgvector, the shared API
and Studio, and a durable worker. It uses pinned image indexes and locked Python
and JavaScript dependencies. The desktop app connects to this service; each
desktop does not need its own database or model installation.

The release ledger records the platforms and workloads actually validated. This
guide describes a single-host deployment. High availability, managed PostgreSQL,
company identity federation, and provider-specific acceptance need their own
deployment configuration and verification.

## Start on Windows, macOS, or Linux

Install Python 3.12–3.14 and Docker Engine with Compose, or Docker Desktop using
Linux containers. Start Docker, check out the release, and run from its root:

```sh
python deploy/manage.py init --state-dir /private/mnemion --tenant "My organization" --owner "Owner"
```

Use `python3` where that is the Python command. On Windows, use an explicit local
directory such as `C:\Users\Alice\AppData\Local\Mnemion\service`; quote paths with
spaces. Choose a persistent filesystem with working access controls. The setup
tool restricts the directory to the current user (and SYSTEM on Windows), creates
a random database password, and retains the one-time owner key in
`owner.mnemion-credentials.json`. It prints the filename, not the key. Do not use
a shared, cloud-public, or temporary directory for deployment state.

Initial setup builds the application, applies checked migrations, creates
separate restricted database logins, creates one organization and private space,
and downloads/verifies the pinned local model. Open
`http://127.0.0.1:7892/workspace` and connect using the owner key. Create a distinct
application identity and space grants for each assistant or connector.

Useful commands use the same selected state directory:

```sh
python deploy/manage.py status --state-dir /private/mnemion
python deploy/manage.py logs --state-dir /private/mnemion
python deploy/manage.py stop --state-dir /private/mnemion
python deploy/manage.py up --state-dir /private/mnemion
```

`stop` retains database, model and credential volumes. `up` rebuilds and recreates
containers, revalidates initialization, and waits for readiness. It preserves the
organization and keys; it does not bootstrap a replacement organization. Use
`init --prepare-only` to create private files before starting containers. Use
`--project` and `--port` at initialization for independent installations.

Compose stores data in its named `database`, `operator`, `api_credentials`,
`worker_credentials`, and `models` volumes. The selected host directory stores
the password, setup metadata, owner key, and `backups/`. Preserve both the host
state and operator secrets in a restricted secret store. A database snapshot
does not contain database login passwords. Removing volumes is data destruction,
not a routine reset or upgrade step.

The API and worker run as UID 10001 with a read-only root filesystem, dropped
capabilities, and read-only model/credential mounts. Only short-lived setup and
operator containers receive the database-owner secret. The database has no
published host port. Private container networks and host access controls remain
part of the deployment boundary.

## Network access and resource settings

The host listener defaults to loopback. For other hardware, use a TLS reverse
proxy and initialize with `--public-url https://memory.example.com`. A Caddy
configuration on the same host can be:

```caddyfile
memory.example.com {
    reverse_proxy 127.0.0.1:7892
}
```

Provision DNS, certificates, firewall rules, request limits and authentication
policies appropriate for the organization. Serve Studio from the same origin as
the API. An independently hosted browser client needs explicit comma-separated
`MNEMION_CORS_ORIGINS` entries. The desktop uses its restricted HTTP bridge.
Interactive API documentation is disabled in Compose unless
`MNEMION_API_DOCS=1` is explicitly configured.

Start capacity planning with four CPU cores, 8 GiB RAM and durable storage, then
measure the actual corpus. This is planning guidance, not a capacity guarantee.
The model is local and uses two inference threads per process by default. API
concurrency defaults to 64 (`MNEMION_HTTP_CONCURRENCY`) and the database pool to
10 (`MNEMION_DB_POOL_SIZE`). Increasing workers also increases model memory and
database connections. Vector ranking currently computes exact distance within
authorized scopes; scope size, text length and concurrency affect latency.

## Routine backup and recovery rehearsal

Run one operator at a time. Commands after `operator --` are passed verbatim to
the service CLI. `/backups` inside the container is the selected host state's
`backups/` directory. Always use new filenames:

```sh
python deploy/manage.py operator --state-dir /private/mnemion -- backup --output /backups/snapshot-2026-10-10.mnemion
python deploy/manage.py operator --state-dir /private/mnemion -- verify-backup /backups/snapshot-2026-10-10.mnemion
python deploy/manage.py operator --state-dir /private/mnemion -- recovery-ledger --output /backups/ledger-2026-10-10.json
python deploy/manage.py operator --state-dir /private/mnemion -- restore /backups/snapshot-2026-10-10.mnemion --database mnemion_recovered --ledger /backups/ledger-2026-10-10.json --credentials-output /backups/recovered.mnemion-credentials.json
```

The restored database must have a new name. Restore verifies all table hashes,
reconciles the later deletion/access ledger, suspends source permissions pending
fresh provider checks, and rotates every API key. It does not switch the live
service. The [recovery guide](recovery.md) describes archive trust, ledger
freshness, retention, positive-write recovery points, and v3 preservation.

Copy verified snapshots and a more frequent recovery ledger to an encrypted
backup location outside this host's failure domain. Define recovery-point and
recovery-time objectives, measure a restore regularly, and test the required
retention policy. Managed PostgreSQL PITR can improve the positive-write recovery
point; it does not replace current deletion/access reconciliation.

## Cut over to the verified restored database

Schedule the write interruption and validate the recovered data using an isolated
API/worker before changing client routing. Then run the explicit cutover:

```sh
python deploy/manage.py adopt-restored --state-dir /private/mnemion --database mnemion_recovered --recovery-file recovered.mnemion-credentials.json
```

The helper stops API and worker containers. Activation verifies the recovered
administrator key, matching completed-recovery record, migration hashes, and
both restricted database roles. It records the database and owner credential in
one atomic activation file, derives fresh runtime files, and recreates the
service. Initialization and subsequent operator commands use this recorded
database. The prior database and operator state remain available for inspection.
The host's previous owner credential is retained in a private `owner.previous-*`
file; the primary owner credential file receives the recovered key.

By default, activation selects the original deployment's organization from the
recovery file. Use `--tenant-id` to select another recovered organization. The
full recovery file retains the separate new owner keys for other organizations;
distribute them through the organization's secret-management process. Reissue
application keys and refresh provider access before reconnecting adapters.

If cutover is interrupted, inspect `status` and rerun the same `adopt-restored`
command with the same database and credential file. The atomic activation record
makes derived-file publication resumable. Do not delete state files to bypass a
diagnostic. A stale owner key, unmatched recovery record, or missing role
manifest is rejected. A full host/cluster loss additionally requires recovering
the original role manifest and provisioning its restricted logins, or following
the explicit standalone recovery procedure.

Reopening an older database after new writes or revocations is not a complete
rollback. Preserve and reconcile the accepted tail and latest deletion/access
ledger before changing routing again. Keep the old database until that rollback
window is closed deliberately.

## Readiness, incidents, and upgrades

`/health/live` checks process liveness; `/health/ready` checks the database and
registered embedding generation. Compose verifies the model cache before API
startup. These endpoints do not prove worker progress. Monitor accepted/indexing
operation age, terminal failures, indexing completeness, source permission expiry,
failed provider scans, and disk/database availability through Studio Activity and
the authenticated operations/connector APIs.

Retry interrupted writes with their original idempotency key. A model failure
leaves accepted work durable and exposes incomplete semantic indexing; do not
replace embeddings with a different model under the same generation ID. A stale
provider access lease denies access until fresh permission evidence arrives.
Pause a compromised connector or disable its application identity, revoke its
keys, rotate provider credentials, and inspect the audit history.

Before upgrading, export a current snapshot and ledger, retain the working image
and dependency locks, and rehearse the new version against a copied database.
Applied migrations are immutable and checksummed. Changed checksums or a schema
version mismatch stop startup; editing an applied SQL file is not an upgrade.
Restart with `up`, verify scoped save/retrieve/correct/delete and a local Obsidian
refresh, then reconnect applications. Keep private credentials, source content,
backups and diagnostic dumps out of public issues and build artifacts.
