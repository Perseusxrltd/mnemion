# 4.46.0 frozen native installation acceptance

Qualified **23 October 2026 at 04:44:53.746993 UTC** for frozen source
[`a53ca6ff123c70686c8d89e2c9545143a2fadc37`](https://github.com/Perseusxrltd/mnemion/commit/a53ca6ff123c70686c8d89e2c9545143a2fadc37),
branch `release/4.46.0-r2`. [Release run 39895069093](https://github.com/Perseusxrltd/mnemion/actions/runs/39895069093)
concluded **success**. All six installed hosting/capture receipts contain
**59/59 required true fields**. These are overlapping acceptance observations,
not a count of independent tests.

| Installed target | Successful native job | Evidence artifact | Required fields | Separate packaged update/relaunch |
| --- | --- | --- | --- | --- |
| Linux x64 | [120225126077](https://github.com/Perseusxrltd/mnemion/actions/runs/39895069093/job/120225126077) | `12477259296` | 59/59 | Not separately listed |
| Linux ARM64 | [120225126118](https://github.com/Perseusxrltd/mnemion/actions/runs/39895069093/job/120225126118) | `12477770557` | 59/59 | Not separately listed |
| Windows x64 | [120225126107](https://github.com/Perseusxrltd/mnemion/actions/runs/39895069093/job/120225126107) | `12478465703` | 59/59 | Passed |
| Windows ARM64 | [120225126065](https://github.com/Perseusxrltd/mnemion/actions/runs/39895069093/job/120225126065) | `12479156750` | 59/59 | Passed |
| macOS x64 | [120225126125](https://github.com/Perseusxrltd/mnemion/actions/runs/39895069093/job/120225126125) | `12478067573` | 59/59 | Passed |
| macOS ARM64 | [120225126073](https://github.com/Perseusxrltd/mnemion/actions/runs/39895069093/job/120225126073) | `12477725666` | 59/59 | Passed |

Windows ARM64 uses an ARM64 desktop with the tested **x64 engine and database
emulation**. The other five targets use matching native desktop, engine and
database architectures. Both Windows jobs passed installation, authenticated
upgrade and relaunch; both macOS jobs passed packaged update, restart guards and
relaunch. These are runner checks, not public-feed or actual customer updates.

The [qualification receipt](2026-10-23-4460-native-acceptance.json) is an unchanged
copy of the collected receipt, SHA-256
`4024f9d17a92b6f7375ef39060b451cc1140e7cacab6ae40c203cdcf8259dfad`.
It binds the run/source, six source-contract hashes, artifact IDs, downloaded
evidence-archive hashes and decoded evidence hashes. These archives contain
installed-hosting evidence; they are not installer distribution checksums.
The frozen probe also verifies engine source and dependency hashes; those
manifests are not embedded in this small receipt.

Each hosting journey used a locally built installer, a new private profile and
a real model download; model weights were not bundled. The observations cover
setup and protected account/key recovery, local semantic memory, encrypted
backup/vault recovery, retained capture, offline intake, authority/deletion
fences, restart continuity and damaged-state preservation.

## Packaged independent host controls

All six complete native jobs and their platform's **packaged window, sandboxed
bridge and local-client** step concluded success. Both Linux jobs also passed
**Linux encrypted workspace reconnect after process restart**, which reruns the
packaged journey with a required real OS keyring. These conclusions are separate
from the 59 hosting/capture observations above.

The [frozen packaged probe](../../studio/electron/scripts/smoke-packaged-app.mjs)
requires the real host UI, protected per-device key, pinned SSH and native agent
pipe with the peer's memory API absent. A full app restart reopens the same key,
inspects the original queued UUID without replay, enforces the custodian
boundary and requires acknowledgement before archiving the public request and
removing the local key. The queued and archived requests must be visible in the
UI. The isolated peer has no worker: its approved `service.stop` remains queued,
so this does not demonstrate a production service stop or watchdog integration.

## Preserved failure and corrected rebuild

The original [run 39884444351](https://github.com/Perseusxrltd/mnemion/actions/runs/39884444351),
source `82925e7aa82826029fb576e7d39dc21166d09f6f`, passed four Linux/macOS jobs
but failed both Windows packaged host-control views. The
[Windows failure record](2026-10-23-windows-host-client.md) retains the missing
`win32timezone` failure from unused GSS/SSPI initialization, original receipts,
initial cleanup failure and the separate bytecode-patched diagnostic copy.
That diagnostic copy was not a rebuilt release artifact.

The correction explicitly disables unused GSS context initialization and adds
an early frozen-engine gate. The actual rebuilt Windows engine in
[job 120224223590](https://github.com/Perseusxrltd/mnemion/actions/runs/39895069093/job/120224223590)
passed pinned inspection and changed-host-identity refusal at **03:32:14 UTC**,
with no service effects. The six completed installed jobs above supply the
later corrected native qualification; the earlier diagnostic report's pending
native gate is historical.

## Publication and deployment boundary

At the **04:46:39 UTC** checkpoint, independent publication verifier
[39901894314](https://github.com/Perseusxrltd/mnemion/actions/runs/39901894314)
was still scanning the downloaded distributions. This report records no
publication pass. Current public availability and gates belong to
[generated release status](../RELEASE_STATUS.md).

The receipt retains `public_release_acceptance: false` and `l1_complete: false`.
Actual Windows/Hostinger paired acceptance remained at
[4.45.1](2026-10-23-4451-live-acceptance.md) at this checkpoint. This qualification
does not establish a 4.46.0 live update, fresh production backup, independent
host adoption, whole-machine boot, provider wake or full authority-state
backup/recovery. Broader provider histories, fleet/load measurements and
[L1–L7](../research/2026-10-20-layered-librarian.md) remain open.
All [65 requirement texts and states](../PRODUCT_REQUIREMENTS.md) are unchanged;
issues **#44/#45** remain open. The separate PC publisher pause and the
administrator conversation's stopped Grokbot/Adonis tests remain in force.
