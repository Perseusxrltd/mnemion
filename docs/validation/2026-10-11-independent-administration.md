# Independent workspace administration

Validated **2026-10-11** in the 4.0.11 candidate. Publication still requires the
complete native release gates; this report covers the stated source/UI change.

## Gaps found and corrected

The service already permitted an organization administrator to create another
administrator. Studio and its TypeScript convenience method omitted that choice.
In addition, all authenticated Studio routes were behind a memory-space gate:
a new administrator without a space grant could sign in but could not open
People & apps. Creating a needless private space was an accidental workaround.

Studio now offers an explicit organization role with member as the default,
shows an organization roster and prepares the separate individual-key form.
Organization administration, Connections, Setup and help no longer require a
content-space grant. Space-grant administration selects its target explicitly;
it does not select or fetch private memory contents to enable administration.
The existing server permission and tenant boundaries remain authoritative.

## Evidence

- Two real PostgreSQL/API tests: an independently created human administrator
  continues after both original administrator identities are disabled; an
  organization administrator cannot issue a different tenant's keys. Ordinary
  members cannot create administrators. Content access requires an explicit
  grant even for the new administrator.
- TypeScript client tests cover explicit administrator creation and the ordinary
  default for the following call, with no automatic retry of administrative
  creation. The frontend type check and production build passed.
- A real Chromium journey against a disposable PostgreSQL service first
  reproduced the space-gated administration failure. The corrected build then
  created and used an individual administrator key, opened administration with
  no content grant, managed an explicitly selected space grant without fetching
  memory content, and remained usable after the original identity was disabled
  through the authenticated API.
- The browser created and signed in as an ordinary assistant, confirmed that
  administration navigation was absent, verified server refusal of an attempted
  administrator creation, and verified refusal of the direct administration UI.
- Desktop and 390-pixel mobile screenshots were inspected. No browser exceptions
  or document-width overflow occurred. The key-form shortcut retained the
  workspace route. Fixture credentials and full-key displays are excluded from
  public evidence.

The browser service used a deterministic embedding fixture because the scenario
tests administration, not retrieval quality. No personal workspace was changed.
This does not prove completed personal/company sign-in, invitations, host
registration, remote restart, portable recovery credentials, failover or offline
recovery. Those remain in the [continuity contract](../implementation/workspace-continuity.md).
