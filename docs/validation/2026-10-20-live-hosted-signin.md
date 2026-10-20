# Hosted sign-in over an actual public HTTPS route

Recorded 20 October 2026 (Europe/Paris); execution was 19 October at 21:46–21:57
UTC. The existing independently supervised host ran **4.17.0**. Endpoint,
organization/person identifiers, private inputs and memory contents are omitted.

## Deployment repair

The public authorization and protected-resource metadata both returned 404:
built-in OAuth was not enabled in the persistent Supervisor environment.
The operator saved the exact private configuration, enabled the already shipped
OAuth mode for the existing shared organization and stable HTTPS origin, and
restarted the service. Runtime, intentional manual update policy, organizations
and existing agent grants were retained. A rollback procedure was prepared;
the configuration and startup checks passed without using it.

## Actual HTTPS acceptance

The test used a temporary nonadministrator person with reader access to one
existing space. It completed dynamic registration, S256 PKCE, origin/cookie/CSRF
bound consent, matching state and issuer, code exchange, MCP initialization,
16-tool discovery and exact fetch of a known memory. Write and administration
requests were denied. Refresh invalidated the preceding access token; removing
the space grant immediately prevented the read. Revoking the connection denied
both access and refresh.

The temporary ordinary device session was signed out, the reader grant removed,
the OAuth connection revoked and the principal disabled. Both pre-existing
agent credentials still passed exact MCP fetch. The original memory and owner
login configuration were unchanged. The original owner had no personal password;
enabling OAuth alone does not create one or enroll a human account.

A fresh encrypted full host snapshot and newer access ledger were delivered
through the existing private off-host Git pipeline. A separate authenticated
GitHub manifest read confirmed the delivered commit and both ciphertext hashes,
after the configuration change and test cleanup. Private operation logs and
receipts remain outside the public repository.

## Remaining named-provider acceptance

This was actual public HTTPS protocol acceptance, **not a ChatGPT UI test**.
The available Windows session was locked and the test browser had no signed-in
ChatGPT account. Issue [18](https://github.com/Perseusxrltd/mnemion/issues/18)
remains open for supported ChatGPT registration, consent and tool discovery.
The separate general OAuth request in
[4](https://github.com/Perseusxrltd/mnemion/issues/4) is addressed by the actual
scoped protocol, rotation and revocation checks above. Its reviewed release
association uses published 4.29, whose native/public update checks passed and
whose [live upgrade retained these identities and access](2026-10-20-shared-workspace-429.md).
That bounded closure does not claim ChatGPT acceptance. The later
[remote-access review](2026-10-20-remote-access-issue.md) separately verifies
issue 3's original scope and diagnostic follow-up. Live managed-ngrok account
acceptance remains separate from the existing HTTPS proxy. No paid service, trial, hosted model
call or provider enrollment was used.
