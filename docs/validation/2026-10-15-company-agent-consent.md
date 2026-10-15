# Company accounts authorize assistants

Source milestone: **4.10.0**, migration **019**. Reviewed **2026-10-15**.
This records source and protocol acceptance. Installer, publication, website
and public automatic-update gates are tracked separately in
[release status](../RELEASE_STATUS.md).

## PostgreSQL and authorization boundaries

**70 focused checks passed** across company consent, existing hosted OAuth,
company Studio sessions and previous-schema upgrades. The suite uses real
PostgreSQL and restricted application logins. A signed deterministic OIDC peer
exercises malformed claims separately from the real provider check below.

- A linked company user with no personal password can review, approve, query,
  refresh and revoke an assistant connection. Consent preserves the existing
  protected Studio cookie and creates no extra Studio session.
- The original browser, consent request, selected workspace, company policy and
  one-use login purpose are required. Cross-origin or missing-CSRF requests,
  substituted browser/ticket, native-channel substitution and using an assistant
  handoff as a Studio login fail. Rejected CSRF does not consume a valid login.
- Unknown subjects do not create users from email, verification or provider
  role claims. A member's assistant retains its actual space role and cannot
  create an organization space without the required authority.
- Link revocation, disabled people, changed/removed host policy and absolute
  expiry are checked through review, code exchange and token use. Changed space
  grants during review require new approval. Refresh preserves the original
  absolute deadline; code/refresh replay revokes the affected connection.
- Password-only SQL entry points reject company sessions even when their UUID
  versions are deliberately made equal. Switching the review to a password
  clears its company binding and invalidates the earlier proof.
- Upgrades from schemas 013–018 preserve existing keys, grants and memory. The
  pre-018 check preserves an existing personal device session. The pre-019 check
  also preserves actual personal OAuth request/session rows, access, refresh and
  an already reviewed pending approval through migration 019.
- Real backup restoration cannot revive company assistant access, refresh,
  reviewed consent or an unfinished company handoff. Existing personal OAuth
  recovery checks also pass.

The first local run found an old packaged UI in the development checkout;
subsequent source checks used the explicitly built matching Studio directory.
One recovery run used PostgreSQL client tools from a different server version;
it passed with the matching tools. Neither required weakening product checks.

## Actual company provider and MCP client

An isolated TLS workspace used **Dex 2.46.0**, the same digest-verified provider
artifact recorded in the [4.9 company check](2026-10-15-company-sign-in.md).
Its database, users, invitations, certificates and credentials were disposable.
No production workspace or external company account was used.

Chromium completed a real company invitation and remembered Studio login. The
**MCP Python SDK 2.3.0**, with **httpx2 2.13.1**, then independently discovered the
protected resource, dynamically registered its loopback callback and opened the
OAuth authorization page. The member authenticated with Dex, reviewed contributor
permissions and the absolute expiry, and approved the SDK client.

The SDK completed PKCE exchange, MCP initialization, tool discovery and
`memory_search`. Direct API checks verified the member identity and contributor
role, and denied an administrator-only operation. Refresh rotation invalidated
the previous access token. An independent administrator revoked the app; the
next MCP request returned 401. Service and provider requests verified the local
test CA; browser certificate bypass was confined to the disposable browser context.

Browser inspection confirmed that the existing protected Studio cookies were
unchanged by consent. The saved company login resumed afterwards. Login secrets,
provider handoffs and assistant tokens did not enter local/session storage.
The permission review fit a **390-pixel** viewport without horizontal overflow.
Browser, SDK callback, Dex and PostgreSQL fixture processes were closed after
acceptance.

## Delivery and remaining limits

The final **4.10.0** TypeScript client, web frontend, desktop frontend and Electron
main-process builds passed. Repository-wide Ruff checks and formatting passed,
both Python dependency locks verified offline, and the scripted package-version,
OpenAPI, agent-contract and roadmap preparation passed. Native installer and
public delivery evidence belongs to the normal release pipeline.

This proves the generic company-account flow with a real local OIDC provider and
MCP SDK. It does not prove live acceptance in ChatGPT, Dot, Claude, Grokbot,
Hermes or OpenClaw, every enterprise identity provider, or restricted-device
policies. Automatic provisioning, group mapping, company-only admission,
back-channel logout and guided remote provider setup remain open. A company
provider's upstream account removal requires local revocation for immediate
Mnemion enforcement; otherwise the configured absolute lifetime bounds access.
