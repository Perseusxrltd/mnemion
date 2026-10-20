# Slack and Google Drive sources in Studio

Source 4.34.0 extends [desktop sources](desktop-sources.md) to Slack and Google
Drive. A desktop can contribute to a shared workspace without hosting a local
database or model. Check [release status](../RELEASE_STATUS.md) for published
installers.

## Common setup

1. Connect to the intended workspace. In **People & apps**, create a dedicated
   application for this source. Register its Slack or Google Drive connection in
   **Connections**, using provider access mode.
2. Under **Who can use this source?**, map actual provider identities to the
   people or agents who should receive access. Slack identities look like
   `slack-user:U12345678`; Drive identities look like `google-user:123456789` and
   use the provider's permission ID. A matching provider permission and an
   explicit mapping are both required. An invented mapping grants nothing.
3. Under **Run on this computer**, enter the selected resources and existing
   provider credential. An administrator can leave the Mnemion application key
   blank to issue a dedicated key automatically. Other operators supply that
   application's key. An administrator's own key is refused.
4. Review provider permissions, the scan interval, source RAM and count limit.
   Select **Save and start scanning**. Setup checks the workspace/application and
   provider identity. The first scan checks access to the selected resources;
   inspect its result before relying on captured memories.
5. Keep **Run in background** and **Start at login** enabled for unattended
   capture. Scans need this computer and its network connection.

Selecting resources or confirming the permissions review never overrides their
provider ACLs. Unmapped users, groups, domains and public-link grants do not
become Mnemion readers. Group expansion requires an identity-aware adapter.
Access leases expire when successful permission checks stop. See the
[connector contract](connectors.md) for partial inventories and deletion rules.

## Slack

Use an existing organization-approved Slack token. Enter the workspace/team ID
and one or more channel IDs. The token must belong to that workspace and be able
to read the selected channel details, membership, history and requested threads.
The app verifies the workspace with Slack's `auth.test` endpoint.

The required scopes depend on public/private channel type and Slack token type.
An administrator must approve the relevant read scopes and channel membership.
Some bot tokens cannot read channel threads through `conversations.replies`;
use an authorized token or disable **Include message threads**. Mnemion does not
send Slack messages or download attachment binaries.

The count setting means **messages per channel** for Slack. Pages request at
most 15 messages to respect restrictive history limits; Slack still decides the
actual rate allowance. Large complete histories can exceed the ten-minute scan
deadline. Use smaller selected channels, a suitable interval or an independently
managed adapter for larger histories. Incomplete scans retain previous data.

To use a different Slack workspace, create a separate connection. Replace an
expired or revoked token in source settings. Automatically rotating Slack OAuth
credentials and creating/installing Slack apps are not part of this desktop
setup.

## Google Drive

An administrator supplies a downloaded Google **service-account JSON key**, at
most 8 KiB. Paste it or select the JSON file. Enable Drive API access for its
project and share the selected resources with the service account's email. A
service account is a separate Google identity; it does not inherit access to a
person's My Drive. Organization policies can prohibit service-account keys or
external sharing.

Enter folder/file IDs, or their `https://drive.google.com/` and
`https://docs.google.com/` links. At least one selected file or folder is
required. Recursive folders are optional. Shared-drive API flags are included.
Readable text files and Google Docs/Slides/Sheets exports use the existing
Drive adapter. Ordinary files exposed by a Drive desktop client can instead use
the folder source if service-account enrollment is unsuitable.

Studio uses the key to sign a short-lived assertion for Google's fixed HTTPS
token endpoint, requesting only `https://www.googleapis.com/auth/drive.readonly`.
The resulting access token lives in the helper's memory and is renewed before
expiry during longer scans. There is no domain-wide delegation or user
impersonation. Downloaded JSON cannot redirect token exchange to another host.

The count setting means **files per scan**. File-size and source-RAM limits also
apply. Drive's per-file permissions determine access; sharing a folder with the
service account alone does not map a Mnemion reader. Interactive personal Google
sign-in and organization-approved OAuth enrollment remain roadmap work.

## Credential custody and device controls

The provider credential and Mnemion key are encrypted separately using the
desktop's OS credential facility, without a plaintext fallback. They are passed
to the helper through private stdin. They are omitted from status, reports,
public APIs, logs and source settings shown to agents. The saved ciphertext is
account/device-specific and is not a portable recovery key.

After a successful save, credential fields are cleared. Leave a credential
blank when editing an existing source to retain its saved value. Pause before
editing settings. If the OS store cannot decrypt a key, re-enroll it using the
owning account; do not copy another computer's ciphertext.

**Sources on this computer** permits pause, resume and removal while signed out
or while the workspace is offline. Removal drains the active scan and removes
both saved credentials. Existing memories, provider credentials and server-side
application keys remain; revoke unused keys through their respective account
controls. Scheduled scans and updates use the same bounded queue and shutdown
drain as folder sources.

## Private agent setup

The [desktop operator](desktop-operator.md) keeps the existing `source.status`,
`source.configure`, `source.pause`, `source.sync` and `source.remove` actions.
Read the current revision before a mutation.

For `source.configure`, provide the dedicated Mnemion key in `credential` and
the Slack token or Google JSON string separately in `provider_credential`.
Existing entries can retain either key by omitting its field. Cloud source
objects omit `path` and contain one of:

```json
{"provider":"slack","slack":{"team_id":"T12345678","channels":["C12345678"],"include_threads":true}}
```

```json
{"provider":"gdrive","gdrive":{"folder_ids":["selected-folder-id"],"file_ids":[],"recursive":true}}
```

These selections supplement the common source IDs, endpoint, name, mapped
`members`, resource settings, `enabled` and explicit
`publish_to_mapped_members: true` review acknowledgement. That acknowledgement
does not replace provider permissions. The legacy `max_files` property means
messages per channel for Slack and files per scan for Drive. Credentials belong
in the private request, never inside `source` or a shared configuration snippet.

Provider references: [Google service-account authorization](https://developers.google.com/identity/protocols/oauth2/service-account),
[Drive permissions](https://developers.google.com/workspace/drive/api/guides/manage-sharing),
[Slack history](https://docs.slack.dev/reference/methods/conversations.history/),
[Slack replies](https://docs.slack.dev/reference/methods/conversations.replies/).
