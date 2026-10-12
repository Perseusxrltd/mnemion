# MCP profile identification — 2026-10-12

**Published in [4.1.3](../releases/4.1.3.md).** Its [release validation](2026-10-12-managed-connectors.md)
includes all six native targets, independent artifact verification and public feeds.

The new read-only `memory_profile` tool exposes the authenticated principal's
existing immutable UUID, display name and workspace label. It carries the
`openai/profile` metadata marker and a strict response schema, following the
[official OpenAI profile contract](https://developers.openai.com/plugins/build/auth).
No email, key, session ID or caller-selected account enters the result.

Seventy local MCP/client/OAuth tests passed using real PostgreSQL and non-owner
application logins. The focused profile checks cover HTTP and stdio, an identity
without any memory grants, two organizations with identical display names,
different credentials for one person, renaming, key revocation, principal
disablement and a new identity after retirement. IDs remain stable for the same
principal and differ for distinct principals. Structured output and its JSON
text representation match the declared schema.

OAuth protocol fixtures verify that the profile marker survives alongside OAuth
security metadata, different accepted tokens resolve to the same profile, and
current authorization remains necessary. The broader regression suite retains
expiry, revocation, tenant isolation and error-privacy checks. Repository lint
and formatting also pass. No database migration or new dependency is required.

This enables clients to label and distinguish already authenticated connections.
It does not supply individual login, invitations, consent, refresh, provider
registration or live ChatGPT/Dot compatibility. Those remain in the
[sign-in implementation contract](../implementation/individual-sign-in.md).
