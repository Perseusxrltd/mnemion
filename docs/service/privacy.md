# Mnemion privacy policy

Updated: **2026-10-10**. This describes the rebuilt shared-memory platform.

## Your organization's data

Mnemion stores the memories, source evidence, revisions, connections, access
records and evaluations supplied to the service. The operator chooses where that
service and its PostgreSQL database run, which sources are connected, who may
access each space and how backups are protected. A desktop installation does not
create a hosted memory account with the project maintainer.

Studio sends requests and memory content to the service address you select.
The connection key stays in the window's memory and is cleared on reload or
disconnect. The server records bounded operational counters and audit history for
authorized administrators; these are not sent to a publisher analytics service.
Evaluation datasets can contain private memory and should receive the same
protection as the source material. Avoid placing secrets in public support reports.

## Network connections

| Connection | Purpose and control |
| --- | --- |
| Your selected Mnemion service | Authentication, memory operations, administration and evaluations requested in Studio or an integration. Disconnect to stop using that connection. |
| Configured Git, Drive, Slack, rclone or custom source | The service reads only sources configured by an authorized operator. Credentials and provider permissions remain the operator's responsibility. Pause or remove the connection to stop ingestion. |
| Local model download host | Model preparation retrieves pinned model files, including from Hugging Face, into the server's model cache. The current local embedding model processes text locally; the download does not upload memories. |
| GitHub and its asset infrastructure | Supported desktop packages check the official stable release feed and download updates by default. GitHub receives normal network request metadata, including the source IP. Memory text, API keys and vault contents are not included in update checks. Disable automatic updates in **Background and updates**, or use the administrator policy in the update guide. |
| External links you open | Your browser contacts the linked site under its own privacy settings. Documentation is bundled for offline use; remote documentation images are presented as links. |

GitHub's [privacy statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement)
and Hugging Face's [privacy policy](https://huggingface.co/privacy) govern their
services. Your organization should review the policies of its chosen storage,
messaging, hosting and model providers. The shared-service cloud model/librarian
options remain planned; future providers must document data egress before use.

## Local storage and lifecycle

Desktop preferences and update files are stored locally. Obsidian exports are
ordinary plaintext Markdown and may contain sensitive evidence. Studio remembers
the service address locally, but does not save the connection key. Protect those
files, the device and any chosen sync destination appropriately. Space permissions
do not encrypt an already exported copy or remove it from someone else's backup.

Background mode, login startup and automatic stable updates are enabled by default
for supported desktop packages. Users can change these in **Background and updates**;
administrators can disable updater/startup defaults through deployment policy.
See the [update and removal guide](updates.md) for package-specific behavior.

Deleting a memory follows the service's deletion policy and removes it from
authorized live retrieval. Independent exports, backups and external source systems
have separate retention rules. Ask your organization's administrator about access,
correction, deletion and retention; the project maintainer does not operate or
have access to a self-hosted organization's database.

Report product security issues through the [security policy](../../SECURITY.md).
For ordinary support, use [GitHub issues](https://github.com/Perseusxrltd/mnemion/issues)
with sanitized examples. Information posted to a public issue is public.
