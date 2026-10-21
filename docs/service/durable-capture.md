# Keep selected conversations after chat logs disappear

**Unreleased implementation.** This guide describes the current development
source. Check [release status](../RELEASE_STATUS.md) for published availability.
Both Studio and the workspace server must support retained capture; the server
advertises `durable_capture: "v1"` in `GET /health/live`. This work advances L1
of the [layered librarian](../research/2026-10-20-layered-librarian.md); full L1
and R07 acceptance remain open.

Retained capture commits the selected conversation items to an encrypted local
inbox before making any service request in a scan. Once accepted locally, those
items can still be delivered after the original JSONL file rotates or disappears.
Delivery checks the workspace's current authorization and forgetting decisions.

## Choose retention before enrollment

Use [desktop source setup](desktop-sources.md#set-up-a-source) with a **new
conversation connection**, its own non-administrator application and an explicitly
mapped audience. Existing conversation mirrors keep their existing inventory and
removal policy. Changing a mirror into retained capture requires a reviewed
migration; this guide does not provide that migration.

Map yourself too if you need to read the captured memories. Organization
administration alone does not grant access to a source's content. With no mapped
people or agents, only the dedicated source application can read its copies.

1. In **Connections → Run on this computer**, choose the conversation folder.
2. Choose **What to remember**. **Messages only** (`messages`) copies supported
   user and assistant message text. **Messages and exposed session events**
   (`complete`) also keeps the session records actually saved by the producer,
   including exposed tool activity and reasoning traces. Unknown message formats
   produce no message copy. Neither mode obtains hidden provider reasoning.
3. As a workspace administrator, select **Keep captured memories when original
   chat logs rotate or are removed**. Review the audience and the pending content
   limit. The selection is fixed for this inbox: changing `capture_mode`, its
   identity or its dedicated key requires a reviewed migration.
4. Leave the application key empty to have Studio create a dedicated key, or
   supply the existing dedicated key **and its key ID**. The key ID binds the
   device grant; it is separate from the inbox's encryption key.
5. Confirm publication to the mapped identities and select **Save and start
   scanning**. Studio first configures the server's retention policy and device
   grant, then verifies and saves the local enrollment with OS-protected keys.

Initial enrollment requires a reachable workspace. After enrollment, Studio can
accept available complete records while the workspace is offline, within the
local limits below. Keep Studio running, with **Run in background** and **Start
at login** enabled for unattended scans. Quitting the app stops its runner.

The inbox contains only the approved capture selection. In `messages` mode,
raw tool and reasoning records remain in the producer files; they are not hidden
inside the inbox's source evidence. Unfinished JSONL tails wait for a later scan.
Material removed before a successful local commit cannot be recovered by this
feature. A completed scan covers the available input; it does not prove that
every historical conversation was captured.

## Read capture and delivery status

**Run on this computer** and **Sources on this computer** show the last saved
capture observation. The native `source.status` action returns the same values
in `activity.report.capture`.

| Observation | Meaning |
| --- | --- |
| `locally_accepted` | Selected events committed locally during the reported scan. These are events/fragments, not a count of conversations or messages. |
| `pending_events`, `pending_bytes` | Locally accepted content still awaiting a confirmed server outcome. Pending content has no automatic expiry. |
| `stored_events` | Events acknowledged as stored by the workspace. |
| `forgotten_events` | Events covered by the workspace's current forgetting decisions. |
| `remote_committed_events` | Delivery acknowledgements received during the reported scan, including `stored` and `forgotten` outcomes. |
| `unknown_pages` | Saved delivery pages awaiting reconciliation. A lost reply does not prove failure or authorize a different page. |
| `capture_complete`, `reason_code` | Whether that local scan finished and any observed source, capacity, integrity or authorization problem. An incomplete scan can leave earlier accepted evidence available. |
| `delivery_complete` | The observed pending queue and current forgetting sweep finished without a delivery error. |
| `database_bytes`, `device_database_bytes`, `device_pending_bytes`, `over_limit` | Local storage observations and whether the inbox exceeds an admission limit. |

Delivery reuses each saved page's exact identity and body. After an uncertain
reply, the runner looks up the receipt before resending the same page. It applies
current forgetting fences and checks the source, device key, grant and audience
again at server commit. A revoked grant cannot deliver queued evidence. Once
revocation is observed locally, further intake under that enrollment stops.

Local acceptance, server acknowledgement, indexing readiness and librarian work
are separate stages. An empty queue or successful HTTP reply does not establish
semantic-search readiness or completed librarian processing. Saved scan history
also reports the last success, failure or interrupted attempt; an unknown or
unsaved observation must remain unknown in an agent's report.

## Storage and resource limits

| Limit | Current value |
| --- | --- |
| Pending selected content per source | Default 256 MiB; configurable from 1 to 1,024 MiB |
| Pending selected content across this device's saved sources | 1 GiB |
| Inbox database admission per source | 512 MiB |
| Aggregate inbox database admission on this device | 2 GiB |
| Free disk required for new intake | At least 512 MiB, plus room for the incoming transaction |
| Retained event references per inbox | 100,000; producer tracking is also bounded |
| Producer scopes per inbox | 10,000 |
| Source RAM | Default 256 MiB; configurable from 128 to 2,048 MiB |

Content limits count the selected payload, independently of database
overhead. Raising the payload limit does not raise the database or reference
limits. Database admission counts SQLite pages. Bounded delivery bookkeeping can
use reserve above the database limit so reconciliation and forgetting can still
finish; this is not extra allowance for new capture.

At capacity, new intake stops and already accepted evidence stays available.
Lowering a limit does not trim the queue or silently discard events. Delivery
and forgetting remain available, subject to usable disk space and current
authorization. Free storage or let the backlog deliver, then check status again.
The [desktop resource limits](desktop-sources.md#capture-and-resources), including
the sampled RAM limit and process deadline, also apply. Capture does not need a
local model; server indexing follows the workspace's model policy.

## Pause, remove and forget

**Pause on this computer** works offline. It saves the pause, stops this device's
scan and retains its inbox and committed progress. Resume starts from that saved
state and delivery rechecks current authorization.

To remove retained capture, pause it first, then select **Remove from this
computer → Revoke device grant and discard local inbox**. This permanently
discards the local inbox, including pending content and deliveries whose outcome
is still unknown. The workspace must confirm that the device grant, or its
source, is revoked before local data is discarded. Original chat files, server
memories and the application key's other permissions remain. Revoke an unused
application key separately in **People & apps** when intended.

If the saved device key is lost, expired or revoked, use a current administrator
connection for the **same workspace**. Removal from **Connections** automatically
uses that matching administrator session.
Alternatively, expand **Device key unavailable?** under **Sources on this
computer** and supply the optional **Administrator key** for the displayed
workspace. The removal operation uses this credential only to check and revoke
the saved grant; it does not save the credential, replace the source's key or
authorize new capture. The native helper checks the exact saved grant binding,
and the server checks the caller's current rights. A refused credential leaves
the inbox in place.

A lost revocation reply leaves local data in place. Read fresh status before
retrying: the removal flow checks the existing grant and can recognize an
already-completed revocation. If confirmed retirement was saved locally but
cleanup was interrupted, cleanup can resume offline from that record without
a surviving device or administrator credential. Leave the optional removal
credential empty for that local cleanup. A lost reply without a saved retirement
record still requires server confirmation. Offline pause remains available
while server confirmation is unavailable.

Server revocation and forgetting have different effects. Revoking a device grant
stops its capture delivery; revoking a source also denies access to its custody
space. Neither action is a request to erase its stored memories. To forget a
captured fragment, use the normal memory-forgetting action and review
`capture_forget`: it withdraws that fragment's retained raw evidence, projections,
parts and revisions together and may include adjacent messages. Its retained
count is an observation; the write rechecks the current family atomically.
Later deliveries of the same fragment stay forgotten. This is not semantic
deletion of matching text across unrelated files, new generations or imports.

## Recovery boundaries

Each inbox uses a separately generated, random 256-bit key sealed by the OS
credential store. Selected payloads and checkpoints are encrypted with
AES-256-GCM in private local storage. The dedicated API key does not derive or
replace that encryption key. Neither key is returned by `source.status`.

Only a new, pending enrollment may initialize an empty inbox, before any intake.
Missing or damaged keys, an initialized database that has disappeared, or an
enrollment/binding mismatch stop capture visibly. The runner does not silently
create an empty replacement and claim previous work was preserved.

Unlock OS credential storage when it is merely locked. For lost or corrupted
state, preserve the existing files and restore the verified matching inbox,
enrollment, settings and usable protected key. A new computer cannot infer past
accepted or forgotten ranges from today's chat files. Restoring the original
verified state or completing an explicitly reviewed migration is required; new
IDs, a new key or a fresh source are not a recovery substitute. An OS-sealed key
is not automatically portable between accounts or computers, and a server
backup cannot reconstruct undelivered local evidence.

An expired or revoked device API key can be handled through the
[administrator removal fallback](#pause-remove-and-forget). That fallback
permits retirement and explicit local discard; it does not recover a missing
encryption key or restore capture. Replacing an established inbox's key through
an ordinary settings update remains unsupported.

**Repair saved scan history**, also exposed as `source.repair`, repairs only
observations. It preserves the damaged diagnostic file and resets scan history
for **every source on this computer** to unknown. Settings, credentials, inboxes
and capture checkpoints remain. It does not recover lost evidence, restore
encryption keys or prove a previous scan succeeded. Repair does not start a scan;
normal automatic checks resume at their next interval.

## Agent and administrator setup

Remote administration uses the server's capture APIs. The local runner uses the
same OS-account [private desktop interface](desktop-operator.md) as Studio;
a network memory credential does not authorize control of the computer. Discover
the current [agent operation schemas](agent-control.md) before submitting a
request. These operations are part of the unreleased implementation:

| Operation | HTTP route |
| --- | --- |
| `capture.source.configure` / `capture.source.status` / `capture.source.revoke` | `PUT` / `GET` / `DELETE /v1/connectors/{connector_id}/capture-sources/{source_id}` |
| `capture.grant.configure` | `PUT /v1/capture-sources/{source_id}/grants/{grant_id}` |
| `capture.grant.status` / `capture.grant.revoke` | `GET` / `DELETE /v1/capture-grants/{grant_id}` |
| `capture.pages.accept` | `POST /v1/capture-grants/{grant_id}/pages` |
| `capture.pages.receipt` | `GET /v1/capture-grants/{grant_id}/pages/{page_id}` |
| `capture.fences` | `GET /v1/capture-grants/{grant_id}/fences` |

After registering the new `conversations` connector with `access_mode:
"published"` and mapping its audience, an administrator approves the source
with a stable `source_id`. The initial source PUT body is:

```json
{
  "expected_version": 0,
  "namespace": "selected-source",
  "name": "Selected conversations",
  "members": ["application:approved-assistant"],
  "capture_mode": "messages",
  "keep_accepted": true
}
```

Use the original approved namespace if it differs from `selected-source`.
Updating the name or audience uses the current source version from GET. The
source identity and capture selection remain immutable. Then approve a stable
`grant_id` through the device-grant PUT with
`{"device_key_id": "DEDICATED_APPLICATION_KEY_UUID"}`. Only an administrator
can authorize the source and grant; the source's application key cannot grant
itself custody or expand its audience.

Read `source.status` locally, then send `source.configure` with its fresh
`expected_revision`, the complete [source settings](desktop-sources.md#local-agent-controls)
and the dedicated credential through private stdin. Add these fields to the
`source` object, using the IDs approved above:

```json
{
  "capture_mode": "messages",
  "custody": {
    "source_id": "APPROVED_SOURCE_UUID",
    "grant_id": "APPROVED_GRANT_UUID",
    "keep_accepted": true,
    "pending_limit_mib": 256
  }
}
```

This is a settings fragment, not a complete `source.configure` request. Native
enrollment creates and seals the independent inbox key; do not supply one through
the public source object. Keep the same mode, namespace, source and grant on
later settings updates. An uncertain administrative reply requires reading the
existing source/grant or local status before another write.

The runner owns page construction and retries. Pages contain 1–50 selected
evidence events, with at most 1,500,000 bytes of canonical JSON. Reusing an ID
with different content is rejected. `capture.pages.accept` is classified as
private input; use the private CLI/transport path described by discovery rather
than putting conversation payloads into ordinary agent tool arguments.

Native removal requires `source.pause` with `enabled: false`, followed by
`source.remove` with a fresh `expected_revision`, `id`, `confirm: true` and
`discard_local_inbox: true`. Its optional `retirement_credential` supplies a
current administrator credential for that workspace when the device key is
unavailable. Pass it only through the private desktop pipe; it is never saved
by removal or used for intake. The app can pass a matching administrator session
handle for native resolution. Omit the field when completing cleanup after
retirement was already recorded locally; no surviving credential or HTTP request
is then needed. Native history repair requires its current
`repair_token` and `confirm: true`, with no active source scan; its source ID
identifies the displayed context, not a source-only reset.

Broader migration/export, the complete installed Windows/macOS/Linux journey
and full L1 acceptance remain pending. This workflow does not replace those
gates or narrow the [65 product requirements](../PRODUCT_REQUIREMENTS.md) and
L1–L7 scope.
