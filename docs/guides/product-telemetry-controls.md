# Product telemetry privacy controls

**Source checkpoint, 24 October 2026; V08 is Building.** Local choice and
disclosure controls are implemented in source. There is no product sender or
collector: `collection_available` is `false`, the destination is `null`, and
`effective_enabled` stays `false`. Saving an enabled preference does not activate
analytics. The core browser journey passed **19 checks at 00:51:17 UTC**, followed
by **eight browser policy/fault checks**. [Source-input qualification](../validation/2026-10-24-telemetry-controls.md)
passed at **01:12:30 UTC**; native release acceptance remains pending.
These controls and this documentation update are excluded from the isolated
4.46.6 dependency-security release. The [contract](../implementation/anonymous-product-telemetry.md)
records the dated source evidence and full remaining scope.

## In the app

Open **Privacy & product telemetry** from the connection screen or visit
`/privacy`. The page works before workspace sign-in and without a live memory
service. The desktop bundles it; a browser still needs the app assets available
to use the page offline.

**Share anonymous product statistics** changes the saved preference, which
defaults to enabled. **Disable product telemetry** saves an opt-out and clears
pending local aggregates. **Refresh privacy status** reads the current choice.
**Show payload preview** currently reports no queued request, a null outbound
body and zero outgoing payload bytes. The listed measurements are planned.
A later build capable of collection must present its current disclosure before
anything can be sent; today's enabled preference cannot acknowledge that future
destination.

The desktop and native agent share the preference under the same OS account and
application data configuration. A browser stores its own choice for that site;
it does not synchronize it with other browsers, desktop installations or remote
hosts. Global Privacy Control keeps browser collection off. A browser without
the required coordination between tabs also keeps it off. Clearing site storage
removes the saved choice and requires fresh disclosure; no identifier or
fingerprint is used to recover it.

## From a native agent or terminal

A runtime built with these source controls accepts one JSON line on private
stdin, without a memory API connection, credentials or a running desktop:

```sh
printf '%s\n' '{"action":"schema"}' | mnemion-service telemetry
printf '%s\n' '{"action":"status"}' | mnemion-service telemetry
printf '%s\n' '{"action":"preview"}' | mnemion-service telemetry
```

`schema` describes the four local actions and disclosure; it is not an
implemented aggregate-event schema. `status` distinguishes `user_enabled`,
`effective_enabled`, `reason`, `storage`, company restriction and `revision`.
`preview` returns `outbound_body: null`, `outbound_bytes: 0` and
`transport_available: false` in this build. Success returns
`{"event":"result","ok":true,"result":...}`; refusal returns a fixed error code
with `ok: false` and exit status 2.

To save a choice, first read status and substitute its current revision for
`0` in this opt-out example:

```sh
printf '%s\n' '{"action":"configure","enabled":false,"expected_revision":0}' | mnemion-service telemetry
```

To save an enabled preference, use `enabled: true` and the latest revision.
Omit `disclosure_version` or use `0`: this build rejects a nonzero disclosure
acknowledgement with `telemetry_disclosure_unavailable` because no collection
destination is available. Enabling with an outdated revision is refused as
`telemetry_choice_changed`; disabling remains allowed with an outdated revision.
Every successful opt-out advances the revision, even if already disabled, so an
older enable request cannot override it.
A successful change clears pending aggregates, so re-enabling cannot revive old
data. The desktop agent exposes the same typed `telemetry.schema`,
`telemetry.status`, `telemetry.preview` and `telemetry.configure` actions without
requiring a workspace.

## Company restriction and damaged settings

The native policy reads an optional administrator file:

| Platform | Policy file |
| --- | --- |
| Windows | `%PROGRAMDATA%\Mnemion\telemetry-policy.json` |
| macOS | `/Library/Application Support/Mnemion/telemetry-policy.json` |
| Linux | `/etc/mnemion/telemetry-policy.json` |

For example, `{"schema_version":1,"enabled":false,"metric_groups":[]}` disables
collection. Policy may narrow the disclosed groups; it cannot override a user
opt-out. The service-served browser app receives the restriction with its page;
reload to obtain a changed policy. An unreadable or invalid policy restricts
collection rather than falling back to permission.

Unreadable, damaged or inaccessible local settings fail closed with
`storage_unavailable`; status is not confirmation of a saved preference in that
state. A failed save is not a successful opt-out or re-enable. There is no
automatic settings repair or repair action yet. Do not erase settings as a
generic repair: that can erase an explicit opt-out. After a transient storage
or lock problem is resolved, refresh status and confirm the saved choice.

Optional product telemetry is separate from private workspace operational and
security records. These controls do not change memory access or disable those
records. The [full V08 contract](../implementation/anonymous-product-telemetry.md)
and [proposed catalog](../implementation/anonymous-product-telemetry-catalog.md)
retain app, agent, headless and remote-workflow coverage; shared-host ownership,
the sender, collector and transport-anonymity proof remain unfinished. See the
[privacy policy](../service/privacy.md) for existing service and model traffic.
