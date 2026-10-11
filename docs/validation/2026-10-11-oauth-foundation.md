# OAuth resource-server foundation validation

Validated **2026-10-11**, isolated `codex/hosted-auth` worktree based on `762c1db`.
This is source validation for the next access increment, not a public release or
a completed sign-in flow. No version number was changed.

## Implemented boundary

- Operator-selected HTTPS issuer, introspection endpoint, secret file and
  admitted workspace UUID; ordinary tenant administrators cannot select them.
- Protected-resource metadata, HTTP challenges, per-tool OAuth declarations and
  runtime MCP authentication error metadata.
- Per-request issuer, audience, optional resource, expiry/not-before/issued-at,
  stable subject/client and access-scope checks through bounded introspection.
- Immutable issuer/subject/client bindings to dedicated hidden credential
  anchors; current Mnemion principals and grants remain authoritative.
- Independent connection revocation, principal disablement, and transaction
  rechecks, including request-derived OAuth expiry.
- Discoverable HTTP/CLI/MCP binding operations and regenerated OpenAPI/agent
  contracts. Existing API keys and operator recovery remain available.

The [operator guide](../service/oauth.md) records configuration and limitations.

## Evidence

All Python runs used the release Python 3.12 environment in a systemd user scope
with `MemoryMax=1G`, `MemorySwapMax=0`, and `CPUQuota=100%`. They used disposable
PostgreSQL with separate non-owner API/worker logins and deterministic embedding
fixtures. No embedding weights or live provider accounts were used.

| Check | Result |
| --- | --- |
| `service_tests/test_oauth.py` | **55 passed**, 7.01 seconds |
| `test_http.py`, `test_transactions.py`, `test_clients.py`, `test_agent_control.py`, `test_request_limits.py`, `test_recovery.py` | **44 passed, 1 skipped**, 27.91 seconds |
| Ruff on changed Python files | Passed |
| `git diff --check` | Passed |
| OpenAPI and agent catalog generation | Passed; includes `oauth.bindings`, `oauth.bind`, `oauth.revoke` |
| TypeScript client build and JavaScript client tests | **8 passed** |
| Required Node client integration with real HTTP/PostgreSQL | **Passed**, 4.87 seconds |
| Combined OAuth, native readiness, memory budget, insights and client tests | **88 passed**, 20.32 seconds |

The initial skipped Node regression was subsequently run with the built client
and `MNEMION_REQUIRE_NODE_SDK=1`. The combined run used a temporary merge of the
OAuth source and native runtime `ff608e5`, with real PostgreSQL, the same required
Node check, and the 1 GiB/no-swap/one-CPU resource scope. It passed without skips.
This integration check predates the native installer and policy-repair changes;
the final integrated source still requires its full release checks.

The OAuth suite covers real PostgreSQL row-level isolation, no implicit space
grants, permitted MCP save/fetch, denied writes, exact subject/client resolution,
immutable mappings, independent connection and API-key revocation, disabled
principals, token expiry between transactions, and issuer revocation between
MCP admission and the backing tool request. Protocol fixtures also exercise
malformed/oversized responses, redirects, duplicate JSON fields, timeouts,
missing scopes, duplicate Authorization headers, and keeping API keys away from
the introspection endpoint. The issuer responses are fixtures; these are not
live OAuth authorization-code or provider compatibility tests.

## Independent review and corrections

Read-only review found that global tuple uniqueness alone would let another
tenant administrator pre-bind a known external subject/client and select the
wrong workspace for that person's future token. The fix requires
`MNEMION_OAUTH_TENANT_ID` from the host operator, rejects out-of-policy binding
creation before either insert, and checks the configured workspace again during
authentication. The regression proves that a competing tenant cannot create a
credential or claim the identity, an external tenant claim is ignored, a stale
binding cannot bypass changed operator policy, and other-tenant API keys work.

Wire-level testing also found that the MCP SDK's core protocol conversion drops
unknown top-level tool fields. The implementation uses the SDK's public response
middleware to retain OpenAI's `securitySchemes` extension in the actual HTTP
response. Runtime challenges remain in the standard `_meta` field.

Documentation distinguishes expiry of request-derived identities from accepted
evaluation/librarian jobs, which retain their persisted credential/permission
contract. Access-token expiry alone is not cancellation. Ordinary indexing uses
the separate service-worker contract after the memory write is accepted.

## Remaining acceptance

Built-in simple personal/team login, invitations, app setup, consent management,
multi-workspace identity admission, reconnection of a revoked pinned identity,
and guided independent recovery remain required. An optional external identity
server does not replace those product requirements.

An actual authorization server must still be configured and tested for PKCE
S256, discovery, CIMD/DCR as required, login/consent, refresh and revocation.
Dot, ChatGPT, Claude, Grok Bot, Hermes and OpenClaw each require separate live
connection, allowed/denied-operation and reconnection evidence. No issue is
closed by these fixtures. Automatic history capture remains a separate source
integration with approval, checkpoints, exclusions and retention handling.
