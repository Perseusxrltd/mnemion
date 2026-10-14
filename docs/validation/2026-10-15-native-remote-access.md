# Native remote access validation

Source batch: **4.4.0**, reviewed on 15 October 2026 (Europe/Paris).
[Release status](../RELEASE_STATUS.md) records actual publication and platform
gates. Source checks below are not a claim that all installers have shipped.

## Service and controller checks

The remote-access and local-address suites passed **30 tests in 12.85 seconds**.
Coverage includes private credential persistence, sanitized status, revision and
workspace binding, interrupted writes, damaged-file repair, the running-host
lock, strict URL controls, a fresh ASGI challenge, rejection of redirects,
oversized/compressed responses and forged proofs, stale process observations,
explicit OAuth/invitation origins, owned provider-session teardown and coalesced
manual checks. Provider lifecycle tests use an SDK double; they do not establish
live ngrok account acceptance.

The preceding selected service run passed 53 tests across remote access,
readiness, personal sign-in and hosted OAuth, with one new fixture error. That
fixture used a nonexistent helper; it was corrected to create the identity
through the real API and passed in the 30-test run above.

The desktop local-workspace suite passed **29 tests**. It covers the existing
host lifecycle and the new configuration operation, including drain before
write, revision checks, restart, failed-write recovery, and preventing an
unwanted reopen after a concurrent stop or app close. Native builder/source
inventory tests passed **14 tests**. The generated web bundle is excluded from
the source-input fingerprint and retained in the complete output inventory,
so sharing a Windows x64 engine with the Windows ARM desktop does not depend on
an untracked staging directory. Client, Studio and Electron builds passed.

The full desktop command subsequently passed **134 tests** (123 ordinary tests
and 11 update-controller tests); the TypeScript client passed **14 tests**.
Repository lint/format checks, the locked dependency check and final Studio
production build passed. Final review found that operator-supplied expanded
IPv6 or shorthand IPv4 could be stored differently from a browser's canonical
origin. Normalization now agrees across the boundary; **9 focused origin checks**
passed, including persistence/reload of those addresses. The installed SDK
reported 1.7.0 and included both its MIT and Apache-2.0 license files for the
existing release notice inventory.

## Real local host and browser walkthrough

A disposable Linux workspace ran the production local-workspace controller,
source engine, verified PostgreSQL bundle and a real pinned BGE CPU model.
Initial readiness saved, indexed and retrieved its synthetic memory. The
browser's private fixture bridge called the actual controller; it was not an
installed Electron application or an OS credential-store check.

The real interface changed from Off to an existing HTTPS proxy, restarted the
workspace and reported a successful route check. A loopback TLS proxy forwarded
the complete site. Its ephemeral CA was trusted only by the child engine; TLS
verification remained enabled in the route checker. The test did not modify
system trust, contact a cloud model or use a real ngrok token.

Turning off that proxy produced **Connection unavailable**, while authenticated
local `GET /v1/me` still returned 200. Re-enabling it and requesting a check
restored **Last check passed**. Workspace and MCP copy fields used the configured
HTTPS origin. The token input was masked, and changing away from ngrok cleared
the unsaved dummy token without submitting it. The 390-pixel layout had matching
viewport and document widths, and the controls and addresses wrapped visibly.

**Account & sessions** displayed a sign-in link using the public HTTPS origin.
A separate browser context loaded the real hosted consent page over the fixture
proxy and displayed the expected incomplete-request message. It had no local
operator bridge. That browser context accepted only the test certificate for
the walkthrough; the production route checker continued verifying its scoped
CA. The initial check used the wrong expected message text and was corrected
without a product change. The browser and disposable host then closed, and
the controller reported clean shutdown.

## Native release gates and limits

Every target's installed-hosting gate now imports the actual compiled ngrok
SDK and requires version 1.7.0. It also fetches the hosted consent page and its
absolute web-script asset from the installed native API. The existing installed
setup, real inference, reopen, policy, migration, recovery and automatic-update
gates remain required. Their final results are retained by release automation.

The local HTTPS exercise does not prove a free provider account's live tunnel,
corporate network access, named AI-provider acceptance, every OS version, host
wake or independent failover. No payment, trial, actual shared-workspace write
or production host reconfiguration was performed. Those broader requirements
remain open in the [complete tracker](../PRODUCT_REQUIREMENTS.md).
