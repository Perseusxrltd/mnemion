# Control an adopted company host

**Available in the published 4.46.5 desktop.** Host controls and native-agent
actions passed [all six installed targets](../validation/2026-10-23-4465-native-acceptance.md),
the [actual Windows/shared-host update](../validation/2026-10-23-4465-live-acceptance.md)
and the [retained-custodian lifecycle](../validation/2026-10-23-4465-custody-acceptance.md).
The [fresh encrypted backup and separate verification](../validation/2026-10-24-4465-backup-acceptance.md)
passed at **00:01:45 UTC on 24 October**. Independent restore remains pending.

Earlier qualification is retained below. In 4.46.3, host controls, native agent
actions and backup approval controls passed
[installed qualification on all six targets](../validation/2026-10-23-4463-native-acceptance.md).
All six public automatic-update targets subsequently passed, verified at
**15:03 UTC on 23 October**. The actual Windows/shared memory-service pair
[passed at 15:54:32 UTC](../validation/2026-10-23-4463-live-acceptance.md), preserving
identities, exact sampled data and protected login/preferences, with 42 lab
requests and complete cleanup. The separate
[two-custodian host-control journey passed at 16:25:34 UTC](../validation/2026-10-23-4463-custody-acceptance.md):
both original custodians inspected while memory was down, deliberate stop
survived a manager restart and two scheduled watchdog ticks, and the original
service restarted with retained access and data. Fresh backup delivery and
independent restore were unaccepted at that historical checkpoint.

The earlier 4.46.1 release passed all six public installed-update targets. Its
actual Windows/shared Linux pair passed
[live acceptance at 09:55:28 UTC on 23 October](../validation/2026-10-23-4461-live-acceptance.md)
and remains a preserved earlier checkpoint.
The earlier [canonical-host setup](../validation/2026-10-23-independent-host-adoption.md)
passed native adoption, backup configuration, OS integration and two protected
custodian enrollments. **Its operational journey failed at the first stop,
before any effect.** Full recovery acceptance and fresh native backup
delivery/restore were unproven at that checkpoint. The
[interruption history](../validation/2026-10-23-4461-live-interruption.md)
preserves the stopped update attempts. Use
[release status](../RELEASE_STATUS.md) for current package availability and
the [qualification section](#qualification-and-remaining-work) for evidence limits.

An adopted host has a separate controller, operator authority and durable
operation store. An authorized person or agent can inspect or resume its memory
service even when the memory API and the agent that originally installed it are
unavailable. The controller runs under the host's service account, independently
of the memory service's Supervisor instance.

| What is unavailable? | What this interface can do |
| --- | --- |
| Memory API or its worker, with the controller reachable | Inspect host state and submit an approved service start, stop or guarded upgrade. |
| Controller listener | The OS owner can inspect and start it through the separate local lifecycle commands. Remote requests cannot reach a stopped listener. |
| Whole computer, network route or hosting provider | Use separately authorized OS/provider recovery. This protocol cannot wake a powered-off machine or restore its network. |
| Original host and its disks | Independently held backups, keys and a replacement-host recovery procedure are required. This controller is not a replica or a provider provisioning service. |

## Authority and supported installations

Initial adoption supports an existing **managed Supervisor service on Linux or
macOS**, under its **unprivileged service account**. It rejects root adoption and
unmanaged services. Windows/Compose server adoption is not implemented by this
path. See [supervision](../service/supervision.md) and
[managed updates](../service/managed-updates.md) for the prerequisite installation.

Published desktop clients cover Windows, macOS and Linux on x64 and ARM64.
Windows ARM64 uses the tested x64 engine/database emulation with an ARM64
desktop. The client transport uses the bundled AsyncSSH library rather than
invoking a local `ssh` executable. A source checkout still needs a compatible
Python installation and the project's dependencies.
The host's backup delivery separately requires Git and its configured transport.

Host grants are separate from memory access. A workspace API key, personal login,
organization administrator role or cached desktop account cannot adopt a host
or authorize these operations. Host actions can interrupt the **whole adopted
service and database**, including every organization using it.

Each enrollment uses a separately held **Ed25519 private key**:

| Host role | Current authority |
| --- | --- |
| `observer` | Read host status and permitted operation lookups/lists. |
| `operator` | Observer actions, service start/stop, backup creation/verification on compatible hosts, signed upgrade planning and approved application. |
| `custodian` | Operator actions, enrollment/revocation, inspection of other operators' receipts and explicit resolution of uncertain work. |

Published **4.46.3** adds [backup creation and verification](#create-and-verify-retained-backups)
for operators and custodians. Observers cannot request these transfers; older
hosts advertise neither backup action.

Non-custodians can retrieve only their own operation receipts. Host status still
reports aggregate operation counts. The first custodian must have no expiry.
Enroll another independently held permanent custodian before retiring the last
one; concurrent changes cannot remove the final permanent custodian.

The OS owner retains authority over the machine. These grants do not isolate the
controller from that OS account. The CLI includes a strictly local
[custodian recovery command](#recover-custodian-authority-as-the-os-owner) with
focused source checks; production recovery remains unqualified. There is no
implemented bind/address-change procedure. Do not delete the authority store,
change saved pins or rerun adoption with a new key as a recovery shortcut.

## Discover the host-control interface

On a compatible service installation, use its `mnemion-service` command:

```sh
mnemion-service host-control capabilities
mnemion-service host-control schema
```

The equivalent source entry point is `python -m mnemion.host_control.cli`.
`capabilities` identifies protocol/store compatibility; `schema` gives the typed
remote requests, connection fields, role/action mapping and separate
`local_owner_recovery` schema. Neither output proves a production adoption or
installed-client qualification.

Version 4.46.0 uses **authority-store format 2**; the remote protocol
remains version 1. Experimental format-1 authority state is refused, not silently
migrated or reset. Preserve it for owner inspection rather than deleting it to
repeat adoption. The [23 October canonical-host record](../validation/2026-10-23-independent-host-adoption.md)
confirms native adoption and preserves the later failed first service stop.

The examples use Unix shell redirection and placeholder paths. Create private,
owner-only parent directories first. Replace uppercase JSON placeholders with
the actual observed values; they are not ready-to-send identifiers or timestamps.
An agent should invoke an executable with a separate argument array and write
one UTF-8 JSON request to stdin, rather than constructing a remote shell command.

## Create a custodian and adopt the actual host

The desktop's [Create host login](#use-the-desktop-app)
flow can generate the first custodian's key and public enrollment. Select
**Custodian** as the requested role. Alternatively, on a CLI custodian's own
computer, generate a new private key:

```sh
mnemion-service host-control keygen --output /private/company-custodian.key
```

The command writes the private key to a new protected file and prints only its
`public_key` and `fingerprint`. Keep the private key on the custodian's device
and in its approved independent custody. Give the host owner a private JSON file
containing the **public** enrollment, for example `/private/first-custodian.json`:

```json
{
  "name": "Primary company host custodian",
  "public_key": "PUBLIC_KEY_FROM_KEYGEN",
  "role": "custodian",
  "expires_at": null
}
```

Use the complete `ssh-ed25519` public-key string returned by `keygen`, without
SSH options or a comment. Do not send the private key to the host to adopt it.

On the host, choose a new controller directory **outside** the actual managed
service state. Neither directory may contain the other. The active managed
runtime must already implement this protocol; adoption probes its
compatibility and does not install a new runtime.

Choose the listener and advertised address **before the first adoption**. This
example explicitly approves an IPv4 network listener:

```sh
mnemion-service host-control adopt \
  --state-dir /private/company-control \
  --service-state /private/mnemion-service \
  --operator /private/first-custodian.json \
  --bind 0.0.0.0 --port 7893 \
  --advertised-host control.example.net \
  --approve-network
```

Replace `control.example.net` with the address operators can actually reach.
The OS owner must separately approve and provide the firewall/network route.
Adoption does not configure DNS, a provider route, TLS or a tunnel. For a local
listener, choose `--bind 127.0.0.1 --advertised-host 127.0.0.1` instead and omit
`--approve-network`. Non-loopback binding requires that explicit approval; the
supported saved port range is 1024–65535. These are alternatives for initial
adoption, not a procedure for changing an existing listener.

Review firewall access for the host-control TCP port, **7893 by default**,
separately from ordinary OS SSH. This listener uses enrolled keys and exact
server pins; it offers no password login, shell or forwarding. Allow only the
network access approved by the host owner.

Standard UFW `limit` rejects the sixth connection from one source IP within
30 seconds. A successful desktop inspection opens **two or three short pinned
SSH sessions**, and the visible host view polls every **15 seconds**. Several
people behind one public IP can therefore hit an ordinary SSH-login limit
during normal use. Use reviewed allow rules for approved sources or a rate
policy sized for that connection pattern; keep OS SSH access rules separate.

Adoption **prepares** the controller. A matching repeat returns
`already_prepared`; it preserves the existing host identity and grants. A
different adoption is refused rather than resetting authority.
Initial adoption records whether the existing memory service is running or
stopped. It does not start a stopped service.

Save only the returned **`connection` object** as the operator's protected
connection file, for example `/private/company-host-connection.json`. It binds
the host and operator UUIDs, address/port, host-key algorithm/fingerprint and
operator-key fingerprint. Verify those pins with the OS owner through an
independent trusted channel. The protocol username is `mnemion`; it does not
grant an OS login.

The host generates a separate Ed25519 server key. A changed server fingerprint
requires owner investigation. Do not accept a replacement key automatically or
disable host verification. The restricted listener accepts only this typed
protocol: no shell, arbitrary command, PTY, file transfer or forwarding is offered.

## Start the controller and inspect startup separately

These are local **OS-owner** commands:

```sh
mnemion-service host-control start --state-dir /private/company-control
mnemion-service host-control status --state-dir /private/company-control
mnemion-service host-control startup --state-dir /private/company-control
```

Check both `running` and `ready`. Readiness checks the actual controller process
identity and its bound-listener receipt. It does not prove that the memory API
or an external network route works.

`startup` returns a suggested cron entry, launchd file/label and boot command.
It reports `registered: false` and `registration_checked: false`: it **does not
register or verify boot/login startup**. The OS owner must review and register
the appropriate mechanism separately, then exercise an actual restart.

`host-control stop --state-dir /private/company-control` stops the controller
listener. It is different from the remote `service.stop` action below. Stopping
the listener or closing a client connection does not cancel already committed,
detached work; inspect operation receipts before controller maintenance.

## Preserve approved stops in OS supervision

The controller saves a desired memory-service state, `running` or `stopped`,
separately from observed process readiness. A start, stop or reviewed upgrade
changes this intent only when it reaches its guarded effect after checking
current authority. Queuing a request does not change it. An explicit custodian
resolution records the accepted observed state. The decision survives receipt
pruning and later operator revocation; it is not an expiring operation receipt.

The OS owner must integrate this policy before relying on remote stop controls.
An existing unconditional startup job or external watchdog can otherwise restart
the service after an approved stop. Inspect the local policy with:

```sh
mnemion-service host-control service-policy --state-dir /private/company-control
```

The result reports `desired`, its `operation_id` and `changed_at`, plus
`pending_work`, `recovery_required`, `start_needs_inspection` and
`automatic_start_allowed`. This read is a snapshot, not permission for a later
independent restart command. Errors never authorize a restart.

`startup` supplies arguments for the copied stable launcher. It resolves the
verified current controller runtime, avoiding a hardcoded package path:

| Startup field | OS-owner use |
| --- | --- |
| `memory_supervisor_arguments` | Run foreground `memory-run` as the memory service's outer OS job. It stays alive while memory is deliberately stopped. |
| `service_policy_arguments` | Run the read-only `service-policy` observation. |
| `memory_repair_arguments` | Run `memory-repair` for automatic watchdog repair. It rechecks policy while holding both the host-worker and memory-update locks. |
| `memory_launchd_file`, `memory_launchd_label` | Review the generated, hashed memory launchd job. It has not been installed or registered. |

The policy and repair launcher modes do not consume controller fallback attempts.
Pending work, an interrupted migration or an unconfirmed automatic start defer
automatic starting. The manager records start/repair intent before effects;
subsequent observations can confirm the original start without replaying it.
Otherwise inspect the host and explicitly approve a new start if needed.

Before adoption is accepted operationally, the OS owner must:

1. Replace the existing unconditional memory job with the returned memory
   launcher arguments under the reviewed service account and bootstrap working
   directory. Keep one outer memory job; do not add a duplicate alongside it.
2. Register the independent controller separately using its reviewed startup
   instructions. A running memory job does not prove controller boot registration.
3. Configure every external watchdog to invoke `memory_repair_arguments`.
   Checking policy and then calling `systemctl restart` leaves a race with an
   approved stop and is not a supported repair path.
4. Give the memory job the official supervision stop action for `ExecStop` or
   its OS equivalent: `mnemion-service supervise stop --state-dir /private/mnemion-service`,
   using the installed executable and actual memory state. Stopping only the
   foreground wrapper does not stop the managed memory Supervisor.

Inspect pending operation receipts before OS maintenance. Preserve detached
guarded work and update custody; stopping the outer manager must not kill that
work or substitute process-tree termination for the official stop action.

Review [supervision](../service/supervision.md), then qualify the actual
registration and restart behavior. `registered` and `registration_checked`
remain false; these commands install no OS jobs. A separately performed
[OS integration completed on 23 October](../validation/2026-10-23-independent-host-adoption.md).
Its original 4.46.1 journey failed before the first stop took effect. The later
[4.46.3 custody acceptance](../validation/2026-10-23-4463-custody-acceptance.md)
verified approved-stop preservation through a manager restart and two actual
scheduled watchdog ticks. Whole-machine boot/login behavior remains unproven.

## Use the desktop app

Open **Host controls · manage a company server** before signing in, or
**Host controls** in the workspace sidebar. Both open `/hosts`; a memory account,
selected workspace or working memory API is not required. An ordinary browser
shows **Use the desktop app for host administration** instead of opening the
independent SSH connection. This page is included in the published 4.46.0
desktop; a compatible adopted host is required for remote operations.

1. Under **Host logins on this device**, enter **New device or agent name** and
   choose **Create host login**. The app generates a fresh Ed25519 key and seals
   its private identity using the OS secure-store integration. Creation and use
   require that store to be available. Public profile results never contain the
   private key. The [six-platform native journey](../validation/2026-10-23-4460-native-acceptance.md#packaged-independent-host-controls)
   verified protected key reuse after a full app restart; both Linux targets
   also passed the journey with a required real OS keyring.
2. Choose **Requested role**, then **Copy public enrollment**. Give that public
   document to the OS owner for first adoption, or to an existing custodian for
   an additional login. A requested role grants no authority by itself. The
   first adopted custodian must be permanent.
3. For an additional login, the custodian opens **Host access → Add another
   device, person or agent**, pastes **Their public enrollment document**, chooses
   **Approved role** and any **Access expiry (optional)**, and confirms the
   recipient and role before **Grant host access**. The custodian sends the
   resulting **Copy host connection** document to the new operator. Initial
   adoption instead returns this connection from the OS-owner CLI.
4. Verify the host and server fingerprint with its owner through an independent
   trusted channel. Paste the returned object into **Host connection from your
   custodian**, check **I verified this host and server fingerprint with its
   owner**, and choose **Save host connection**. This validates and saves the
   local key/pin binding; it does not prove the remote host accepted the login.
5. Use **Refresh** for the separate live check. Read **Your current role**,
   **Memory service**, **Installed version** and **Last observation**. A saved
   profile or requested role is not current host authority. Inspect **Verified
   connection details** when checking the host, operator and key fingerprints.

The app also shows the saved stop decision. It flags a service running despite
that decision, or an automatic start that could not be confirmed. The former
requires owner inspection of startup/watchdog settings; the latter requires
inspection before approving another start. These observations do not replace
the [OS supervision setup](#preserve-approved-stops-in-os-supervision).

The app keeps up to 32 saved host logins. Each new device or agent gets a new
enrollment. Private-key export/import is intentionally absent; copying a public
enrollment document is not a key backup or a portable login. A saved connection
cannot silently be rebound to another host or key.

After successful inspection, the host's current role determines the controls:

| Task | Desktop workflow |
| --- | --- |
| Start or stop memory | Approve the host's service change and possible interruption, then use **Start memory service** or **Stop memory service**. A pending migration requires its recovery path. |
| Update or resume an interrupted update | Choose **Review available update**. Review the target, source, expiry and backup requirement; explicitly approve interruption before **Apply this update** or **Resume this update**. Observe its operation receipt. |
| Create an independent backup — 4.46.3 | In **Independent backups**, review the owner-configured storage and limits, approve the encrypted transfer and choose **Create encrypted backup**. |
| Inspect or verify a retained copy — 4.46.3 | Read the inventory and **Recovery details**. Approve the transfer and choose **Verify stored copy** for a fresh readback. |
| Inspect work | Use **Operation history**, **Latest**, **Inspect** and **Older operations**. **Inspect saved request** checks this device's original request. |
| Reconcile a lost reply | **Awaiting acknowledgement** retains the exact request. Inspect it first; **Retry the same request** resends that body only while its original approval is valid. It does not create a replacement UUID. |
| Resolve uncertain effects | A custodian inspects **Needs inspection**, chooses **Recovery action**, confirms the observed state and uses **Accept inspected state**. Stopping first also requires interruption approval. A pending migration uses the update recovery path instead. |
| Retire access | In **Host access**, refresh the identities, select **Revoke**, and confirm **Revoke this identity**. This changes host authority; removing a device's saved login is a separate local action. |

The open page observes enrolled hosts every 15 seconds while visible and idle.
Closing it does not cancel host work. See the
[receipt and recovery rules](#recover-a-lost-reply-or-interrupted-operation)
below before repeating an operation. **Accept inspected state** resolves uncertain
work; lost custodian authority requires another custodian or the local OS-owner
procedure.

To remove a saved key, open **Remove this login from this device**, confirm the
local removal and choose **Remove saved login**. Have a custodian revoke the host
grant separately if it should lose access. If the login has unfinished work,
explicitly acknowledge retaining its public recovery request before removal.
The app archives the exact request and public host/profile identity before
deleting the saved key, even when that login can no longer reach or authenticate
to the host. Removing it neither revokes authority nor cancels remote work.

For **Awaiting acknowledgement** or **Needs inspection**, the app also offers
**Keep this recovery record and clear the local pending request**. Read its
acknowledgement before **Keep recovery record**. This keeps the key but archives
the uncertain request before clearing the device's pending slot. It does not
resolve uncertainty on the host or authorize repeating the effect. A new recovery
plan/application or resolution also archives any earlier unfinished request
before replacing the local slot.

Find these records under **Retained recovery requests** and use **Copy recovery
document** to give the original host/operation identity to a current custodian.
The document includes the public connection and exact request, not the private
key; keep its company metadata in an appropriate private location. Its
`original_outcome: "unconfirmed"` is not a completion receipt or a new grant.
The local inventory is bounded to 128 records with a 24 KiB read limit per record.
Full storage refuses additional archives while preserving existing evidence;
there is currently no archive-pruning action, and exporting alone does not free
capacity. Focused source checks cover these archive and refused-replay paths;
the six installed journeys also passed acknowledgement, public-request
archiving and local-key removal with the retained record visible in the UI.

## Use a saved host login from a local agent

The same desktop controller is available through the existing
[native desktop operator interface](../service/desktop-operator.md). Keep the
desktop app running under the same OS account. Use the app's copied executable
and argument array; for a source installation, send one JSON object on stdin to:

```sh
mnemion-service desktop-control < /private/desktop-host-action.json
```

Discover `catalog` and `host.schema` before constructing requests. These host
actions do not require a selected workspace or `expected_workspace_id`:

| Desktop action | Input and result |
| --- | --- |
| `host.profiles` | No input. Returns `secure_storage` and public `profiles`, including saved connections and the last request. |
| `host.schema` | No input. Returns typed remote request/connection schemas and the role/action mapping. Local OS-owner recovery is a separate CLI schema. |
| `host.create` | `name`. Creates a protected key and returns its public profile, including local `id`, `public_key` and `fingerprint`. |
| `host.enroll` | `id`, complete `connection`, `confirm: true`. Validates and seals the local binding after independent pin review; does not make a live request. |
| `host.inspect` | `id`. Checks live status, permitted history and the saved operation, returning separate `status`, `history` and `operation` receipts. |
| `host.request` | `id`, typed `request`. Sends the same permitted host operation used by the UI, retaining state-changing intent before transmission. |
| `host.forget` | `id`, `confirm: true`; unfinished work also requires `acknowledge_outstanding: true`. Archives that public request before deleting the saved key. Does not revoke or cancel on the host. |
| `host.request.archive` | Profile `id`, `confirm: true`. Archives unfinished work and clears the local pending slot while retaining the key. Does not settle the host's operation. |
| `host.recoveries` | No input. Returns bounded `records` with archive IDs and public host/operation metadata. |
| `host.recovery` | Archive `id` from `host.recoveries`. Reads the exact retained public profile/request document without using a saved private key. |

For example, create the agent's protected profile:

```json
{"action": "host.create", "input": {"name": "Company operations agent"}}
```

Construct its public enrollment from the returned name and public key and the
reviewed requested role, as in the adoption example. After the custodian returns
the connection, enroll that **local profile ID**:

```json
{
  "action": "host.enroll",
  "input": {
    "id": "LOCAL_PROFILE_UUID_FROM_HOST_CREATE",
    "connection": {
      "host_id": "HOST_UUID_FROM_CUSTODIAN",
      "operator_id": "OPERATOR_UUID_FROM_CUSTODIAN",
      "hostname": "control.example.net",
      "port": 7893,
      "username": "mnemion",
      "host_key_algorithm": "ssh-ed25519",
      "host_key_fingerprint": "HOST_FINGERPRINT_VERIFIED_WITH_OWNER",
      "operator_key_fingerprint": "THIS_PROFILE_FINGERPRINT"
    },
    "confirm": true
  }
}
```

Replace the example address/port and every identifier with the exact returned
connection. Then make the live check:

```json
{"action": "host.inspect", "input": {"id": "LOCAL_PROFILE_UUID_FROM_HOST_CREATE"}}
```

For subsequent work, `input.request` is the full host request shown in the
[protocol examples](#send-requests-and-distinguish-acceptance-from-completion),
for example a read-only status request:

```json
{
  "action": "host.request",
  "input": {
    "id": "LOCAL_PROFILE_UUID_FROM_HOST_CREATE",
    "request": {
      "protocol": 1,
      "host_id": "HOST_UUID_FROM_CONNECTION",
      "request_id": "NEW_HOST_REQUEST_UUID",
      "action": "host.status"
    }
  }
}
```

The profile ID, host ID and operator ID are different identities. The outer
desktop transport request ID is also distinct from the inner host `request_id`,
which names durable host work. Preserve that inner ID and exact payload across
reconnects. The desktop saves the last state-changing request before sending it;
an interrupted connection does not authorize automatic replay or a new operation.

Check both envelopes: outer desktop `ok` means the local action completed;
`host.request` returns the host's own `ok` inside `result`. An accepted queued
operation still needs its final receipt. For `host.inspect`, inspect each
returned receipt's `ok`; absent history or operation data is not proof that work
completed. Neither the agent nor renderer receives the saved private key.

The [backup examples below](#create-and-verify-retained-backups)
use this same `host.request` envelope for typed `backup.create` and
`backup.verify` requests. They are not separate desktop action names.

For example, explicitly forget a revoked login whose last operation remains
unconfirmed while preserving its request:

```json
{
  "action": "host.forget",
  "input": {
    "id": "LOCAL_PROFILE_UUID_TO_REMOVE",
    "confirm": true,
    "acknowledge_outstanding": true
  }
}
```

Use `host.recoveries` and then `host.recovery` to save the retained document.
A currently authorized custodian inspects its original operation using their
own profile and `operations.get`; the archive ID is not the host operation UUID.
An unavailable or pruned host receipt leaves the original outcome unconfirmed.
Do not resubmit the archived effect under a fresh UUID merely to clear that gap.

## Send requests and distinguish acceptance from completion

On an enrolled operator's computer, save a request as a private JSON file:

```json
{
  "protocol": 1,
  "host_id": "HOST_UUID_FROM_CONNECTION",
  "request_id": "NEW_REQUEST_UUID",
  "action": "host.status"
}
```

Then send it through the pinned connection:

```sh
mnemion-service host-control call \
  --connection /private/company-host-connection.json \
  --identity /private/company-custodian.key \
  < /private/host-request.json
```

The response binds `protocol`, `host_id`, `operator_id` and `request_id` and
contains `ok`, `result` and `error`. Inspect **`ok` as well as the process exit
status**: receiving a valid remote rejection can still complete the CLI call.

`host.status` returns current host authority in `result.revision`,
`result.operator` and `result.actions`. Its `result.service` includes readiness,
active version, recovery requirement, operation counts, backup observations and
controller runtime state. A reachable controller with a stopped memory service
is distinct from a connection failure.

Every new state-changing request needs a new UUID and current, timezone-aware
`issued_at`/`valid_until` values. The approved window must be positive and no
longer than **one hour**. Expired approvals are refused; a device clock more than
five minutes ahead is also rejected. For example, an approved service start is:

```json
{
  "protocol": 1,
  "host_id": "HOST_UUID_FROM_CONNECTION",
  "request_id": "NEW_OPERATION_UUID",
  "action": "service.start",
  "issued_at": "CURRENT_UTC_TIMESTAMP",
  "valid_until": "APPROVAL_EXPIRY_WITHIN_ONE_HOUR",
  "approve_service_interruption": true
}
```

`service.stop` uses the same fields and approval. Set an approval only after the
authorized person has approved that host, action and interruption. The protocol
does not authorize unattended disruption merely because a key can sign in.

Queued actions return an operation whose **`operation_id` equals the original
`request_id`**. An `ok: true` response with `phase: queued` is an accepted intent,
not successful service recovery. Observe it using a new lookup request:

```json
{
  "protocol": 1,
  "host_id": "HOST_UUID_FROM_CONNECTION",
  "request_id": "NEW_LOOKUP_UUID",
  "action": "operations.get",
  "operation_id": "ORIGINAL_OPERATION_UUID"
}
```

Read `result.phase`, `result.error` and `result.result`. Use `operations.list`
with `limit` and `offset` to find retained receipts; follow `next_offset`.

## Delegate and retire host operators

A custodian first reads `host.status` or `operators.list` and uses the current
host authority **`revision`**, not the nested operator revision. Each new person
or agent generates its own fresh key. The following template grants an operator;
replace the example `expected_revision: 1` with the observed integer:

```json
{
  "protocol": 1,
  "host_id": "HOST_UUID_FROM_CONNECTION",
  "request_id": "NEW_GRANT_UUID",
  "action": "operators.grant",
  "issued_at": "CURRENT_UTC_TIMESTAMP",
  "valid_until": "APPROVAL_EXPIRY_WITHIN_ONE_HOUR",
  "expected_revision": 1,
  "operator": {
    "name": "Operations agent",
    "public_key": "NEW_OPERATOR_PUBLIC_KEY_FROM_KEYGEN",
    "role": "operator",
    "expires_at": null
  }
}
```

Choose `observer` for status-only access, or a future timezone-aware
`expires_at` for a temporary grant. A second permanent custodian uses
`role: "custodian"` and `expires_at: null`. Enrollment is not an edit of an
existing key's role: a reused key is refused.

The result returns the new `operator_id`, key `fingerprint` and authority
`revision`. Give the new operator a connection object retaining the verified host
pin, with that operator ID and its own key fingerprint. Its private key remains
on its device.

To retire an enrollment, send `operators.revoke` with the common timed fields,
the freshly observed `expected_revision` and `operator_id`. Do not include the
grant's `operator` object. Revocation is durable, cancels that operator's queued
work and is rechecked for later requests and before guarded effects. It does
not interrupt committed migration recovery or undo completed work. An expired
or revoked grant cannot be restored from an offline memory-role snapshot.

## Recover custodian authority as the OS owner

This **local command** has passed three focused source owner-recovery checks;
it has not qualified production recovery. Use it only as the owning OS account
on an existing adopted host with intact protected controller state. It needs no
old operator key, memory API or remote controller connection. It cannot restore a lost disk or
authority store, change the listener address, or recover an app's private key.
The action is absent from the remote request union and `host.request`.

Read the current local authority first:

```sh
mnemion-service host-control owner-status --state-dir /private/company-control
```

Record `host_id`, the host's current `revision`, operator IDs and
`server_fingerprint`. Generate a fresh key on the replacement custodian's device
using **Create host login** or the CLI `keygen` flow. Obtain only its public
enrollment; an existing or previously retired key cannot be reused.

Review the `local_owner_recovery` schema from `host-control schema`, then save a
private request file such as `/private/recover-custodian.json`. This example
retains all existing grants; replace `expected_revision: 1` with the observed
integer and all identity/time placeholders with current values:

```json
{
  "protocol": 1,
  "host_id": "HOST_UUID_FROM_OWNER_STATUS",
  "request_id": "NEW_LOCAL_RECOVERY_UUID",
  "action": "owner.custodian",
  "issued_at": "CURRENT_UTC_TIMESTAMP",
  "valid_until": "APPROVAL_EXPIRY_WITHIN_ONE_HOUR",
  "expected_revision": 1,
  "operator": {
    "name": "Replacement company host custodian",
    "public_key": "FRESH_REPLACEMENT_PUBLIC_KEY",
    "role": "custodian",
    "expires_at": null
  },
  "retire_operator_ids": [],
  "approve_authority_recovery": true
}
```

The replacement must be a **permanent custodian**. If specific lost or retired
identities should lose access, explicitly list their observed UUIDs in
`retire_operator_ids` before approval; up to 128 distinct existing IDs are
allowed. Unlisted grants remain intact. This is an approved authority change,
not a reset of the host. Selected retirements cancel queued work but do not undo
committed effects.

Apply the reviewed local request:

```sh
mnemion-service host-control recover-custodian \
  --state-dir /private/company-control \
  --request /private/recover-custodian.json
```

The result includes `recovered`, the new `revision`, `operator_id`, selected
`retired_operator_ids` and the replacement's `connection`. The original host
identity and server pin are preserved. Keep the exact request and result; an
identical UUID/payload returns its recorded result, while a changed payload under
that UUID is refused. A stale revision or expired new approval requires fresh
inspection before a new request.

Run `owner-status` again and compare the authority and unchanged server pin.
Give the returned connection to the fresh-key device, complete local enrollment,
then use **Refresh**, `host.inspect` or a CLI `host.status` request for live access
verification. Local authority recovery alone does not prove reachability or
service readiness. Independent controller-authority custody remains necessary
for loss of the host or its protected state.

## Configure encrypted Git backups and independent key custody

An upgrade requires an OS-owner-configured remote backup destination and a
separately held recovery key. These are distinct from the controller's host key,
operator keys and the Git server's own SSH identity.

Create a host-package encryption key through the existing recovery interface:

```sh
mnemion-service host key --output /private/company-recovery.key
```

Use the returned `key_id`. Keep a protected copy outside both the original host
and its backup destination, with an independently usable recovery process.
The host needs its own protected copy to encrypt backups. A confirmation flag
does not prove another person can retrieve the key after losing this machine.

An example `/private/company-backup.json` using a private HTTPS Git destination is:

```json
{
  "format": 1,
  "destination": {
    "remote": "https://git.example.net/company/host-backups.git",
    "token_file": "/private/backup-git.token",
    "branch_prefix": "mnemion-host-backups",
    "network_timeout_seconds": 300
  },
  "secret_file": "/private/company-recovery.key",
  "key_id": "KEY_ID_FROM_HOST_KEY_COMMAND",
  "independent_storage_confirmed": true,
  "independent_key_custody_confirmed": true,
  "maximum_bytes": 536870912,
  "keep_verified_backups": 3
}
```

Replace the destination and private file references, and confirm independence
only after arranging it. Keep credentials out of Git URLs and request bodies.
An SSH destination instead needs an explicit `ssh` object with private
`identity_file` and `known_hosts_file` references and the Git server's verified
host pin; see [Git transport setup](../service/git-journal.md). Those credentials
belong to backup delivery, not to the host-control operator enrollment.

Apply this configuration locally as the host owner:

```sh
mnemion-service host-control backup-setup \
  --state-dir /private/company-control \
  --config /private/company-backup.json
```

Configuration reports `delivery_verified: false`. It does not run a backup or
prove delivery. A local Git repository is insufficient for this independent
backup requirement. The remote URL and custody confirmations still require the
owner to establish actual failure-domain separation.

Before a new guarded upgrade stops the memory service, the worker creates an
encrypted host package and a fresh encrypted access/deletion ledger. It writes
an intent first, uploads encrypted parts to a unique host/operation branch and
verifies the exact commit and bytes through a fresh Git reader. The small Git
manifest contains identifiers, sizes and hashes; it is not encrypted memory
content. The upload uses no shared-branch rewrite or checked-out executable code.

The maximum backup size covers the package and ledger together: default
512 MiB, maximum 2 GiB. Delivery uploads the copy and reads it back; each fresh
verification downloads it again. Network traffic therefore exceeds the stored
copy's size. Delivery uses bounded subprocess/network and disk budgets.
Retention keeps three verified backups by default, configurable from 2 to 20.
Retirement compares the expected remote reference before deleting it; an active
upgrade's backup and uncertain copies remain protected. Deleting a Git reference
does not establish erasure from provider caches, clones or retained Git objects.

Preserve the backup receipt, key ID and independently accessible recovery
material. Readback proves those remote bytes, not a successful replacement-host
restore. The protocol has no Git-backup download/restore action. The
creation and verification controls below are separate from restoration.
Existing [host-package recovery](../service/host-recovery.md)
requires authenticated package/ledger files; a complete independently retrieved
Git-backup recovery journey remains to be qualified.

**Controller authority has separate custody.** The memory-host package does not
escrow the independent controller's host identity, authority store, operator
private keys or recovery of those grants. Their independent custody/export and
replacement-adoption procedure remain distinct work. Do not assume a restored
memory database authorizes a new controller.

### Create and verify retained backups

**Available since published 4.46.3.** The
[all-six native qualification](../validation/2026-10-23-4463-native-acceptance.md)
includes actual approval-control and native-schema checks with **synthetic
inventory**. The later
[4.46.5 fresh production backup and separate verification](../validation/2026-10-24-4465-backup-acceptance.md)
passed; independent restore remains pending. Use
[release status](../RELEASE_STATUS.md) for the public-update gate.

Backup source checks passed: 43 passed with
2 local SSH-environment skips, 3 native-boundary checks and 7 desktop host-profile
tests. The final 13 host-job checks also passed, including inspection for a
dangling inventory symlink. Frontend/Electron builds and Ruff checks passed.
See the [combined release notes](../releases/4.46.3.md) for the separate source,
native and deployment evidence.

Refresh the enrolled host before using **Independent backups**. The card shows
whether storage is owner configured, the **Maximum backup size**, recovery
key ID and last verified readback. Operators and custodians can confirm
**I approve encrypted backup transfers using this host's configured storage and limits.**
Then choose **Create encrypted backup**, or **Verify stored copy** on a retained
row. The confirmation clears after a request or a configuration change.
Controls depend on the actions advertised by the host; older hosts advertise
neither `backup.create` nor `backup.verify`.

The bounded inventory shows memory snapshot time, version when recorded, size
and last readback. **Recovery details** includes the backup ID, key ID,
access/deletion ledger time and each file's size and digest. The corresponding
host reply is `result.service.backups`: `configuration_sha256`, `maximum_bytes`
and `items`, whose entries include `backup_id`, `key_id`, `service_version`,
`snapshot_at`, `ledger_at`, `verified_at`, `last_verified_at`, `bytes` and `files`.
Missing version information is **Not recorded**. Destinations, private paths and
credentials are excluded from this status view.

| Typed host action | Required transfer fields and result |
| --- | --- |
| `backup.create` | Common timed request fields, `approve_backup_transfer: true` and the current `configuration_sha256`. Creates an encrypted memory package and access/deletion ledger using the existing owner-configured Git storage. |
| `backup.verify` | The same fields plus a retained `backup_id` from `items`. Reads back the original stored copy and records a fresh verification observation, preserving its original delivery receipt. |

Both actions require current operator or custodian authority. After bounded
source drain, the worker rechecks that authority, approval expiry and the exact
configuration. A changed destination/key/budget returns
`backup_configuration_changed`; refresh and review the current settings before
authorizing new work. A missing retained copy returns `backup_not_found`.
Requests cannot supply another destination, a key or an arbitrary command.
These transfers preserve the service's current intent: they do not start,
stop or upgrade it. Source imports wait while the copy is prepared.

Creation waits for existing recovery to be resolved. A retained copy can still
be freshly verified during that recovery once active work ends; verification
does not settle the older operation or replay it. Preserve its original UUID
and evidence. Configuration alone, an accepted queue entry and a verified
readback are distinct results; none proves a successful restore.

For a native agent using its saved protected profile, take the digest from the
fresh host reply's `result.service.backups.configuration_sha256` and use the
usual timed approval fields. This example creates one copy:

```json
{
  "action": "host.request",
  "input": {
    "id": "LOCAL_PROFILE_UUID_FROM_HOST_CREATE",
    "request": {
      "protocol": 1,
      "host_id": "HOST_UUID_FROM_CONNECTION",
      "request_id": "NEW_BACKUP_OPERATION_UUID",
      "action": "backup.create",
      "issued_at": "CURRENT_UTC_TIMESTAMP",
      "valid_until": "APPROVAL_EXPIRY_WITHIN_ONE_HOUR",
      "configuration_sha256": "64_LOWERCASE_HEX_CHARACTERS_FROM_CURRENT_HOST_STATUS",
      "approve_backup_transfer": true
    }
  }
}
```

To verify a retained copy, use the same outer desktop envelope with this
`input.request`. The copy's `backup_id` is separate from the new verification
operation UUID:

```json
{
  "protocol": 1,
  "host_id": "HOST_UUID_FROM_CONNECTION",
  "request_id": "NEW_VERIFICATION_OPERATION_UUID",
  "action": "backup.verify",
  "issued_at": "CURRENT_UTC_TIMESTAMP",
  "valid_until": "APPROVAL_EXPIRY_WITHIN_ONE_HOUR",
  "configuration_sha256": "64_LOWERCASE_HEX_CHARACTERS_FROM_CURRENT_HOST_STATUS",
  "approve_backup_transfer": true,
  "backup_id": "RETAINED_BACKUP_UUID_FROM_CURRENT_HOST_STATUS"
}
```

Observe `operations.get` using the original operation UUID. A lost reply keeps
that UUID and exact request; inspect it before any retry rather than issuing a
new copy request. The app and native agent retain the same durable request.
These controls add no controller-authority escrow, device-key recovery,
replacement-host takeover or new restore acceptance.

## Review and apply a guarded upgrade

An operator submits `upgrade.plan` with the common protocol, host/request IDs and
timed approval fields. It takes no client-chosen version, URL, executable or host
path. Observe the resulting operation until it succeeds. If a plan is available,
`operations.get` returns it in **`result.result`**.

Review the signed target's `target_version`, `source_commit`, schema/migrations,
service interruption, `resume`, backup configuration and expiry. A plan may
instead report that no upgrade is available. A backup configuration flag is not
a delivery receipt. Database rollback is not automatic.

Apply only the exact reviewed plan, with a new operation ID:

```json
{
  "protocol": 1,
  "host_id": "HOST_UUID_FROM_CONNECTION",
  "request_id": "NEW_APPLY_UUID",
  "action": "upgrade.apply",
  "issued_at": "CURRENT_UTC_TIMESTAMP",
  "valid_until": "APPROVAL_EXPIRY_WITHIN_ONE_HOUR",
  "approve_service_interruption": true,
  "plan_id": "PLAN_ID_FROM_COMPLETED_PLAN",
  "plan_sha256": "PLAN_SHA256_FROM_COMPLETED_PLAN"
}
```

An operator applies a plan created under the same enrollment; a custodian may
also apply another operator's current plan after review. The worker binds the
plan to the host, signed manifest, current runtime/configuration, backup settings
and migration journal. Changed or expired inputs require a fresh review. Host
work participates in the existing exclusive update lock, including coordination
with automatic managed updates.

Fresh encrypted backup readback must succeed before a new cutover. Forward
recovery revalidates the recorded original backup and journal instead of creating
an unrelated replacement. Existing migration rules remain in force; an older
memory-service binary must not be started against a newer database schema.
See [managed upgrade rules](../service/managed-updates.md).

## Recover a lost reply or interrupted operation

Persist the original request body and UUID **before sending it**. The host stores
intent before acknowledging work, and a detached worker owns execution beyond
the SSH/app session. Reconnect and inspect that original operation ID after a
timeout. If resubmitting is appropriate, use the same operator, UUID and exact
typed payload, including its original timestamps. Different work under an old
UUID is an `operation_conflict`; inventing a new UUID can create new work.

| Receipt phase | Operator response |
| --- | --- |
| `queued`, `running` | Continue bounded observation of the same operation. A reconnect is not a second upgrade. |
| `succeeded` | Read the result and observed current state; retain the receipt. |
| `failed`, `cancelled` | Preserve the error and original intent. Review authority, expiry and state before approving new work. |
| `inspection_required` | Effects may have begun. Do not replay automatically or treat uncertainty as failure-before-effects. |

After a worker interruption, previously running work becomes
`inspection_required`. Ordinary queued service work is held while uncertainty
remains; recovery planning/application and custodian resolution remain available.

For an uncertain operation with **no pending migration journal**, a custodian
can approve a freshly inspected stable state:

```json
{
  "protocol": 1,
  "host_id": "HOST_UUID_FROM_CONNECTION",
  "request_id": "NEW_RESOLUTION_UUID",
  "action": "operations.resolve",
  "issued_at": "CURRENT_UTC_TIMESTAMP",
  "valid_until": "APPROVAL_EXPIRY_WITHIN_ONE_HOUR",
  "operation_id": "UNCERTAIN_OPERATION_UUID",
  "approve_current_state": true,
  "settle": "observe"
}
```

`settle: "stop"` additionally requires `approve_service_interruption: true`.
Resolution retains `original_outcome: "unconfirmed"` and the accepted current
observation; it does not rewrite the original operation as successful.

When a managed migration journal requires recovery, use a newly reviewed
`upgrade.plan` and guarded `upgrade.apply` for that journal. Successful forward
recovery links its new receipt to the original uncertain failure. Do not clear
journals, rotate pins, remove backup intents or downgrade the database to bypass
an inspection requirement. Escalate to the OS owner when no safe typed recovery
path is available.

## Controller runtime continuity and bounds

Adoption pins a verified controller runtime independently of the memory service's
active runtime. Current/previous pinned slots are protected from normal update
cleanup. When no work can be displaced, the controller probes a compatible new
runtime and acknowledges it only after its listener binds. Repeated unacknowledged
starts can fall back to the prior controller runtime. This is controller fallback,
not database rollback or acceptance of an older memory-service binary.

Inspect `version`, `update_pending`, `fallback` and `update_needs_inspection`
within `result.service.controller` in the host-status response. The stable bootstrap,
protected state, runtime files and OS account remain necessary. This architecture
does not survive loss of the entire computer by itself.

The current protocol bounds requests to 16 KiB and responses to 128 KiB. The
direct CLI connection/reply deadline defaults to 15 seconds; the desktop helper
uses a bounded 20-second call. A queued host job can outlive either connection.
The listener admits at most 32 concurrent connections.
Lists default to 50 entries and permit at most 100 per page. The authority store
bounds active operators to 128 and retained operation records to 512, reserving
space for authority work. Expired terminal receipts can be pruned; it is not an
unlimited audit archive. Retain required evidence independently.

| Diagnostic | Next step |
| --- | --- |
| `host_identity_changed` | Have the OS owner verify the pinned host/configuration. Do not silently replace the pin. |
| `host_access_denied`, `invalid_operator_key` | Check the exact enrollment, key fingerprint, role, expiry and retirement with a custodian. |
| `host_connection_timeout`, `host_control_unavailable` | Inspect reachability, then query the original operation; memory-service status is not yet known. |
| `authority_changed`, `request_expired` | Refresh current authority/clock and inspect old work before approving a new request. |
| `plan_changed`, `backup_required`, `recovery_required` | Review the current plan, independent backup or existing journal; do not bypass its guard. |
| `operation_limit`, or receipt phase `inspection_required` | Inspect retained/pending work and unresolved effects. Do not delete receipts to force execution. |

Raw subprocess output, private paths and credentials are not the remote
diagnostic interface. The OS owner can inspect protected local logs when a
bounded error requires investigation.

**4.46.5 source diagnostics:** the
[backup transfer follow-up](../validation/2026-10-23-backup-transfer-diagnostics.md)
preserves a host-private delivery intent before push and bounded transfer
progress. An uncertain receipt can retain `result.backup_transfer` with a fixed
stage, reason and exit code; Host controls explains that result without raw Git
stderr, credentials or exception text. This work is excluded from frozen
4.46.4. It keeps `inspection_required` and adds no retry or resume action.
Retain the original request and encrypted files for inspection; the new
diagnostics do not establish delivery or resolve the original uncertain backup.

Interpret `deadline` using its recorded stage and configured limit. The
[full-size transfer follow-up](../validation/2026-10-23-backup-transfer-window-900.md)
passed an isolated upload and fresh readback of the retained encrypted files
under a 900-second network-command window; its readback fetch took 403.678
seconds. The first 300-second push failure remains preserved, and the original
native backup remains failed/unconfirmed. This diagnostic created no new
snapshot and does not qualify fresh native backup delivery or restore.

At **19:22:24 UTC on 23 October 2026**, the reviewed company-host configuration
changed only its network-command timeout from 300 to 900 seconds. Runtime
4.46.3 and authority remained unchanged, and no backup was requested or
delivery verified by that update. The diagnostic's 2,700-second total cap was
separate from this configuration change. No product retry or resume action
was added; fresh native backup and independent restore still required acceptance
at that configuration checkpoint.

## Qualification and remaining work

The [4.46.5 second-candidate native qualification](../validation/2026-10-23-4465-native-acceptance.md)
passed all six installed targets at **20:45:26 UTC on 23 October**, with 59
required observations each. The original Windows ARM64 candidate failure is
preserved; the added diagnostics do not establish its cause or a functional
fix. Artifact verification subsequently passed, 4.46.5 was published at
**20:49:55 UTC**, and automatic website verification passed at **20:50:15 UTC**.
All six downloads, current guides and Git-owned product content were present.
Public upgrade checks, still running at 20:56 UTC, subsequently
[passed all six targets](https://github.com/Perseusxrltd/mnemion/actions/runs/40022243634);
the [release status](../RELEASE_STATUS.md) records the public gates.
The [actual 4.46.5 paired acceptance](../validation/2026-10-23-4465-live-acceptance.md)
passed at **21:32:43 UTC on 23 October**, preserving the original failed access
comparison and using an inspected continuation without repeating either update
or the completed Windows restart. The unchanged 15-request comparison and
42/42 isolated lab requests passed, with no pending cleanup. Windows used a
guarded agent-requested restart, which does not establish unattended idle
restart. The separate [4.46.5 two-custodian journey](../validation/2026-10-23-4465-custody-acceptance.md)
passed at **23:52:34 UTC**, retaining existing OS authority, the original stop,
two scheduled watchdog ticks and the planned start issued once after inspection.
Final readiness, both custodians, the saved connection and exact memory/access
comparison passed; the local verifier interruption is preserved. The subsequent
[fresh native backup and separate custodian verification](../validation/2026-10-24-4465-backup-acceptance.md)
passed at **00:01:45 UTC on 24 October**. Independent restore remains pending.

The earlier [4.46.4 native qualification](../validation/2026-10-23-4464-native-acceptance.md)
retains its six installed-target results and matching source, job and artifact
evidence. Its frozen source excludes the later 4.46.5 transfer diagnostics.
That historical qualification does not establish an actual Windows/shared-host
4.46.4 installation, fresh native backup delivery or independent restore.

The [4.46.3 native/public-update qualification](../validation/2026-10-23-4463-native-acceptance.md)
passed all six targets. Its separate [actual paired acceptance](../validation/2026-10-23-4463-live-acceptance.md)
completed at **15:54:32 UTC on 23 October**, after an inspected continuation
that preserved the original access and deletion interruptions. No additional
update, restart or lab cycle was requested by that final continuation. The
separate [two-custodian lifecycle](../validation/2026-10-23-4463-custody-acceptance.md)
passed at **16:25:34 UTC**, retaining the original authority and stop/start
requests, with both clients and the unchanged content/access comparison passed.
Fresh native backup delivery and independent production restore were unaccepted
at that historical checkpoint.

The **4.46.1 qualification at 08:30 UTC on 23 October 2026** passed all six
installed targets and their packaged host-control journeys. The
[4.46.1 native report](../validation/2026-10-23-4461-native-acceptance.md)
retains the source/run bindings, unchanged qualification receipt, corrected
Windows journal-form failure and subsequent six-platform public update results.
All five [release gates](../validation/releases/4.46.1-status.json) passed by
08:46:59 UTC, including automatic website synchronization. At that historical
checkpoint Windows had updated while the host's pre-update backup was running.
The later [actual paired acceptance](../validation/2026-10-23-4461-live-acceptance.md)
passed at **09:55:28 UTC**, preserving the existing Windows installation,
three identities, exact sampled memories, login and preferences. The later
[host-control journey](../validation/2026-10-23-independent-host-adoption.md)
passed adoption, backup configuration, OS integration and two custodian
enrollments, but **failed at the first Windows stop before any effect**.
Manager restart, two watchdog ticks, service start and retained-data acceptance
were not reached. A fresh status read found memory ready/running with no
pending work or recovery.

The [4.46.2 source follow-up](../releases/4.46.2.md) uses the existing supported
five-minute source-drain window and reports fixed `host_busy` when an active
scan still blocks a host operation; the UI explains that result. Source checks
and builds passed, but installed/native, public and actual-host acceptance
remain unproven at that source checkpoint.

The later [4.46.2 native build 39945380878](https://github.com/Perseusxrltd/mnemion/actions/runs/39945380878)
passed; publication was still pending at **12:19 UTC on 23 October 2026**.
That historical qualification predates the later
[4.46.3 native qualification and publication](../validation/2026-10-23-4463-native-acceptance.md).
The later [actual custodian journey](../validation/2026-10-23-4463-custody-acceptance.md)
passed within its recorded scope. Fresh native backup delivery and independent
production restore were unaccepted at that historical checkpoint.

The **23 October 2026 native qualification** passed all six installed Windows,
macOS and Linux x64/ARM64 targets for the published 4.46.0 source. The
[native report](../validation/2026-10-23-4460-native-acceptance.md) binds each job
and receipt. The packaged host-control journey exercised the real UI, protected
key, native agent pipe and pinned SSH with the peer's memory API absent. It
reopened the key after a full app restart, inspected the original queued UUID
without replay, enforced the custodian boundary and archived the public request
before local-key removal. Both Linux targets also passed with a required real
OS keyring. These are installed runner checks; the peer had no worker, so its
approved stop remained queued. They do not establish production stop execution,
OS integration or custody across independently held physical devices.

Earlier evidence includes source/fixture checks, an actual independent local
Supervisor plus restricted SSH lifecycle while the memory API was absent, and
isolated SSH/Git backup delivery. A source Node profile also reached the native
Python engine and a real independent SSH controller with the memory API absent;
its earlier selected run passed 28 checks, including store/upgrade cases. Two
real source journey cases subsequently passed again. These journeys use a fixture
cipher, so they do not qualify an actual OS secure store or an installed desktop
package. Guarded migration checks include mocked managed migration fixtures.
Earlier failing attempts remain historical evidence.

At the **22 October 2026 source checkpoint**, 20 targeted profile/agent/process
checks passed, including recovery archives and refused-replay cases, alongside
three owner-recovery and three backup-retention checks. Electron and frontend
builds, lint and formatting passed. A visual fixture verified approval of the
exact plan digest and a 960px layout without overflow; it is not a live host or
installed-app acceptance result.

The [subsequent source validation](../validation/2026-10-22-independent-host-control.md)
retains 75 Python integration and 20 desktop component checks; the new native
loopback-peer fixture passed one focused case in 4.30 seconds. On **23 October
2026, 00:12:21 UTC**, the final Linux **source Electron preview** passed with the
real app UI, native agent pipe and libsecret. It created a protected host login,
authenticated pinned SSH with the memory API absent, submitted an approved stop,
then fully exited and reopened the same key. The agent inspected the original
queued UUID without replay, was refused custodian-only listing and forgetting
without acknowledgement, and read back the public request archived by the UI
before local key removal.

That peer had no worker: the stop stayed queued and no product memory service
started. Production writes and paid calls were zero. This is source client/key
evidence against a transport fixture; it does not qualify actual stop execution
or an installed package. Earlier missing-Electron and app-ready-await preview
harness failures and the initial passing preview remain preserved separately.
The final run waited for settled UI observations and confirmed the queued UUID
and retained recovery request were visible before closing; both complete
process phases exited successfully, and the Electron rebuild passed.

The **23 October durable service-policy revision** was added after those source
proofs. Its policy source checks and frontend build passed, including restart of
a real `memory-run` process while the saved approved stop remained in effect.
The [separate policy checkpoint](../validation/2026-10-22-independent-host-control.md#durable-service-policy--23-october-2026)
retains the 87-pass/two-fixture-error full attempt followed by two targeted SSH
passes. This source evidence does not qualify actual OS job/watchdog integration.

At those source checkpoints, all six 4.46.0 installed-platform gates were unrun.
The first frozen candidate subsequently passed Windows x64 installed local
hosting, but both Windows x64 and ARM64 failed their packaged host-control UI
checks. Both use the same frozen x64 service engine. The
[23 October Windows failure record](../validation/2026-10-23-windows-host-client.md)
preserves the reproduced `win32timezone` import failure: AsyncSSH initialized
Windows GSS/SSPI despite the disabled GSS authentication flags. The source
correction explicitly sets `gss_host=None` for the key-only transport. An early
frozen-engine gate now requires pinned SSH inspection and refusal of a changed
server pin before the longer desktop tests.

The correction's initial verification recorded 18 source passes and one Studio-built
journey skipped because that checkout lacked compiled desktop output. A separate native
Windows diagnostic copy, replacing only the host transport/server module
bytecode, passed the early gate while the original frozen binary failed it.
The original failures remain retained. The four original Linux/macOS native
jobs passed. The subsequent rebuilt Windows engine passed the frozen gate, and
the corrected release completed all six native jobs as recorded above.

The installed gates require the expanded real UI/agent/key/SSH/restart/archive
journey through the offline `/hosts` route. Their native client smoke stage has
a finite 180-second readiness deadline, with individual helper bounds retained.
Listener reconfiguration, independently recoverable controller-authority custody,
whole-machine boot/login acceptance, independent restore and production backup
retention remain open. Fresh native Git-backup verification subsequently
[passed on 4.46.5](../validation/2026-10-24-4465-backup-acceptance.md). The completed
setup does not establish universal onboarding or full production continuity.

The [23 October publication and live rollout record](../validation/2026-10-23-4460-live-rollout.md)
records successful verification of all 38 release assets, publication at
05:43:10 UTC and all six public installed-update targets passing by 05:54:51 UTC.
The actual Windows app reached 4.46.0, but its shared host rolled back to 4.45.1
at the updater's managed-readiness boundary. The paired observer and dependent
backup/adoption jobs stopped for inspection without controller adoption or OS
changes. At that checkpoint the last complete pair was
[4.45.1](../validation/2026-10-23-4451-live-acceptance.md). The later
[4.46.1 paired acceptance](../validation/2026-10-23-4461-live-acceptance.md)
passed after the [preserved interruptions](../validation/2026-10-23-4461-live-interruption.md).
The later [OS integration and custodian enrollments](../validation/2026-10-23-independent-host-adoption.md)
passed; that 4.46.1 operational journey failed at its first stop. The separate
[4.46.3 two-custodian journey](../validation/2026-10-23-4463-custody-acceptance.md)
subsequently passed deliberate stop, independent inspection, manager restart,
scheduled watchdogs, start and retained-data checks. The later
[4.46.5 fresh native backup verification](../validation/2026-10-24-4465-backup-acceptance.md)
passed; independent restore still requires its own passing evidence.
Current package availability follows [release status](../RELEASE_STATUS.md).

Provider power-on, browser-based independent management, company identity
linking, Windows/Compose host adoption, replacement-host provisioning, replication
and fencing an old writer remain separate capabilities. Follow the
[roadmap](../ROADMAP.md) and [requirements](../PRODUCT_REQUIREMENTS.md); this guide
does not change their states or qualify broader continuity work as complete.
