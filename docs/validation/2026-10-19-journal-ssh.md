# Pinned SSH journal delivery — 19 October 2026

The 4.20 source addresses issue 42 with explicit SSH enrollment, app/private
agent controls and local-versus-network receipt semantics. No original-office
workspace, personal memories, host keys or repository credentials were changed.

**84 focused Python checks pass**, covering the new SSH behavior and existing
journal publication, local enrollment, writeback service and filing contracts.
**55 desktop controller checks pass**, including strict SSH input/snapshot
validation and the existing registration/drain/reopen controls. Desktop process,
TypeScript client and web-renderer builds pass.

A Playwright browser check opens the real built renderer against an isolated
PostgreSQL/API workspace. It uses the actual native identity sanitizer and a
synthetic desktop bridge: the journal panel remains visible, SSH selection shows
the credential fields, both file selections survive, restart review is required,
and the form submits the exact reviewed SSH settings. The rendered form was
visually inspected in the existing Perseus XR theme. This checks renderer wiring;
the mocked picker/restart is not claimed as installed OS-dialog acceptance.

The new tests launch a real isolated OpenSSH server with fresh Ed25519 host and
deploy keys. It serves actual Git repositories. The checks publish Unicode
records, compare the acknowledged commit with the repository head, read back
the exact JSONL bytes, and retry without duplicate records or new commits. A
second writer wins a concurrent push; the first refetches and preserves both.
Credential snapshots use paths containing spaces, Unicode, single/double quotes
and a percent sign. This caught and corrected an OpenSSH identity-path quoting
issue before release. The files are removed after each operation.

A different real host key fails verification. Removing the server's authorized
deploy key prevents further publication. Both failures retain the previous
receipt and repository head; restoring access allows the same event to finish.
Inherited SSH-command and agent variables cannot redirect the transport. The
checks also cover invalid URLs, missing/extra SSH fields, relative paths, linked
or broadly readable inputs, file-size limits and stable pre-SSH destination
fingerprints. Private key bytes and file references do not appear in Git or
public delivery reports.

An integration case enrolls through the actual CLI, then uses HTTP and real
PostgreSQL to enable publication and save an important memory. The HTTP receipt
identifies SSH delivery only after Git acknowledgement; its status commit is
read back independently from the repository. Revoking the deploy key makes the
next important save return a retryable 503, with the prior remote head intact.
Separate service/API checks identify local bare destinations explicitly.

The SSH server fixture runs on Linux under a newly created private temporary
directory. It preserves OpenSSH's strict ownership checks without touching the
user's SSH configuration. Service CI installs OpenSSH and requires these real
tests rather than silently skipping them. This is protocol acceptance on a
synthetic server, not GitHub/provider enrollment, a production-offline recovery
test or a company-scale throughput benchmark. Native packaging, publication,
website refresh and public upgrades remain separate release gates recorded in
[release status](../RELEASE_STATUS.md). Direct SSH acceptance on other operating
systems and provider-managed credentials remain further platform evidence.
