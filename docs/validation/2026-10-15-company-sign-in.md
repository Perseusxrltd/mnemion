# Company sign-in validation — 15 October 2026

The 4.9.0 source adds optional organization-owned OpenID Connect sign-in,
company identity links, private invitation acceptance, protected device sessions
and app/agent administration. The [guide](../service/company-sign-in.md) records
configuration and limits. This record is source and local-provider evidence;
[release status](../RELEASE_STATUS.md) independently tracks installed platform
gates, published artifacts, the website and public automatic updates.

## Service, agent and upgrade checks

The combined real-PostgreSQL access/migration/recovery selection passed **81
tests**. It includes 25 company checks with a signed protocol peer, existing
password/session flows, origin and CSRF policy, restored-access reconciliation
and upgrades from five preceding immutable schemas. Company cases cover:

- Correct issuer, audience, signature, nonce, PKCE and bounded token claims;
  malformed identities and untrusted token key locations cannot authorize access.
- No account or authority creation from an email address or provider role claim.
- Current invitation permissions, single-use concurrent acceptance, revoked
  links, immutable subject ownership and policy changes.
- Browser/native transport separation, protected cookies, pinned callbacks,
  refresh replay and immediate local revocation.

A further **19 agent/upgrade checks** passed after regenerating both public
schemas. They exercise private CLI input/results, suppression of unrelated
bearer keys on login, no automatic retry of uncertain company authentication,
the reviewed catalog and preservation of an existing pre-018 password session.
The preserved session authenticated and rotated successfully after migration;
its identity, expiry and prior row fields were unchanged.

## Desktop connection checks

**Six company-controller checks** and **30 existing native sign-in/connection
checks** passed. The new cases use an actual temporary loopback HTTP listener
with the normal protected-store/connection classes:

- Complete callback, hidden credentials, encrypted storage, restart and refresh.
- Rejection of wrong hosts, origins, states, paths and duplicate authorization codes.
- Cancellation during login start and during token exchange; a late issued
  session is signed out and never saved.
- Provider decline and refusal to replace a company's authentication method
  during refresh.

The store fixture uses authenticated encryption; it does not claim to exercise
each platform's real Keychain/DPAPI/keyring or system-browser launcher. Those
existing native distribution gates remain separate. SDK, web and Electron
TypeScript builds passed during implementation; final release checks run on the
committed source through the established pipeline.

## Actual Dex and browser acceptance

Used the official **Dex v2.46.0** Linux amd64 image, manifest
`sha256:fd4ab5d117005b927433133f1d7db7cc30fbb537c377912b75b349edff47df01`.
Downloaded layers were digest-verified; only its executable and web assets were
extracted into an isolated temporary test directory. No paid service, external
company account or production workspace was used.

Dex used a real password database, an authorization-code public client with S256
PKCE enforced and HTTPS on loopback. Mnemion validated provider TLS against the
explicit private test CA. The browser accepted that test certificate in its
isolated test context; no operating-system trust setting was changed.

The actual compiled Studio and service completed this sequence:

1. Preview an administrator's first-login invitation and assigned memory spaces.
2. Open Dex in a separate browser window, enter the synthetic company login and
   approve the requested OpenID identity.
3. Return to the correct Mnemion person and organization, without a personal
   Mnemion password or provider role-based account creation.
4. Inspect the linked company account and its device session in the app.
5. Confirm a Secure/HttpOnly/SameSite=Strict remembered refresh cookie and no
   login credentials in local or session storage.
6. Reload, choose **Continue**, and rotate the remembered company session.
7. Revoke company access in the app; return to the welcome screen with the saved
   login removed. Independent authenticated inspection confirmed both the link
   and associated session were revoked, while the original administrator key
   still worked.

A separate native flow used the compiled `WorkspaceCompanyAuth` controller,
the actual service and Dex. The browser completed the provider login and
redirected through the service into the controller's real temporary loopback
receiver. The resulting company session authenticated as the invited person;
native logout immediately invalidated its access. Node trusted only the explicit
test CA for this exercise. This validates the actual redirect/callback protocol
on Linux, while the OS-specific launcher and secure-store gates remain separate.
The documented private provider JSON also loaded using Dex's real discovery
endpoints and the configured CA bundle.

All **14 SDK checks**, **36 focused native connection checks**, final web and
Electron builds, dependency lock validation and repository lint/format checks
passed before integration. The frontend was visually inspected in the existing
Perseus XR theme. The
company panel was moved before optional password creation, provider spacing was
corrected and session durations use hours where appropriate. Authorization
failures immediately after self-revocation are expected; follow-up refreshes are
skipped when that action disconnects the current account.

## Remaining acceptance

This validates one actual free provider and one local browser environment. It
does not establish acceptance for every company's issuer, MFA configuration,
corporate device policy or native operating system. Provider back-channel
logout, provisioning/group mapping, mandatory company-only policy and company
sign-in for hosted-agent consent remain open. The full 64-requirement scope and
**17 shipped requirements (26.6%)** are unchanged.
