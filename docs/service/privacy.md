# Mnemion privacy policy

Updated: **2026-10-24**. This describes the shared-memory platform, the legacy
library correction and the inactive source telemetry components below.

## Your organization's data

Mnemion stores the memories, source evidence, revisions, connections, access
records and evaluations supplied to the service. The operator chooses where that
service and its PostgreSQL database run, which sources are connected, who may
access each space and how backups are protected. A desktop installation does not
create a hosted memory account with the project maintainer.

Studio sends requests and memory content to the service address you select.
Browser keys stay in window memory and are cleared on reload or disconnect.
Desktop keys are managed outside the renderer; from 4.0.9 an optional remembered
connection uses the operating system's secure store. The interface uses a
temporary handle limited to the selected API. The server records bounded operational counters and audit history for
authorized administrators; these are not sent to a publisher analytics service.
Evaluation datasets can contain private memory and should receive the same
protection as the source material. Avoid placing secrets in public support reports.
Librarian proposals also contain derived memory text and exact quotations; they
remain private to current reviewers of their source space.

## Network connections

| Connection | Purpose and control |
| --- | --- |
| Your selected Mnemion service | Authentication, memory operations, administration and evaluations requested in Studio or an integration. Disconnect to stop using that connection. |
| Configured Git, Drive, Slack, rclone or custom source | The service reads only sources configured by an authorized operator. Credentials and provider permissions remain the operator's responsibility. Pause or remove the connection to stop ingestion. |
| Optional Git journal (4.15.0) | After a host registers a destination and an organization/space administrator explicitly approves it, future native memory changes are sent to that repository. Secret checks run first; Git history retains published text after deletion. Pausing stops pushes while local capture continues. See [journal privacy and recovery](git-journal.md). |
| Optional journal filing (4.16.0) | A separate administrator setting enables readable Markdown views in the displayed notes folder and moves old journals intact into the archive. No language-model service is contacted. Current denials govern the views and replay; published history and external copies remain retained. The journal's pause also stops filing. |
| Local model download host | Model preparation retrieves pinned model files, including from Hugging Face, into the server's model cache. The current local embedding model processes text locally; the download does not upload memories. |
| Approved embedding endpoint | Only operator-configured profiles are selectable. A space administrator must approve sending retained revisions, new memories and search queries to non-loopback destinations. Credentials remain on the server. Pause/cancel candidate indexing or change the active model to control further processing; already-sent text cannot be recalled from a provider. Database restore pauses HTTP active-model processing and candidates for explicit reapproval. |
| GitHub and its asset infrastructure | Supported desktop packages check the official stable release feed and download updates by default. GitHub receives normal network request metadata, including the source IP. Memory text, API keys and vault contents are not included in update checks. Disable automatic updates in **Background and updates**, or use the administrator policy in the update guide. |
| Approved librarian endpoint | Optional processing sends a bounded selection of memory text, titles, tags and summaries to the configured model. It does not upload source attachments. Non-loopback processing requires space-administrator approval; credentials stay on the server. Schedules are opt-in. Pause or cancel to prevent further requests. Already-sent text remains subject to the provider's policies. Restores disable schedules and clear outbound consent. |
| External links you open | Your browser contacts the linked site under its own privacy settings. Documentation is bundled for offline use; remote documentation images are presented as links. |

GitHub's [privacy statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement)
and Hugging Face's [privacy policy](https://huggingface.co/privacy) govern their
services. Your organization should review the policies of its chosen storage,
messaging, hosting and model providers. [Embedding profiles](embeddings.md) support
approved local and cloud endpoints, as does the optional [librarian](librarian.md).
Provider retention, training policies and charges are governed by
the selected provider/operator, not by Mnemion's local model behavior.

## Product analytics and legacy vendor telemetry

Mnemion's [V08 product analytics](../implementation/anonymous-product-telemetry.md)
are **Building, with source-only controls, components and owner wiring; collection remains inactive**.
No V08 measurement instrumentation or collector is deployed.
Source now includes a pre-login/offline `/privacy` page and native
`mnemion-service telemetry` controls. They save a default-enabled preference;
they do not enable collection. The disclosure currently states
`collection_available: false` and `destination: null`, and the payload preview
shows no outbound body and zero outgoing bytes. No product statistics are sent,
and no production analytics or anonymous ingress is deployed. The bounded
sender/collector components and owner wiring remain unreleased; their checks do
not establish installed-app or public-ingress acceptance.
They and this documentation update are excluded from the isolated 4.46.6
dependency-security release.

The app and native process share a persistent preference under the same OS
account and application data configuration. Browser choice is local to that
browser and site and honors Global Privacy Control. Company policy can restrict
collection but cannot force it over a user opt-out. A later collection-capable
build must present its current disclosure before any emission; saving today's
enabled preference does not acknowledge an unknown destination. Damaged or
unreadable settings keep collection off; there is no automatic repair in this
source checkpoint. See the [privacy control guide](../guides/product-telemetry-controls.md)
for offline usage, status and storage limits.

The current [source batch](../validation/2026-10-24-telemetry-app-owners.md) adds
**Telemetry connection settings** and the native/private-stdin `connection_mode`
field: `auto`, `unmetered` or `metered`. Automatic mode pauses delivery when
metering is unknown; an unmetered declaration resolves only that uncertainty;
metered mode pauses delivery. Detected data limits, resource pressure and
privacy restrictions still take priority. The setting persists until changed
without storing a network name or address. A stale opt-out preserves a newer
connection choice, and migration/choice changes retain spent delivery accounting.

Opportunistic desktop/browser and Python service/local stdio owners now have
source checks and an isolated actual-browser journey. CPU admission in that
journey was synthetic; real sensor and resource qualification remains open.
They do not activate collection, add an idle scheduler or flush on
shutdown; the release route address is also null. Unknown native metering and
unsupported browser pressure/heap capabilities can prevent an attempt. Fresh
browser organization-policy refresh, public-ingress metadata/log privacy,
whole-wire/resource limits and all-platform release acceptance remain open.

Explicit native privacy changes may wait up to 250 ms per busy SQLite lock to
accommodate a brief reader. A persistent busy lock can still produce a visible
save failure. Measurement producers and delivery do not wait for those locks.

Private workspace operational counters and security audit records remain
separate. Product telemetry opt-out does not disable those records or the
service, source, model and update connections listed above.

On 23 October, an isolated synthetic check of the legacy Chroma backend reached
**five vendor SDK capture calls** and created a persistent vendor identifier.
The capture boundary was replaced by a **no-send spy**, so those calls could not
submit vendor telemetry. This establishes a configuration gap, not five network
transmissions or proof of any historical successful transmission. An incompatible
signature in the pinned vendor SDK is not a privacy control.

The correction included in [4.46.4](../releases/4.46.4.md) explicitly disables
the vendor telemetry component for Mnemion's legacy clients. Its isolated
regression recorded no vendor calls, network attempts or new identifier while exercising real local
storage. **Frozen 4.46.3 does not include this correction.** The change neither
deletes an existing third-party Chroma identifier nor changes settings for other
Chroma applications. The [dated validation](../validation/2026-10-23-legacy-vendor-telemetry.md)
records the evidence and release limits. The selected-service, source, model
and update connections listed above retain their stated controls.

## Local storage and lifecycle

Desktop preferences and update files are stored locally. Obsidian exports are
ordinary plaintext Markdown and may contain sensitive evidence. Studio may remember
the service address locally. From desktop 4.0.9, an opted-in saved connection also
records its workspace/identity names and identifiers, address, last-use time and
an OS-encrypted key. Windows protection, macOS Keychain and supported Linux
keyrings supply encryption; unavailable stores never fall back to plaintext.
On Windows the bundled local helper uses current-user DPAPI over private process
pipes, without secrets in arguments or environment variables. Another program
running as the same OS user is outside this protection boundary.
Disconnect clears the live credential and pauses reconnection; Forget removes
the saved device bookmark without revoking the server key or deleting memories.
Session-only keys disappear on desktop app exit or disconnect. See
[workspace connections](workspaces.md). Protect those files, the device and any
chosen sync destination appropriately. Space permissions
do not encrypt an already exported copy or remove it from someone else's backup.

Background mode, login startup and automatic stable updates are enabled by default
for supported desktop packages. Users can change these in **Background and updates**;
administrators can disable updater/startup defaults through deployment policy.
See the [update and removal guide](updates.md) for package-specific behavior.

From 4.0.8, explicitly adopted Linux/macOS services also check GitHub for signed
compatible patches by default. Locked dependency installation contacts the
package locations in the signed release. These requests contain normal network
metadata, not memory text or database credentials. Local operators can pause
automatic service checks through `mnemion-service updates preferences`.
Verified pre-update database backups are private local files under managed state;
the updater retains three unchanged copies it created. They contain sensitive
workspace data and need the same protection as the database. See
[managed updates](managed-updates.md) for retention and separate host authority.

Studio bundles Inter and Outfit locally, including their redistribution licenses.
Opening a screen or offline guide makes no requests to a font provider.

Deleting a memory follows the service's deletion policy and removes it from
authorized live retrieval. Independent exports, backups and external source systems
have separate retention rules. Ask your organization's administrator about access,
correction, deletion and retention; the project maintainer does not operate or
have access to a self-hosted organization's database.

Report product security issues through the [security policy](../../SECURITY.md).
For ordinary support, use [GitHub issues](https://github.com/Perseusxrltd/mnemion/issues)
with sanitized examples. Information posted to a public issue is public.
