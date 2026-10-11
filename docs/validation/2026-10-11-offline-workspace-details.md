# Offline saved-workspace details

Validated **2026-10-11** in the 4.0.11 candidate. Publication still requires the
complete native release checks for the final source commit.

The desktop connection picker now offers **Details & recovery** for a saved
workspace. It displays the saved address, tenant/identity IDs, last successful
connection and last verified organization role. The role observation and its
date are inside the OS-protected credential envelope, bound to the destination,
identity and visible metadata. The outer saved-connection format is unchanged.

Inspection performs no network request, changes no selection and creates no
session. The original connection and credential stay intact. Reconnection still
checks the real service, identity and credential. Historical administrator
status cannot bypass expiry, revocation or changed permissions. Locked secure
storage, older records without a role, and unreadable protected records have
distinct explanations. Replacing an address/key opens an empty key field.

Validation:

- **30 storage/connection tests** cover encrypted persistence, fresh session
  authentication, identity/destination binding, concurrency, locked stores,
  unchanged offline files, older records, tampered metadata, malformed role
  observations, secret exclusion, no network/activation during inspection and
  preservation of an unrelated active workspace.
- The full Electron suite passed **83 tests**. Production frontend type checking,
  branding verification and building passed.
- A separate native Windows check used the installed credential helper and real
  current-user DPAPI. The unmodified storage module extracted from the installed
  **4.0.10** app read new records successfully. New code read records written by
  that older module, reported their role as unknown and refreshed the role on
  reconnection. Inspection preserved paused selection and wrote no plaintext key.
  Test storage was separate from the user's actual workspace profile.
- Chromium exercised the production frontend with a controlled desktop bridge
  and the records produced by that DPAPI check. Cached admin/member, locked,
  legacy and damaged states rendered correctly. A deliberately failed offline
  reconnect did not open the workspace. Replacement cleared a previous draft
  key, and the bundled recovery guide opened. Desktop **1440×1080** and mobile
  **390×844** were visually inspected; no page errors, horizontal overflow or
  remote workspace requests occurred. This UI fixture is not a live remote-host
  recovery test.

The packaged native storage probe now also requires an offline identity round
trip and paused selection where secure storage is available. The six-platform
release matrix must exercise that probe before publication.

This is a recovery-information view, not an independent hosted control plane.
Host registration/operation, backup-location records, unverified connection
preparation, guided restoration/fenced takeover and complete agent parity remain
in the [continuity contract](../implementation/workspace-continuity.md).
