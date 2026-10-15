# Guided company-provider setup

Source milestone: **4.11.0**, reviewed on **2026-10-15**. Published installers,
native delivery and automatic updates are tracked separately in
[release status](../RELEASE_STATUS.md).

## Scope

The [company guide](../service/company-sign-in.md) describes setup for an
app-owned host: the existing workspace and HTTPS callback, OIDC metadata review,
client configuration, private CA trust, session length, removal and damaged-file
repair. The private desktop catalog adds discovery and configuration operations;
HTTP/MCP memory authority does not acquire host configuration.

## Focused checks

**47 service checks** passed across `test_local_company.py` and
`test_local_remote.py`, including the additional existing-environment acceptance
check. **50 desktop checks** passed across the local controller and actual
Python/Node private-operator protocol suites, including the readiness-read race
found in the browser walkthrough. Repeated checks are not counted twice.

The checks cover private secret exclusion, current workspace/company/HTTPS
revisions, interrupted atomic replacement, retained damage evidence, bounded
metadata/TLS input, provider changes requiring explicit secret review, and
preservation of existing explicitly configured server environments. A real
PostgreSQL API check distinguishes the local host identifier from its service
tenant; the provider is offered only to the correct service workspace.

Desktop checks cover drain/write/reopen, explicit stop preventing reopen,
stale configuration leaving the running host alone, rejected unconfirmed
responses, private discovery and ordinary readiness inspection. A discovery
click immediately after restart now waits for an existing status read instead
of returning an unnecessary busy error. Other mutations retain their guards.

## Actual browser and native-controller walkthrough

An isolated Linux workspace used the current Python engine, PostgreSQL **18.6**,
the real CPU **BGE Small English** model and the actual `LocalWorkspace`
controller. A private loopback fixture connected the browser screen to that
controller. This is source/controller evidence; it is not an installed Electron
IPC or all-platform acceptance claim.

The provider was **Dex 2.46.0**, reusing the previously verified fixture binary,
with a fresh private CA and a confidential OIDC client. The walkthrough:

- Configured HTTPS through Studio, read the provider's actual discovery
  document with the supplied CA and reviewed the callback/client/endpoints.
- Saved through the native controller, stopped/reopened the real local service
  and confirmed the provider appeared under the correct tenant.
- Joined through a real first-login invitation, authenticated at Dex,
  exchanged the authorization code using `client_secret_basic` and entered
  the authenticated memory UI. The invitation bound the signed OIDC subject.
- Observed Secure/HttpOnly remembered-session cookies, no access or refresh
  credentials in browser storage, and no saved client secret in operator/API
  status. The original independent administrator key remained usable.
- Confirmed that an expired login and an unlinked provider subject were refused.
- Inspected the screen and a **390 px** layout; document width stayed **390 px**.

Synthetic credentials, provider files, raw protocol details and screenshots stay
outside public evidence. Public examples use reserved placeholder addresses.

## Release observations and remaining acceptance

The preceding **4.10.0** release's first Windows ARM attempt failed during
restored-copy reopen with only `setup_failed` reported. A single focused retry
used the same frozen source and passed. Version 4.10.0 was published at
**2026-10-15 14:20:26 UTC**; [website verification](https://github.com/Perseusxrltd/mnemion/actions/runs/38750512242)
and [all six public automatic updates](https://github.com/Perseusxrltd/mnemion/actions/runs/38750517752)
passed. This
milestone includes the existing bounded setup diagnostic in that recovery probe
so a future failure reports safe code locations/categories. It does not claim
to have fixed the unidentified cause of the first attempt.

Guided remote-host configuration, provider account creation, automatic
provisioning, company-only policy, named hosted-assistant acceptance and company
fleet/device policies remain open. Normal native installer, publication and
public-update gates are still required. This advances F08, A01/A08 and U01
without closing their full scope; strict completion remains **17/64 (26.6%)**.
