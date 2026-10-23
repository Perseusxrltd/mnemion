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
