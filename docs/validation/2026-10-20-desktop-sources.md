# Desktop folder and conversation source acceptance

Recorded 20 October 2026. Source distribution: **4.31.0**. Native installer
publication and public update results are tracked in [release status](../RELEASE_STATUS.md).

The change adds [source setup and controls](../service/desktop-sources.md) to
Studio and its private local-agent interface. It reuses the existing connector
inventory, access, review and conversation-checkpoint contracts.

## Focused automated checks

- Seven private-helper checks passed: revision-bound atomic settings, protected
  files, damaged-file preservation, refused private-state overlap and replaced
  symlinks, HTTPS/address validation, bounded settings and safe exclusions. An
  actual child process exceeded its 128 MiB allowance with bounded allocation
  and was stopped by the resident-memory monitor without a model/network call.
- Two real HTTP/PostgreSQL capture tests passed for ordinary files and growing
  JSONL conversations. They verify dedicated identity and workspace matching,
  mapped-reader access, no implicit administrator content access, secret-file
  exclusion, unchanged rescans, retained good data after unreadable input,
  deletion, incomplete JSONL tails, subsequent complete records and disabled
  connection refusal.
- All 49 focused Electron controller checks passed. Six new source cases cover
  protected persistence/reopen, unavailable key storage, stale settings,
  identity mismatch, serialized/fair queued scans, pause and update guards,
  failed pause persistence, draining removal, ambiguous committed replies and
  immutable source identities. Existing private desktop, workspace, backup,
  credential and update-policy checks also passed.
- All 17 existing update-controller cases passed, covering idle/locked restarts,
  draft and in-flight-work guards, cancellation, preferences and bounded retries.
- Python formatting/lint, Electron TypeScript and the desktop frontend build
  passed. No dependency or schema migration is added.

## Actual source-app walkthrough

A disposable Linux Electron instance used the real preload, main-process
bridge, private local operator, frontend and native source helper against a
separate HTTP/PostgreSQL fixture. Its local database runtime was deliberately
absent, and local status remained unavailable/new throughout contribution.
The fixture used a fresh isolated OS Secret Service session; it did not use
the user's keychain or live workspace.

The UI selected a synthetic Obsidian folder, confirmed its mapped audience,
created a dedicated application key and captured the selected document. The
key was protected with the actual OS credential backend and was absent from
public source status and plaintext settings. Unsaved setup blocked an update;
the saved form released that guard. Source counts appeared in Connections.
A simultaneous device-control change preserved the person's draft, blocked its
stale save and offered an explicit reload of the current settings.

The same session ran the committed installed-app source probe: renderer setup,
private-agent resume/status/removal, actual capture, encrypted-key inspection
and the configured source's visible Connections panel all passed. It then
disconnected the workspace and paused the remaining source using **Sources on
this computer** on the signed-out welcome screen. No workspace login or local
database was required for that device control.

Desktop and 500-pixel-wide captures were visually inspected. No horizontal
overflow or renderer console errors were reported. The complete walkthrough
passed in 46.82 seconds. All source documents and database identities were
synthetic; temporary registrations and device settings were cleaned up.

## Delivery and remaining scope

The installed-app probe is included in the existing backup/resume acceptance
on Windows, macOS and Linux, each on x64 and ARM64. These native gates must pass
before publication; the Linux source-app walkthrough alone is not six-platform
installer evidence.

The first 4.31 build exposed an omitted shared TypeScript declaration in the
Docker context. The build now includes the shared declaration files as a group,
so adding a new public type does not require another manual Docker allowlist
edit. The frozen first attempt was cancelled and superseded by a corrected
immutable attempt; no failed candidate was published.

The next attempt passed both container builds and exposed a test-suite boundary:
the source helper's RSS test belongs to the full engine environment, while the
small desktop bridge intentionally does not include process monitoring. The
helper cases now run in the service suite, with actual packaged source execution
still covered by the installed-app probe. The small bridge's dependencies remain
unchanged. The second frozen attempt was superseded before publication.
The corrected lightweight environment passed 200 checks, with 11 intentional
platform/dependency skips. Release start now verifies that locked environment
before reserving native runners, and reuses a successful receipt only while its
runtime and relevant source/test inputs match.

Other providers retain their existing adapters. This does not complete graphical
Git/Drive/Slack/rclone enrollment, provider OAuth or organization ACL translation,
virtual cloud-file hydration, full chat-history access, source-key transfer
between devices, or fleet acceptance. Sampled RSS enforcement can miss a brief
allocation spike. Strict complete product coverage remains **17/64**.

The third candidate passed source ingestion but exposed two assumptions in the
combined installed-app fixture. Windows canonicalizes its short temporary path,
so its UI assertion now compares the saved canonical path. The source exercise
also creates an additional managed space; later address-recovery checks now
follow the original space ID explicitly. Fresh creation and its first restart
still require exactly one private space. No production behavior or access check
is weakened. Corrected native acceptance remains a publication prerequisite.
