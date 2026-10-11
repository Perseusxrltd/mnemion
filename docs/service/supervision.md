# Background service without systemd

From **4.0.7**, `mnemion-service supervise` manages the API and durable worker
through the free, pinned Supervisor 4.3.0 package. It runs as an ordinary service
account on Linux or macOS, including hosts without systemd. The API also serves
Studio and authenticated HTTP MCP. On Windows, use the background
[Compose deployment](deployment.md); Supervisor itself does not support Windows.

This manages the two application processes. PostgreSQL, TLS/tunnels and source
runners retain their own deployment lifecycle. It does not download software
updates or run migrations. For automatic compatible patches, use the
[managed setup](managed-updates.md) introduced in 4.0.8; it adds an updater child
to a new private Supervisor instance. Desktop automatic updates remain independent.

## Prepare a private instance

Complete the [database and restricted-login setup](README.md#run-the-service)
first. Prepare the model cache and, for a Git checkout, build Studio. Install the
extra in the same environment that runs the service:

```sh
uv sync --locked --no-dev --extra supervision --python 3.13
uv run --no-sync mnemion-service prepare-model
uv run --no-sync mnemion-service studio build
```

An official Python release wheel already includes Studio. When installing that
wheel, select its `supervision` extra, for example
`python -m pip install './mnemion-4.0.8-py3-none-any.whl[supervision]'`.
Use the [official downloads](https://github.com/Perseusxrltd/mnemion/releases).
The extra is optional and adds no model or paid service.
Intel Mac servers require Python 3.12 or 3.13. The package selects ONNX Runtime
1.23.2 there, the newest version publishing compatible Intel wheels; other
platforms retain their newer locked runtime. This does not change E5/BGE weights
or require a reindex. See [model compatibility](embeddings.md#native-runtime-compatibility).

From the installed environment or checkout, choose a persistent private state
directory. The shared login file produced by `mnemion-service logins` is accepted:

```sh
MNEMION_SUPERVISION_DIR="$HOME/.local/state/mnemion/service"
uv run --no-sync mnemion-service supervise prepare \
  --state-dir "$MNEMION_SUPERVISION_DIR" \
  --api-credentials .mnemion-run/database.mnemion-credentials.json \
  --worker-credentials .mnemion-run/database.mnemion-credentials.json
uv run --no-sync mnemion-service supervise start --state-dir "$MNEMION_SUPERVISION_DIR"
uv run --no-sync mnemion-service supervise status --state-dir "$MNEMION_SUPERVISION_DIR"
```

`prepare` copies only `database_url` into the API file and only
`worker_database_url` into the worker file. The database administrator login and
owner API key are not copied. The supervisor also removes common inherited
database credentials before launching either process. Files use mode 0600,
directories 0700 and the local control socket 0600. No TCP control panel is opened.
Both processes still run as the same operating-system user: database-role
separation is not isolation against compromise of that user. Use the documented
container separation when that is required.

Use `--host` and `--port` during preparation to change the loopback listener.
`--public-url https://memory.example.com` configures the external MCP origin;
it does not create a tunnel, DNS entry or TLS certificate. `--studio PATH` keeps
an explicit web build. State paths with control characters, `;` or `#` are
rejected because of Supervisor's configuration grammar. Spaces and percent
characters are supported, including in the generated cron entry.

For provider settings, pass `--environment /private/runtime.json`, containing
a JSON object of environment names and string values. Model, embedding,
librarian and selected resource settings are also captured from the preparation
environment. Do not put database logins in this file; use the role files above.
Settings and provider keys are private, not printed in command results. Changing
the login shell later does not change the saved configuration.

Preparation never overwrites different existing settings or credentials. For a
configuration change, prepare a new state directory, stop the old instance and
start the replacement. Do not share either directory publicly. Unchanged saved
configuration remains usable after a compatible package update; do not rerun
`prepare` just to update the software.

## Observe and stop

Commands return JSON so a host operator or authorized maintenance agent can use
them without a screen. `status` reports the supervisor PID, both process states
and PIDs, the bounded log directory and readiness. Readiness requires both
managed processes to be running and the HTTP response to identify that exact
API instance and PID. An unrelated listener or an orphan from an earlier start
cannot satisfy it. A timeout talking to Supervisor is an error, not proof that
the service stopped.

The API readiness endpoint checks the database and configured generation; it
does not prove indexing progress, model quality, or that all provider sources
are current. Monitor durable operation age and failures in Studio as well.

```sh
uv run --no-sync mnemion-service supervise stop --state-dir "$MNEMION_SUPERVISION_DIR"
```

`start` is idempotent for an existing supervisor. A start that has not become
ready returns exit code 2 with its current status. Unexpected API/worker exits
are restarted. Repeated failures before the two-second startup threshold exhaust
five increasing startup retries and enter `FATAL`; inspect the private logs,
correct the problem and use `stop` followed by `start`. A deliberate stop drains
both process groups, waits for completion and can be repeated safely. If stopping
cannot be confirmed, the command fails instead of authorizing a software cutover.

Logs under `STATE/logs` rotate: API and worker each keep a 10 MB file and two
backups; Supervisor keeps 5 MB plus two backups. Failed daemon initialization
retains at most 32 KiB in `startup.log`. Logs can contain private provider or
database diagnostics; redact them before sharing. The saved configuration hashes
detect edits before lifecycle commands run. Keep the exact virtual environment
and checkout path available for the boot commands.

## Linux boot with cron

`prepare` returns a `cron_entry` using absolute, quoted interpreter, checkout and
state paths. Add that line to the service account's crontab using `crontab -e`.
The host's cron daemon must be installed and enabled; this does not require
systemd. PostgreSQL and network prerequisites must become available within the
startup retry window. The generated line does not contain credentials.

Adding the entry is an explicit host configuration step; preparation does not
edit an existing crontab. Remove only that entry to disable boot startup. Cron's
`@reboot` starts Supervisor after a host reboot; it does not continuously monitor
the supervisor daemon itself. An external init system can monitor foreground
mode instead.

For runit, s6, OpenRC or another existing process manager, supervise the absolute
interpreter command `python -m mnemion.service.supervision run --state-dir STATE`
as the service account, with the prepared checkout as working directory. `run`
keeps Supervisor in the foreground so the outer manager owns its lifetime.
Run only one outer manager for a given state directory.

## macOS login with launchd

Preparation also writes a private `launchd.plist` and returns its label and path.
The file uses foreground mode, runs at login and restarts an abnormal supervisor
exit with a 30-second throttle. It uses the same rotated process logs rather
than creating an unbounded duplicate log. Inspect `run` in the foreground if
Supervisor fails before it can open those logs.

Stop a manually started instance before loading launchd. Copy the generated
plist to `~/Library/LaunchAgents/`, naming it with the returned label and `.plist`
extension, retain owner-only permissions, and load it with:

```sh
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/RETURNED_LABEL.plist"
```

Replace `RETURNED_LABEL` with the generated `launchd_label`. To disable login
startup, run `launchctl bootout` with the same domain and file, then remove that
one installed plist. A clean `supervise stop` does not trigger abnormal-exit
restart. A launch agent runs when its user logs in; a headless service before any
user login requires an administrator-managed launch daemon or another host
deployment. No system account or startup registration is changed automatically.

## Resources, upgrades and recovery

Supervisor is a process manager, not a memory or CPU isolation boundary. Use
container/cgroup limits or the host's existing service limits, and retain bounded
model/inference settings from the [resource guide](embeddings.md). Do not add
unbounded worker replicas to solve a growing queue without measuring throughput.

Before a service upgrade, keep a verified backup and deletion/access ledger,
retain the old release, and follow the patch's migration instructions. Stop both
processes, update the locked environment, build Studio when using source, apply
required migrations with separate operator credentials, then restart and verify
authorized reads and writes. Do not replace a running virtual environment.

This patch adds no database migration or reindex requirement. Upgrading from
before 4.0.5 still requires [migration 012 and its rollback procedure](../releases/4.0.5.md#server-upgrade-and-rollback).
[Managed service patches](managed-updates.md) add signed staging, backup
verification and compatible runtime rollback from 4.0.8. Fleet rollouts and
schema-changing unattended updates remain tracked in
[issue 11](https://github.com/Perseusxrltd/mnemion/issues/11).
Physical boot, site-specific cron/launchd policy and high availability require
deployment-specific verification in addition to the process-recovery tests.
