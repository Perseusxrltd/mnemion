# Telemetry setup recovery — 27 October 2026

This source-only follow-up is prepared on
`629a7afc7938f87656ad05c2a38d5427ae5e35c8`. Three original compiled-UI failures
are retained. All 11 corrected compiled-UI recovery checks, 29 policy-control
tests and the SDK/frontend builds passed. Installed and release acceptance
remain separate.

## Retained reproduction

The actual compiled React UI in Chromium used controlled native privacy replies.
All three regression cases failed:

| Case | Original behavior |
| --- | --- |
| Initial native privacy read fails | Setup hides the failure without offering recovery. |
| A refresh fails after a readable disclosure | Stale enable controls remain usable. |
| Status reports unreadable storage | Setup silently dismisses itself. |

The receipt records **zero page errors, external requests and network writes**;
production collection was unchanged. The private `browser-before-result.json`
has SHA-256
`945f6869770a4a79e42e4ec2ea316bcd93a4780d64fe03734fda0703189062c9`.
These failures remain evidence, not passing qualification.

## Current source recovery

[Setup](../../studio/frontend/src/workspace/TelemetrySetup.tsx) now presents
**Privacy settings unavailable** after a failed initial/current read or an
unreadable status. A failed current read clears the old UI snapshot; unavailable
settings cannot leave stale enable controls usable. Recovery offers
**Retry privacy settings**, **Continue to Mnemion** and **Open Privacy controls**.
Retry reads status; continuing or opening the privacy page does not write a
choice or acknowledge a disclosure.

If saving returns an error, setup reads actual status before offering another
choice. It never automatically retries the write. When the choice remains
unconfirmed, it displays **Your privacy choice could not be confirmed** and asks
the user to review the latest settings. A fresh readable status still supplies
the original revision/generation fence for a subsequent explicit choice.

Recovery does not force-disable or change an existing saved policy. A failed UI
status request alone does not prove that an already-enabled policy is off, or
that the underlying policy store is unreadable. The
[user guide](../guides/product-telemetry-controls.md#in-the-app) gives recovery
steps without treating a failed read or save reply as a successful opt-out.

## Corrected qualification

The actual compiled React app passed **11 distinct checks** in Chromium
**144.0.7559.96**. Eight checks cover the three original defects, fresh-state
retry without losing an unsaved opt-out, dismissal during a delayed retry,
navigation to full privacy controls, repeated read failure and mobile/Escape
behavior. Three additional checks cover a rejected save, a successful save whose
reply was lost, and a save followed by an unreadable confirmation. Each verifies
that status recovery does not replay the write or use a stale revision.

Both corrected selections recorded zero page errors, external requests and
network writes. The test's private native reply model simulates persistence and
failure; these are UI observations, not proof of actual native storage writes.
Only the copied disclosure's availability flag and `.invalid` destination were
changed; its transport route remained unavailable and production configuration
was unchanged. The named browser session and owned loopback server were closed; the
server recorded 520 GETs and no POSTs across the original and corrected cases.
Original and corrected script, source and asset inventories remain retained.

The existing **29 policy-control tests** passed with no skips. The SDK build and
source TypeScript/frontend build passed. Documentation edited afterward is
rebuilt by normal source/release automation. Controlled replies and a compiled
browser app do not qualify installed storage, other platform runtimes, provider
behavior, resource limits or the complete privacy path. Existing saved opt-outs,
company/GPC restrictions and the unavailable-release setup gate remain
authoritative. No new native release is requested for this source-only follow-up;
the separately frozen 4.46.37 release keeps its original source and gates.

All 66 requirement states remain unchanged. V08 is **Building**; production
collection/destination/route remain **false/null/null**, with release CAs empty.
The **2 MiB added RSS / 0.5% of one core** ceilings and all failed resource
evidence remain unchanged. No new resource measurement is selected.
