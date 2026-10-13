# Agent and ingestion hotfix publication — 2026-10-13

[Mnemion 4.1.6](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.1.6)
was published at **08:34:34 UTC** from
`74fb444d0f8eebe41c59753ffd5f708c53442675`.

All 30 [release jobs](https://github.com/Perseusxrltd/mnemion/actions/runs/38365967799)
passed, including all six native installer, workspace and update targets.
The [product checks](https://github.com/Perseusxrltd/mnemion/actions/runs/38365884132)
passed. The [source validation](2026-10-13-agent-ingestion-stabilization.md)
records 80 focused checks and three catalog/version checks, using disposable
databases, real Git history and real HTTP/MCP/scanner processes.

The [independent artifact verifier](https://github.com/Perseusxrltd/mnemion/actions/runs/38369821896)
passed with the production validator from the exact source commit. Its
[receipt](2026-10-13-v4_1_6-hosted-verification.json) covers all 38 assets,
totaling 3,865,555,048 bytes, and unchanged uploaded IDs, sizes and digests.
The checksum inventory's SHA-256 is
`e6186f06407d5a92723d69c321ad670d12da149b8268b708fa03201542f96e5c`.

The [08:34:56 public check](2026-10-13-v4_1_6-publication.json) confirmed the
source tag, latest stable release, all assets and all 12 anonymous metadata,
checksum and update feeds. [Website synchronization](https://github.com/Perseusxrltd/mnemion/actions/runs/38370191054)
completed automatically. The [live HTML check](2026-10-13-v4_1_6-website.json)
confirmed the visible version, six installer links, current notes, guides,
checksums, roadmap on `main` and homepage product link. No website layout
change or new visual render is claimed.

All six [public 4.1.5 → 4.1.6 upgrade rehearsals](https://github.com/Perseusxrltd/mnemion/actions/runs/38370191234)
passed by **08:45:49 UTC**. The [sanitized receipts](2026-10-13-v4_1_6-public-upgrades.json)
confirm official feeds, unchanged public packages, real system idle, process
replacement and preserved profiles. Starting package hashes match the
independently verified 4.1.5 release for their platform and architecture.

## Separate observation on the user's Windows installation

The actual installed 4.1.3 application had a verified 4.1.4 installer cached.
Its ordinary update menu reported waiting for the app to enter the background.
The operator used **Hide to Tray**; no restart command or preference change was
made. After actual system inactivity exceeded ten minutes, the observer recorded
the installation transition and a new 4.1.4 main process at **08:39:22 UTC**.

The [sanitized observation](2026-10-13-actual-windows-update.json) records that
automatic updates, background operation and login startup remained enabled.
The protected saved identity and credential matched their earlier backup. An
initial connectivity check failed; a later read-only check authenticated the
same independent human administrator at **08:42:10 UTC**, with the shared server
reporting 4.1.5. The earlier response status was not retained, so its cause is
not attributed to the desktop update.

The 4.1.6 Windows installer subsequently appeared in the normal app cache and
matched the independently verified published size and SHA-256. That is download
evidence, not a claim that 4.1.6 was already installed on this computer. User
activity resumed during observation; ordinary restart safeguards remain active.
No production memory was written and no cloud model was called by these checks.

## Automatic website verification

The release metadata workflow now includes [live page verification](../../deploy/verify_website.py)
after updating its public fallback, both on publication and its regular schedule.
It checks every published primary installer, visible version, versioned guides,
release notes, checksums, roadmap and homepage product link, and retains a JSON
receipt. Requests are anonymous, restricted to the two canonical public pages
and bounded; short retries allow the website cache to catch up.

The verifier and existing metadata publisher passed **44 tests**. These include
stale or missing links, a version present only in scripts/styles/templates,
partial publications, drafts, unrelated destinations and a stale-cache retry.
The new verifier also passed against the actual 4.1.6 page. Its hosted workflow
run is recorded separately after the updated workflow is pushed.

The full product checklist remains open. This hotfix does not complete company
sign-in, hosted OAuth, independent host recovery, broader capture, retrieval
quality or the separately encrypted secrets vault.
