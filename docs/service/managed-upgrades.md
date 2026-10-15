# Upgrade a managed host across a schema boundary

From 4.2.4, an adopted Linux/macOS Supervisor host has an explicit, JSON-speaking
upgrade command. It stages one signed runtime, verifies a backup, stops the API
and worker, applies the checked migrations and starts the new runtime. It does
not start a second service or load a second set of embedding models for a
rehearsal. Existing organization IDs, API keys, source configuration, vaults and
database role credentials are retained.

The command also handles minor-version boundaries for older updaters. From
4.7.1, an enabled updater can apply newer minor releases in the same major series
when migrations and model generations are identical. A host using the older
patch-only policy may need this procedure once to reach 4.7.1. The automatic
path retains its verified backup, readiness and rollback checks.

Automatic compatible updates remain enabled according to the saved preference.
They never opt into a schema migration. An operator or authorized host agent
chooses the exact new version and supplies `--allow-migration` for this path.
The ordinary tenant administrator's memory key does not grant OS or database
owner access. Run these commands as the unprivileged account that owns the
[managed installation](managed-updates.md), using its original state directory.

## Plan and apply

For an installation whose command-line tools already include 4.2.4 or later:

```sh
mnemion-service updates plan --state-dir "$MNEMION_MANAGED_DIR"
mnemion-service updates upgrade --state-dir "$MNEMION_MANAGED_DIR" \
  --version 4.2.4 --allow-migration
mnemion-service updates status --state-dir "$MNEMION_MANAGED_DIR"
```

`4.2.4` is an example exact target; use the currently published version returned
by the plan. If a newer release arrives between planning and applying, the
command stops before changes and asks for a fresh plan. A plan reports the source
commit, new migration names, downtime, backup policy and the apply command. It
does not change the database or stop processes. Package staging during upgrade
can take several minutes; the existing service continues running during it.

Only newer versions in the same major version are supported here. Every applied
migration must retain its original checksum, new scripts must come after the
existing sequence, and installed/live model-generation identities must match.
A model change or major-version migration needs its own documented procedure.
No model is silently changed or re-embedded by this command.

## Existing 4.1.x and earlier managed command-line tools

An old bootstrap does not know the new `plan` and `upgrade` subcommands. Keep that
bootstrap environment and its original source path intact: they remain a
verified rollback endpoint. Use the small
[upgrade bridge](https://github.com/Perseusxrltd/mnemion/blob/main/deploy/upgrade_managed.py) from a separate current source
checkout or the published source archive, with the **existing installation's
Python**:

```sh
"$MNEMION_EXISTING_PYTHON" /path/to/current-source/deploy/upgrade_managed.py \
  --state-dir "$MNEMION_MANAGED_DIR" --version 4.2.4

"$MNEMION_EXISTING_PYTHON" /path/to/current-source/deploy/upgrade_managed.py \
  --state-dir "$MNEMION_MANAGED_DIR" --version 4.2.4 --allow-migration
```

The first command uses the old updater's existing publisher signature, archive,
lockfile and installed-byte checks to stage the candidate, then executes that
verified candidate's plan command. The second executes its guarded upgrade.
The bridge accepts no arbitrary package URL or executable, receives no
credentials on its command line, and installs no second service. The candidate
contains its own current CLI, so this also works when the original bootstrap
predates the migration feature. Continue using the bridge for later boundaries
if the original bootstrap command is still old; do not edit signed installed
packages or manually rewrite `active.json`.

`updates status` identifies the original configuration, current runtime and
processes. The original Python path is also in the installation's private
`settings.json`; do not publish that file. `MNEMION_EXISTING_PYTHON` above is a
shell variable you set to that executable, not a new Mnemion preference.

## What the command verifies and changes

1. It owns the existing managed operation lock. Enrolled connector scans hold
   shared leases, so a scan finishes before upgrade work can acquire that lock.
   A busy command returns JSON `status: deferred`, a 30-second retry hint and
   exit status 75; it does not interrupt another updater or source scan.
2. It verifies the official stable manifest, exact requested version, downloaded
   packages, dependency lock, installed files and current embedding generations.
   A stage or check alone does not make a host upgraded.
3. The saved owner, API and worker credentials must name the same database.
   The live migration ledger must still match the previous runtime. Existing disk
   admission checks and matching PostgreSQL backup tools apply.
4. It creates and verifies a database archive before stopping the running
   service. Failure here leaves the service running. It writes a durable upgrade
   journal and retains both runtimes and the backup during recovery.
5. It stops the updater, then drains the API and worker. The verified candidate
   applies its exact migration set under the database migration lock, in one
   transaction, checking the previous ledger again inside that lock. Lock and
   statement timeouts bound this operation. API and worker credentials never
   receive database-owner privileges.
6. It selects the new runtime and verifies real API/process identity and both
   initialization receipts while the updater is intentionally stopped. Only
   after the service is ready does it clear the journal and restart the updater.
   Future compatible hotfixes use that runtime automatically.

For **4.1.7 → 4.2.4**, the production addition is
`015_individual_sign_in.sql`. It retains existing keys and adds personal account
and device-session support. 4.2.4 itself adds no production migration after 015.

There is one service interruption. Other deployments writing to the same
database need coordinated maintenance too; this command controls only this
managed Supervisor instance. Available disk space remains necessary for the
candidate and verified backup even on a machine with limited RAM.

## Source connectors after cutover

Already [enrolled managed runners](managed-connectors.md) retain their connector
IDs, token files, cursor state and configuration. They select the verified active
runtime on the next scan; there is no need to issue new keys or re-enroll them.
Check each runner's `scan_version`, last successful scan and source errors in
`updates status`. A configured interval can delay the first observed new-version
scan. The upgrade result does not claim that an unobserved scan has passed.

A standalone or remotely hosted runner that was never enrolled remains owned by
its deployment. Update or enroll it using the managed-connector guide. This
command does not take over another computer or change a reverse proxy/tunnel.

## Recovery

```sh
mnemion-service updates status --state-dir "$MNEMION_MANAGED_DIR"
mnemion-service updates upgrade --state-dir "$MNEMION_MANAGED_DIR" \
  --version 4.2.4 --allow-migration --resume
```

For an older bootstrap, append `--resume` to the bridge's second command instead.
The version must match the pending journal. Resume revalidates the recorded
candidate and backup and recognizes whether the database is still at the old
schema or has already reached the target. Committed migrations are not repeated.

If the migration fails before commit and the previous schema remains intact,
the old runtime is restarted automatically. If migration committed and the new
runtime cannot become ready, the command stops the service and records
`recovery_required`; fix the reported private-log cause and resume forward.
If interrupted, the durable journal identifies the same recovery path.

**A database backup is never restored automatically.** A new API can accept a
write before another child fails its readiness check; restoring the older backup
would lose that write. Unknown schema state also requires operator recovery.
The new updater refuses ordinary automatic updates while this journal is pending.

For a separately chosen database rollback, keep the current database, upgrade
journal and backups. Use the [verified recovery procedure](recovery.md) to
restore into a separate empty target, preserving the current deletion/access
ledger and any accepted post-backup writes. Review the recovered data and access
before rerouting clients. Do not overwrite the only live database, delete the
migration ledger, or pair the old binary with a newer incompatible schema.

## Visibility and limits

`updates status` exposes `pending_update.available_version`, `operator_required`,
the concrete upgrade reasons and this guide, independently of an older
`last_check` record. A pending journal adds the target, phase and backup name.
Status is local and read-only with respect to the workspace database; it remains
available while a scan or updater holds the operation lock.

Containers, Windows-hosted services, Python/PostgreSQL upgrades, organization
maintenance-window policy and fleet rollout still use their deployment
lifecycle. Windows, macOS and Linux **desktop** upgrades are separate and retain
their existing native updater and local-workspace migration gates.
