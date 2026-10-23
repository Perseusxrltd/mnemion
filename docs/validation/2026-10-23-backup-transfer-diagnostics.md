# Backup transfer diagnostics and local processing

**23 October 2026; UNRELEASED source work.** This change preserves transfer
evidence and reduces Git processing of encrypted parts. It adds **no retry or
resume action** and does not establish recovery of the original uncertain
backup. It is excluded from frozen 4.46.4 source
`4e64aad45c288d2bc71146b976857225c628fb7a`, whose
[native run 39997298864](https://github.com/Perseusxrltd/mnemion/actions/runs/39997298864)
was running at this checkpoint. [Release status](../RELEASE_STATUS.md) tracks
public gates separately.

## Retained evidence and bounded diagnostics

Before pushing, the [transfer implementation](../../mnemion/host_control/backup_git.py)
writes a host-private `delivery-intent.json` binding the original operation to
the exact commit, destination ref, manifest digest, manifest and file hashes.
A bounded `transfer-progress.json` retains the latest stage, state, timestamp
and optional diagnostic. These records support inspection; they do not prove
remote delivery.

The [worker](../../mnemion/host_control/worker.py) preserves a transfer failure
under `result.backup_transfer`, with an allowlisted Git `stage`, fixed `reason`
and bounded integer or null `exit_code`. Reasons are `deadline`, `storage_guard`,
`git_exit`, `process_io` and `transport_setup`. Raw Git stderr, credentials and
arbitrary exception text are excluded from this diagnostic. The
[Host controls UI](../../studio/frontend/src/workspace/HostControl.tsx) renders
fixed guidance to inspect the original request. An uncertain operation remains
`inspection_required`; this source change neither replays it nor resolves it.

Git uses `core.compression=0`, `pack.compression=0`, `pack.window=0` and
`pack.threads=1` for these transfers, avoiding compression and delta-search
work on encrypted parts with one packing thread. These are per-command
settings, not changes to the user's global Git configuration.

## Synthetic local measurement

The fixture contains **64 MiB of random high-entropy data plus a 1 KiB ledger**.
Four trials ran in balanced order: legacy, changed, changed, legacy. Timed work
covers delivery and fresh readback against local bare Git repositories, with
**zero network calls**. Every trial verified exact file sizes and SHA-256
digests; all recorded Git commands succeeded.

| Git settings | Trial durations (seconds) | Mean (seconds) |
| --- | ---: | ---: |
| Legacy | 25.183, 29.111 | 27.147 |
| Compression/delta search disabled, one packing thread | 12.983, 13.151 | 13.067 |

The ratio of means is **about 2.1× for this local sample**, with only two
observations per variant. No WAN timing, live backup acceleration or repair of
the original failure was measured.

The private `encrypted-git-measurement/receipt.json`, recorded at
**17:57:27 UTC**, has SHA-256
`761858af34631e539eb2df1c1318c1a88701203cd17e3554a3c9263535e8510f`.
The dated `2026-10-23-inventory-privacy-4464` evidence directory retains
`measure-encrypted-git.py` with the method. Focused Git/jobs checks
passed **19 tests in 36.42 seconds**, with **two local SSH-fixture skips**;
the frontend TypeScript/Vite production build passed. These are source checks,
not installed acceptance of this change.

## Original live outcome remains uncertain

The original backup entered `inspection_required` at **16:55:33 UTC**. Its
encrypted files remain retained. The **17:45:34 UTC** checkpoint found no
matching independent destination branch and recorded no new operation.
Read-only inspection also confirmed that the configured SSH read works
and the deploy key is writable; no OOM or disk-pressure evidence was observed.
The exact failure cause remains unknown because no original transfer
diagnostic survived. The new records cannot reconstruct that missing evidence.

At **18:10:36 UTC**, the existing 4.46.3 native custodian's supported
`operations.resolve` action accepted the healthy current service with
`settle: "observe"`. Final readback at **18:14:03 UTC** confirmed unchanged
authority, readiness and restored automatic-start eligibility. The original
backup is now `failed` with `operation_uncertain` and `original_outcome:
"unconfirmed"`; its failure and encrypted files remain retained. No backup,
service stop or service start was replayed. The first unavailable status read
and the first observer's elapsed window remain in the evidence.

The private `2026-10-23-backup-transfer-recovery/recovery.receipt.json` has
SHA-256 `061e8aae109ad316401dbd3dc5a9d6c00a4ca53f2d2c1b1d51348df13b0184ab`.
This establishes recovery of host administration, not backup delivery or restore.

That preserved checkpoint is
`2026-10-23-174534-release-and-backup-inspection.json`, SHA-256
`58330860cae4cda239cf175fdedf0bf709de8a3eb10a0f5a681ef8cba59042e3`.
Fresh backup delivery and independent restore remain unaccepted. The earlier
[paired update](2026-10-23-4463-live-acceptance.md) and
[two-custodian lifecycle](2026-10-23-4463-custody-acceptance.md) retain their
separate accepted evidence. Issues #44/#45 remain open, all
[66 requirement texts and states](../PRODUCT_REQUIREMENTS.md) are unchanged,
and [V08 telemetry](../implementation/anonymous-product-telemetry.md) remains
Planned and inactive.

## Full-size isolated transfer diagnostics

**23 October 2026 follow-up.** The first isolated diagnostic used frozen
4.46.5 source
`704650c91af3e6a300758d71d7ee72f29874a04b`, the original retained encrypted
bundle and ledger, and a separate destination branch. Its **18:44:18 UTC**
receipt recorded failure at **`stage: push`, `reason: deadline`**, with
`exit_code: null`. The configured network-command limit was **300 seconds**;
the measured push lasted **300.807 seconds**. The service-manager observation
at **18:45:08 UTC** recorded `Result: exit-code` and `ExecMainStatus: 1`.
The diagnostic ended before its 1,200-second total runtime cap, and sampled
OOM counters were zero.

A separate matching-ref read at **18:49:30 UTC** found the diagnostic branch
absent. The original production backup receipt remained unchanged, and no new
snapshot was created. This identifies the failing stage and limit in the
isolated diagnostic. It **does not establish the cause of the original native
4.46.3 backup failure** or qualify fresh backup delivery or independent restore.

The second isolated diagnostic uses the **same frozen source archive, transfer
module and encrypted input hashes**. Its copied destination settings allow
**900 seconds per network command**, with a **2,700-second total runtime cap**.
Production settings and the active runtime remain unchanged. This is a
separately launched diagnostic; no product retry or resume action was added.

At the **18:58:01 UTC** documentation checkpoint, the latest saved observation
at **18:57:04 UTC** showed the second diagnostic **active/running**, preparing
encrypted parts at `hash-object`, with **no terminal receipt**. Its outcome
remains **pending** at this checkpoint; no successful delivery is established.
The first failure remains preserved independently.

The first private `observed-completion.private.json`, under the dated
`2026-10-23-backup-transfer-live-4465` evidence directory, has SHA-256
`e13f1c8ccfc1f99b3f5a30088921525a20d31eb5a4d22104abd34ce424c0cc82`.
The second directory, `2026-10-23-backup-transfer-live-4465-r2`, retains
`plan.private.json`, SHA-256
`69f365ba6092d2d0d7e52a8541cdbd0a43a0789dffb9587aca0dd5620b9124f4`,
and `observations/003.private.json`, SHA-256
`37bc9ebdb390492641d99d62434bfc919e8246a37219c9f394d7a413d2da0d5c`.
The plans and saved stage observations bind the source, input identities,
separate branch inspection and diagnostic-only limits without publishing raw
logs, private destinations or operation identities.

## Later transfer and configuration observations

The [19:09 UTC full-size readback and 19:22 UTC owner configuration update](2026-10-23-backup-transfer-window-900.md)
record the later successful isolated diagnostic and the separately applied
900-second network-command window. They preserve the failures and pending
state at the earlier checkpoints above. Fresh native backup creation and
independent restore still require their own acceptance.
