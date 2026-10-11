# Managed server updates

From **4.0.8**, a Linux or macOS service can adopt independently signed,
automatic patch updates using `mnemion-service updates`. New managed instances
enable checking by default. The API, worker and updater run under the private
[Supervisor instance](supervision.md); systemd and paid services are unnecessary.
An authorized host agent can perform every step through JSON CLI commands.

This first managed updater covers compatible Python service patches. Existing
servers require one explicit adoption. Containers, Windows servers, PostgreSQL,
Python itself, source runners and reverse proxies retain their deployment
lifecycle. Desktop automatic updates remain separate.

## Requirements

- An ordinary, dedicated Linux/macOS account; root adoption is rejected.
- A working service and database with matching migrations, separate API/worker
  logins, a database owner login for backups, and the `supervision` extra.
- Python 3.12–3.14; Intel Macs currently require 3.12 or 3.13 and macOS 11 or newer.
- The free **uv 0.12.24** installer and matching PostgreSQL client tools.
  Setup copies the reviewed uv executable into private managed state, so a later
  upgrade of the operator's general uv command does not change this installer.
- At least 3 GiB free for staging, plus space for the database backups and models.
  Before backup, available space must also exceed twice the reported database
  size. These are conservative admission checks, not a guarantee against a disk
  filling during concurrent work. Maintain an external storage alert.
- HTTPS access to GitHub release assets and the dependency locations in the
  signed lockfile. Package staging installs wheels without source builds or
  automatic Python downloads. Approved proxy and certificate settings remain usable.

Install the official 4.0.8 wheel with its extra, or use a checked release checkout:

```sh
uv sync --locked --no-dev --extra supervision --python 3.13
uv run --no-sync mnemion-service studio build
```

On Intel Macs, upstream no longer provides a binary for the current
`cryptography` release. The official Mnemion release includes a native wheel
built with pinned static OpenSSL; no compiler or Homebrew runtime is needed.
For the initial checkout installation, replace the `uv sync` command above with:

```sh
uv sync --locked --no-dev --extra supervision --python 3.13 --no-install-package cryptography
uv pip install --python .venv/bin/python --no-deps \
  https://github.com/Perseusxrltd/mnemion/releases/download/v4.0.8/cryptography-50.0.2-cp312-abi3-macosx_11_0_x86_64.whl
```

The wheel's checksum is included in the same release's `SHA256SUMS.txt`. It
contains upstream licenses and source/build provenance. Future managed patches
select, authenticate and install the matching dependency automatically; other
platforms do not download it. The source lock still controls its exact version.

An official wheel already contains Studio, the fonts, guides and notices. Node.js
is only required to build Studio from Git. Keep the original virtual environment
and checkout at their original paths: they launch Supervisor and remain the
bootstrap fallback. Future application runtimes are isolated under managed state.

## Adopt a host

Complete [database provisioning](README.md#run-the-service) first. API and worker
credential files use the existing `database_url` and `worker_database_url` keys.
The shared private file produced by `mnemion-service logins` is accepted for both.
Provide a separate private JSON file with `admin_database_url` for backup access.
Use mode 0600; keep it outside Git and shell history. All three URLs must name the
same explicit database target. libpq service-file indirection is not accepted.

```sh
MNEMION_MANAGED_DIR="$HOME/.local/state/mnemion/managed-service"
uv run --no-sync mnemion-service updates setup \
  --state-dir "$MNEMION_MANAGED_DIR" \
  --api-credentials .mnemion-run/database.mnemion-credentials.json \
  --worker-credentials .mnemion-run/database.mnemion-credentials.json \
  --admin-credentials /private/mnemion-backup-owner.json
```

Use a **new empty state directory**. Setup validates the existing schema without
changing it, copies the role credentials separately, records the installed
embedding generations and writes the managed configuration. A failed setup
removes only that newly prepared installation; input files and the database are
preserved. No listener, host startup entry or migration is started by setup.

Optional setup arguments:

| Argument | Purpose |
| --- | --- |
| `--uv /absolute/path/to/uv` | Select the reviewed installer if it is not on PATH |
| `--pg-bin /path/to/postgresql/bin` | Select matching PostgreSQL backup tools |
| `--environment /private/runtime.json` | Save approved model, provider and resource configuration |
| `--host 127.0.0.1 --port 7892` | Choose the listener; loopback is the default |
| `--public-url https://memory.example.com` | Configure the public MCP origin; does not provision a tunnel or TLS |

Stop any old API/worker deployment before starting the managed replacement on the
same port and database. Use its existing stop command; do not run two worker
installations while changing lifecycle ownership.

```sh
uv run --no-sync mnemion-service supervise start --state-dir "$MNEMION_MANAGED_DIR"
uv run --no-sync mnemion-service updates status --state-dir "$MNEMION_MANAGED_DIR"
```

The generated cron entry and launchd plist work as described in the
[boot and login guide](supervision.md#linux-boot-with-cron). Installing one remains
an explicit host configuration step. Verify actual reboot, database/network
startup order and the organization's OS policy on the adopted host.

## Automatic behavior

The updater checks the official stable release after 1–2 minutes and roughly
every six hours, with jitter to spread simultaneous organization downloads.
It checks a separate Ed25519 signature before interpreting the release payload.
The payload binds version, repository, source commit, wheel/sdist hashes and
sizes, the optional native dependency, Python compatibility, the dependency lock
and every migration hash.
Older versions and changed manifests for an already observed version are rejected.

Only a newer version in the same major/minor series, with **identical database
migrations and embedding-generation identities**, can cut over automatically.
Changed schema, model identity or major/minor versions require operator planning.
No model is silently replaced and no database migration is run.

For an eligible patch, the updater:

1. Downloads bounded, hash-verified wheel and source archives into private state.
2. Validates archive paths and source/wheel parity, then creates an isolated
   environment with the signed, locked dependencies. It makes no inference calls.
3. Checks installed version, Studio, migration identity, model generations and
   the application's exact bytes against the signed wheel. On Intel Macs it also
   verifies the native dependency's package, ABI, source-lock identity and bytes.
4. Creates and independently verifies a database backup **before stopping** the
   running API or worker. A failed backup leaves the running service in place.
5. Writes a durable recovery journal, drains both processes, changes the active
   runtime and verifies the new API instance/PID and worker readiness. Runtimes
   advertising initialization protocol 1 must provide matching private child
   receipts; a process waiting during imports or argument parsing cannot pass.
6. Restarts the updater itself through Supervisor using the newly verified runtime.

There is a short service interruption during cutover. Applications should use
documented retries and idempotency keys. This does not provide high availability
or a maintenance-window scheduler.

If startup fails, the previous runtime is restored with the same live database.
**The updater never restores a database backup automatically**, so writes accepted
by a candidate before a failed readiness check are not discarded. An interrupted
cutover is recovered from its journal on the next updater start. A failed version
is held until an operator explicitly retries it or a newer release is published.
The protocol capability is recorded during verified staging. Earlier runtimes
that predate these receipts remain valid rollback targets under their previous
readiness contract; receipt absence is never accepted for a protocol-1 runtime.

## Inspect, pause or run a check

```sh
uv run --no-sync mnemion-service updates status --state-dir "$MNEMION_MANAGED_DIR"
uv run --no-sync mnemion-service updates preferences --state-dir "$MNEMION_MANAGED_DIR" --enabled false
uv run --no-sync mnemion-service updates check --state-dir "$MNEMION_MANAGED_DIR"
uv run --no-sync mnemion-service updates stage --state-dir "$MNEMION_MANAGED_DIR"
uv run --no-sync mnemion-service updates apply --state-dir "$MNEMION_MANAGED_DIR"
uv run --no-sync mnemion-service updates preferences --state-dir "$MNEMION_MANAGED_DIR" --enabled true
```

Pausing stops automatic checks and downloads; explicit operator commands still
work. It does not interrupt an already running operation or disable journal
recovery. Commands use an exclusive local lock. A second operation reports busy
instead of starting a concurrent cutover. `apply --retry` acknowledges a previously
failed candidate; use it only after reviewing and correcting the failure.

Status includes current version, enabled preference, check interval, latest
check, pending recovery, the last 20 events and Supervisor process readiness.
`not_published` means the latest stable release has no service manifest yet;
`operator_required` means automatic compatibility requirements were not met.
`held_after_failure` means the candidate already failed its cutover.

## Storage and recovery

Managed state and records are private to the service account. Update command logs
retain a 256 KiB tail per operation; process logs rotate through Supervisor.
Logs and backups can contain private service information. Redact them before sharing.

The updater retains the **three latest verified backups it created**. It tracks
their identity and does not delete unrelated exports, replacement files or
symlink targets. Keep independent encrypted/off-host disaster-recovery backups;
three local pre-update copies are not a complete backup strategy. Copy a needed
archive outside managed retention before proceeding with more patches.

Staging removes only authenticated obsolete managed runtime slots, preserving
the active, previous and pending runtimes and any runtimes referenced by a recovery
journal. The original Python installation/checkout and the dependency cache are
retained. Model and dependency caches still need the operator's normal disk budget.

For `recovery_required`, inspect `updates/journal.json`, the bounded history and
private process logs before restarting. Do not edit runtime pointers, remove a
journal or restore an old database to force a version change. Correct the host
failure and restart Supervisor; recovery reselects the previous compatible
runtime. For actual database loss, use the separate
[verified recovery procedure](recovery.md), including deletion reconciliation.

## Authority and limits

Host updates require local operator access and private database-owner credentials.
An ordinary HTTP/MCP memory key cannot invoke this updater. The owner login is
passed only to backup operations, not to the API, worker or package installer.
All three processes still share an OS user, so this is not isolation against a
compromise of that account. Use container separation where the threat model needs it.

The [release signing policy](../CODE_SIGNING.md) governs the dedicated trust key.
No OS certificate, new online account or subscription is required. Multi-host
rollouts, migration-bearing unattended updates, Compose/Windows-server updates,
maintenance windows and fleet policy remain tracked in
[issue 11](https://github.com/Perseusxrltd/mnemion/issues/11).
