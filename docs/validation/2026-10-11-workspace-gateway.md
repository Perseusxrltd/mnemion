# Native workspace gateway and Windows baseline validation

Validated on 2026-10-11. Private addresses, keys, identities, source files and
operator screenshots are excluded from this report and remain outside Git.

## Live host and bounded Windows client

The existing Grok Bot Windows client exposed an independent **Computer → Wake**
control. Waking its sleeping computer restored its existing Mnemion service and
tunnel without an agent prompt, new account, installation or provider purchase.
Authenticated health, identity, two accessible spaces and eight MCP tools then
passed. The supplied identity remains a contributor/reader, not an organization
administrator; no privileges were changed.

The private Windows check completed 40 lexical recalls, limited to two requests
per second and four in flight. All 40 succeeded in 20.511 seconds: p50 315.10 ms,
p95 345.08 ms, maximum 490.16 ms. Peak client RSS was 45,453,312 bytes, with at
least 1,739,739,136 bytes of free system RAM. No memory writes or model calls were
made. This is a bounded connectivity baseline, not a capacity or retrieval-quality
claim. The local one-click checks retain stop conditions and private reports.

## Reproduced failures and correction

The original diagnostic called health routes without authentication. This
gateway replied 401 while the same key successfully reached identity, spaces
and MCP. Version 4.0.12 retries an authenticated health route once at the same
destination. Sixteen diagnostic tests cover public/protected routes, unavailable
tunnels, absent/rejected credentials, redirect handling, secret-free reports,
size limits and deadlines.

The installed Windows 4.0.10 app still reported an offline tunnel. Its HTTP cache
contained the earlier error. A separate, upstream-checksum-verified native
Electron 44.7.0 process reproduced the behavior with a disposable profile and a
loopback fixture: after the fixture recovered, the original request still
returned cached 404, with only one request reaching the server. The production
4.0.12 transport helper immediately reached the server and returned 200. After
revocation it returned 401; a redirect was rejected with zero requests to its
destination.

Against the authorized live host, the original native browser request returned
the ngrok browser warning instead of an identity. The corrected production
helper returned a valid identity over verified HTTPS. Only validated statuses
and booleans were retained. The native check had a 512 MiB process-tree limit,
16-process ceiling and finite deadlines; its temporary runtime/profile were
removed. The real installed app and updater were not modified for this probe.

The complete Electron suite also passed, including an HTTP integration test for
gateway compatibility, request-body/header preservation, current authorization
and redirect rejection.

## Acceptance still required

The native transport probe is not a released-app reconnection or an automatic
upgrade proof. Publish the verified patch, connect through the actual Windows
app, retain its encrypted bookmark, and verify restart/update behavior. The
earlier unmodified Windows 4.0.9 → 4.0.10 unattended update proof remains valid.

Waking a provider-managed computer does not establish always-on availability.
The [continuity contract](../implementation/workspace-continuity.md) still requires
independent human administration, registered recovery hosts and backups, delegated
operator controls, safe restoration/takeover and complete agent parity. A Git
source mirror is not the complete database, current membership or deletion ledger.
