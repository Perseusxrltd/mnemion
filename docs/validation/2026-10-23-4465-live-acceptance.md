# Live 4.46.5 Windows and shared-host acceptance

The actual Windows x64 installation and shared Linux service completed
**4.46.3 → 4.46.5**. The paired observer passed on **23 October 2026 at
21:32:43 UTC**, against published source
[`8f022bd73ee364d681214a1b60421770c061e7e9`](https://github.com/Perseusxrltd/mnemion/commit/8f022bd73ee364d681214a1b60421770c061e7e9).
The immutable acceptance receipt was recorded at **21:32:42 UTC**.

The [native qualification](2026-10-23-4465-native-acceptance.md) passed all six
installed targets. The separate [public-upgrade run 40022243634](https://github.com/Perseusxrltd/mnemion/actions/runs/40022243634)
also passed all six targets. The [generated release status](releases/4.46.5-status.json)
records these gates and the [public release](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.5).

Windows applied the downloaded update through the supported agent-requested
restart after the app's draft and transfer guards passed, then reopened its
saved workspace. This proves a **guarded restart**, not unattended idle restart.
There was no forced installation or restart. The saved human login, bookmarks
and automatic-update, startup and background preferences were retained.

The shared service completed its compatible automatic update and reported
**4.46.5**, automatic updates enabled, healthy supervision, full readiness and
no pending recovery. This compatible update did not invoke a schema migration.

The unchanged external comparison made **15 requests**. The human owner and
both agent identities retained their existing spaces and roles. Both sampled
agent memories retained their exact versions and content hashes; MCP tool
discovery, OAuth discovery and the recorded deletion remained valid.

The isolated contributor lab passed **42/42 requests**, covering idempotent
saves, CPU indexing, lexical and semantic retrieval, revision, stale-write
rejection and deletion. All synthetic memories were cleaned up:
**zero pending cleanup, zero production memory writes and zero cloud model calls**.

## Preserved interruption and inspected continuation

The original post-update observer stopped at **21:23 UTC** because previously
visible spaces were absent from the agent comparisons. Both installations had
already reached 4.46.5. The failed comparison and original observer receipts
remain preserved.

A fresh instance of the same **15-request read-only comparison** passed at
**21:26 UTC**, with `baseline_matched_except_service_version: true`. Inspection
confirmed the original identities, spaces, roles and sampled evidence matched.
These observations establish the later match; they do not establish why the
spaces were temporarily absent.

The reviewed continuation retained the recorded action guards. **Neither
completed update nor the completed Windows restart was repeated.** It reopened
the existing workspace and completed the isolated lab. The original failed
attempt remains part of the evidence.

## Evidence and remaining limits

This report follows the generated public report and its original Windows,
shared-host, comparison and lab evidence. The retained receipt hashes are:

| Evidence | SHA-256 |
| --- | --- |
| Accepted pair | `761df48b1a99e128194578a38398f27489d89d6a9ca756710d3d967972fa0100` |
| Original failed observer archive receipt | `9285c7844c3beea1b28477093b94cc546cff50fbef8e12a2d1134c9f56a37f98` |
| Fresh matching comparison | `59b44d6028e0e3bc0c0a16877d4e7f77f20dd8e276cf2edb81aa3bf4f87eb269` |
| Inspected continuation | `cbcd649106d84d62b3748226788ddce4afd9b6eb989aa6bee1b4dc7bf90cd168` |

At the **23:48 UTC follow-up checkpoint**, custody validation had confirmed a
deliberate stop, manager restart and two real scheduled watchdog ticks. An
intervening local verifier interruption was preserved; it occurred before the
planned start. The inspected native start subsequently succeeded at
**23:46:27 UTC**. **Final 4.46.5 custody acceptance, fresh native backup delivery
and independent restore remained pending.** These partial steps did not yet
establish the complete custody journey.

The later [complete 4.46.5 custody journey](2026-10-23-4465-custody-acceptance.md)
was accepted at **23:52:34 UTC**, retaining the original stop and the planned
start issued once during the inspected continuation. Both final custodians,
readiness, restored connection and the unchanged 15-request comparison passed.
Fresh native backup delivery and independent restore remain unaccepted.

The [original failed/unconfirmed backup](2026-10-23-backup-transfer-diagnostics.md),
[first native candidate failure](2026-10-23-installed-workspace-open-diagnostics.md)
and [earlier actual host rollback](2026-10-23-independent-host-adoption.md#4462-actual-host-rollback--23-october-2026)
remain recorded. This acceptance covers one Windows installation and its shared
service; it adds no whole-machine boot, separate physical-device custody,
provider wake or controller-authority escrow proof.

All [66 requirement texts and states](../PRODUCT_REQUIREMENTS.md) are unchanged.
[V08 product telemetry](../implementation/anonymous-product-telemetry.md) remains
Planned and inactive. The [completion audit](../implementation/completion-audit.md)
and [issue plan](../implementation/github-issues.md) retain the broader pending
work; this paired check does not change publisher settings or close those issues.
