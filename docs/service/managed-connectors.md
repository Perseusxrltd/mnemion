# Managed source connector updates

From 4.1.3, a connector on an adopted Linux/macOS host can follow that host's
verified service runtime. This addresses a separately launched Git, filesystem,
Drive, Slack or rclone runner remaining on its original Python installation
after the API and worker update.

From 4.13.0, a new `updates setup` or `supervise prepare` can accept a repeated
`--connector-config /private/source.json`. Supervisor then owns those runners
alongside the API and worker. Managed instances automatically apply the verified
runtime behavior below. This also lets [host recovery](host-recovery.md) include
the registered configurations and restore their lifecycle without separate
launcher commands. Stop an older independently launched runner before starting
the new supervised instance. Provider authorization and source bindings remain
explicit; registering a process grants no new source permissions.

Keep the existing connector ID, configuration, token references, source cache
and identity mappings. Stop the previous runner through its existing process
manager, then start one managed runner:

```sh
mnemion-connect --config /private/connector.json --watch \
  --managed-state /private/mnemion-managed-service
```

The launch command requires Mnemion 4.1.3 or newer. Keep its bootstrap Python
installation at a stable path outside `updates/releases/`; old release slots
are eventually cleaned up. Point the host's normal startup/service entry at
this command, with its normal bounded log rotation. `--managed-state` selects
an existing [managed service](managed-updates.md), not a new workspace. It does
not create a system service, change source permissions or restart unrelated
processes. Use a private regular configuration file owned by the service account
(mode 0600). Relative paths keep their original meaning.

The runner takes a fresh, consistent configuration snapshot for each scan. Token
files remain references and can rotate. An explicit `MNEMION_API_KEY` token
reference is supported; unrelated API/owner credentials and all database-role
variables are removed from scan and launcher-handoff environments. Git/SSH,
proxy and explicitly configured provider authentication remain available.

<a id="retained-inbox-environment-references-unreleased"></a>

## Retained inbox environment references

Mnemion **4.45.0 or later** lets a registered Linux/macOS Supervisor connector
pass an explicit `capture.inbox_key.env` reference alongside its service/provider
credential references. For example, use `{"env":"MNEMION_CAPTURE_INBOX_KEY"}`
for `capture.inbox_key` in the [headless configuration](headless-capture.md#prepare-the-approved-source-and-private-files).
The value comes first from the Supervisor's private environment settings,
otherwise from its process environment when the child launches. Key values
remain outside the connector configuration.

Missing environment references and reserved names are refused before the
connector executes. This includes `MNEMION_ADMIN_DATABASE_URL`,
`MNEMION_VAULT_KEY` and `PYTHONPATH`; the existing role and loader restrictions
remain in force. The correction does not inherit arbitrary credentials or
database-role variables. File references and their normal reload behavior are
unchanged.

The [Supervisor source checkpoint](../research/2026-10-21-durable-capture-implementation.md#supervised-headless-inbox-key-forwarding)
preserves the key-forwarding and process-restart evidence. See
[current installed qualification](../research/2026-10-21-durable-capture-implementation.md#current-installed-qualification) and
[candidate acceptance and remaining scope](../research/2026-10-21-durable-capture-implementation.md#required-before-l1-can-be-released) for release readiness.

Register each connector explicitly through the existing `--connector-config`
setup and retain the host's startup arrangement. This does not add independent
Windows supervision, boot registration or update management. These controls are not included in **4.44.2**; check [published availability](../RELEASE_STATUS.md)
before selecting a runtime.

## Update and recovery behavior

Each scan starts a separate process from the current runtime, after rechecking
the official service signature, immutable staging record and installed package
bytes. The scan holds a shared update lease; other managed connectors can scan
concurrently, while runtime replacement and cleanup wait. A live updater asking
for access pauses new scans and retries in about 30 seconds. Existing scans
finish normally. This prevents continuous ingestion from starving an update.
An abandoned pause expires and also requires a matching live process identity.

Mirror scans wait while the service is unavailable. The
[headless retained-capture mode](headless-capture.md) can accept selected evidence
locally during a service outage when its verified runtime advertises capture
protocol 1. All modes still wait through update journals and runtime transitions;
an older runtime explicitly refuses a retained configuration.
After cutover, the next scan uses the new version. After rollback, it uses the
verified restored version. Future runtimes that advertise managed-launcher
protocol 1 also replace the launcher between scans. Older rollback runtimes
can still execute their ordinary one-shot scanner without that protocol.

The existing polling interval, configuration reload, **Sync now** requests,
source access leases, idempotency and complete-inventory deletion rules remain.
The host keeps one managed launcher per connector ID. The scan child inherits
the singleton and runtime leases, so an interrupted launcher cannot start a
competing replacement while that child still runs. An ordinary operator stop
drains the scan and its observed provider subprocesses. An interrupted inventory
does not authorize a deletion sweep; its existing server lease remains the
recovery boundary.

## Observe the runner

```sh
mnemion-connect --version
mnemion-service updates status --state-dir /private/mnemion-managed-service
```

The status command's `connectors.items` includes the connector ID, current
launcher version, latest scan version, observed state, process liveness and last
exit code. It excludes provider URLs, source paths, tokens and memory content.
Process identity checks distinguish a stopped process from an unrelated reused
PID. `scan_version` describes the most recent scan, so it can lag during the
normal interval before the next scan. A surviving child whose launcher exited
appears as `orphan_scan` until it finishes.

From 4.3.2, a completed Git scan also records `scanned_commit` and `scanned_at`
in `connectors.items`. This is the scanned repository snapshot, distinct from
each file's last-change commit. The parent accepts a private, bounded receipt
only from the just-completed process with the matching connector and runtime.
A failed attempt retains the previous successful observation and reports its
nonzero exit code. A successful older runner without receipts clears the commit
observation; an old receipt is never reused. These local observations are
independent of the service's [durable complete-inventory checkpoint](connectors.md#git-snapshot-freshness).

Ordinary scan reports include `runner_version`. Plain `--watch` also states
`update_mode: "manual"` at startup. The host status explicitly reports that it
does not inventory unmanaged processes. A connector running on another machine
needs its own deployment/update ownership; a memory-service URL or API key
does not grant control of that machine. Windows/Compose fleet management and
app-based host enrollment remain on the [roadmap](../ROADMAP.md).

From 4.1.6, managed scans retain their reason across the one-shot scanner
boundary: `startup` for the first scan, `poll` for the normal interval and
`requested` for **Sync now**. Waiting for an update or handing the launcher to
the next compatible runtime preserves the pending reason. Older restored
scanners can still run; their older logging behavior may report `startup`.

There are at most 64 managed connector registrations per host. Stop a retired
runner before removing only its corresponding private
`updates/connectors/<connector-id>` directory. This local bookkeeping does not
disable the registered source, remove memory or change permissions in the server.
Use the normal connector controls for those changes.
