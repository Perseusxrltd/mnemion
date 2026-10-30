# Workspace sign-in deadlines and transport guidance

30 October 2026. Actual Windows Grok Build authored candidate
`f167bc71bb0c3006adec6db1dd2a9ed8a92b7554`. Astra reviewed the source, tightened
bounded error handling and ran the focused checks.

## Observed problem and correction

A Windows password sign-in returned an unconfirmed failure at its 20-second
deadline. A later read of the same user's sessions found that the server had
created a matching session after that response. This establishes an uncertain
delivery, not a rejected password. Password login and invitation acceptance
now have a 60-second deadline. Refresh, logout and other sign-in requests keep
20 seconds; identity verification keeps 15 seconds. The exact source of the
server delay remains unresolved.

Both sign-in and identity verification use a shared error boundary. Exact,
allowlisted platform codes select fixed DNS, TLS, proxy, timeout, connection
or redirect guidance. Unknown or malformed values retain a generic message.
The parser bounds token lengths, traversed objects and aggregate children;
it does not execute property getters or copy raw failures into messages,
causes or logs. Descriptor failures and mixed classifications remain unknown.

The boundary calls the existing transport once. HTTP responses retain their
status, and requests keep `no-store`, `redirect: error` and omitted ambient
credentials. Password storage, identity checks, revision/generation fences
and cancellation guards are unchanged. No automatic sign-in retry was added.

## Qualification

The Linux review checkout passed its Electron TypeScript/native-helper build
and **76 focused checks**, with no skips. These cover the new error boundary,
fetch behavior, sign-in, saved connections, desktop workspace actions and
protected workspace storage. Negative cases include private exception text,
throwing accessors/proxy descriptors, oversized tokens, malformed aggregates
and conflicting failure classes.

This is source qualification. It does not establish that every proxy or OS
emits an allowlisted error, fix a stopped host, or prove that the longer
deadline eliminates every slow response. Native release and public-update
results are recorded separately in [release status](../RELEASE_STATUS.md).
