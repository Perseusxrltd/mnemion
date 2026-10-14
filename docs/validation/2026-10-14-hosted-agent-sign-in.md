# Hosted-agent sign-in validation

Validated **14 October 2026** for the 4.3.0 implementation. The
[published release record](../RELEASE_STATUS.md) supplies the separate source,
native installer, migration, signature and public-update gates. This document
records feature validation, not live acceptance by a named assistant provider.

## Authorization and regression checks

**71 tests passed** across `test_hosted_oauth.py`, `test_oauth.py` and
`test_web_studio_http.py`, using real PostgreSQL and the actual HTTP handlers.
They cover:

- Registration, discovery, explicit consent, code exchange, refresh and revocation.
- Client, callback, resource and PKCE substitution; origin and browser-proof
  binding; permission changes between review, approval and exchange.
- One-use code and refresh replay, concurrent redemption, member permissions
  and rejection of another person's revocation request.
- Password reset and actual backup restoration, proving that existing tokens
  and pending consent cannot regain access.
- Real MCP tool discovery and rejection after connection revocation.
- Cancelled approval, preserved state and issuer, malformed or oversized
  protocol input, external-issuer compatibility and browser response policy.

The focused suite and browser fixture run under a bounded local memory/CPU
scope. Deterministic fixture embeddings avoid downloads, cloud models and
production memory access. This is not a performance or retrieval-quality benchmark.

## Browser acceptance

A headless Chromium browser exercised the built Studio against a disposable
HTTPS service with real PostgreSQL and an unprivileged application role.
The flow entered a personal password, reviewed permissions and selected
**Allow connection**. The callback preserved state and the exact issuer.
S256 code exchange succeeded, authenticated `GET /v1/me` worked, the real MCP
endpoint listed **16 tools**, refresh rotated successfully and revocation
caused the old access credential to receive `401`.

Desktop and 390 × 844 mobile layouts were inspected. The mobile exercise found
and corrected a consent-page scroll constraint; actual wheel scrolling then
reached the approval controls. Browser local storage held no credential or
pending authorization proof. No real provider account or production workspace
was used.

The app's **Account & sessions** page also displayed the revoked app, its
connection date and person, separately from the active browser device session.
The TypeScript client and production Studio build passed. OpenAPI and the
reviewed agent catalog are regenerated during release preparation.

The first full release run found that the older upgrade fixture still expected
migration 015 and only its new tables. The fixture now verifies transitions
from schemas 013, 014 and 015, including the actual installed gate's row hashes,
existing keys, grants and memory, and empty new OAuth tables. Its acceptance
criteria retain data-preservation and schema-race checks.
All three real PostgreSQL upgrade cases passed after the fixture correction.

## Compatibility and remaining acceptance

Migration 016 adds bounded client/authorization storage and connection records,
reusing existing revocable password-session anchors. Existing native keys and
external issuer mode retain their own authentication paths. Built-in OAuth is
disabled unless an operator selects it, a workspace UUID and a public HTTPS origin.

Provider-specific consent and reconnect must still be exercised in each named
client. These fixtures do not establish ChatGPT, Dot, Claude, Grok Bot, Hermes or
OpenClaw compatibility, enterprise verified email, CIMD, SSO enrollment or a
multi-workspace login chooser. Requirements A03, A08 and C05 remain partial.
