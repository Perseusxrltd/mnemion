# Remote-access issue acceptance

Reviewed on 20 October 2026 against published **4.29.0** and
[issue 3](https://github.com/Perseusxrltd/mnemion/issues/3), including its
11 October diagnostic follow-up. Private addresses, keys and identifiers are
omitted.

## Reported scope and delivered behavior

The original report requests an official remote-access mode: a built-in tunnel,
invite URL **or documented proxy profile**, without requiring operators to invent
the integration. The follow-up asks for bounded, read-only diagnostics that
separate host readiness, public route availability, MCP authentication/protocol
and actual space permissions.

Published 4.4 introduced [app-managed remote access](../service/remote-access.md)
and equivalent local-agent controls. It includes the official ngrok SDK,
supervised reconnection, stable configured origins and an existing-HTTPS mode.
The [deployment guide](../service/deployment.md#network-access-and-resource-settings)
includes the same-origin Caddy profile; [background supervision](../service/supervision.md)
works without systemd. Public account sign-in and independently scoped keys
share the configured API/MCP address. The
[diagnostic command and guidance](../service/connection-diagnostics.md#read-only-diagnostic-for-people-and-agents)
distinguish offline tunnels, TLS/routing, identity and missing grants without
changing the host or credentials.

## Evidence

- The [native remote-access exercise](2026-10-15-native-remote-access.md)
  configured the real app/controller against a TLS proxy, retained local access
  through proxy failure, recovered after reconnection and verified public links.
  Every native target loads the actual compiled ngrok SDK. The provider lifecycle
  cases use a double, not a live ngrok account.
- The actual independently supervised shared host serves external clients over
  stable, publicly trusted HTTPS. [Public OAuth and scoped MCP access](2026-10-20-live-hosted-signin.md)
  passed, and [the managed 4.29 upgrade](2026-10-20-shared-workspace-429.md)
  retained both existing agent identities, permissions and MCP access. The
  original agent and its model quota are not needed to administer this host.
- A fresh `mnemion-control doctor` on 20 October returned exit 0 against that
  live host: service, readiness, identity, spaces and MCP all passed. The
  nonadministrator account had five explicit grants: two contributor and three
  reader. MCP negotiated `2025-06-18` and listed 16 tools. The diagnostic code
  is unchanged from the published 4.29 source. Its report contains only fixed
  codes, booleans and counts; it reads no memories and triggers no model call.
- Published 4.29 and all six native/public installed-update checks passed.

This fulfills the bounded original report and its diagnostic follow-up. The
reviewed release association is **4.29.0**. Issue closure does not assert live
ngrok-account enrollment, provider outage recovery, a never-sleeping host,
automatic failover or ChatGPT UI acceptance. Those remain explicit broader
requirements; [issue 18](https://github.com/Perseusxrltd/mnemion/issues/18)
retains its actual ChatGPT sign-in/tool-list acceptance.
