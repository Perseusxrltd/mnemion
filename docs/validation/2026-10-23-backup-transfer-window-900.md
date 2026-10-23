# Full-size encrypted transfer and reviewed network window

**23 October 2026.** The second isolated transfer diagnostic passed at
**19:09:41 UTC**, and a separate observation confirmed successful process exit
at **19:11:55 UTC**. An owner configuration update completed at **19:22:24 UTC**.
Fresh native backup delivery and independent restore remain **unaccepted**.

## Accepted diagnostic scope

The diagnostic used frozen 4.46.5 source
`704650c91af3e6a300758d71d7ee72f29874a04b` and the original retained encrypted
files in a separate Git branch. The **402,008,332-byte bundle** and
**569,030-byte ledger** retained their exact sizes and SHA-256 hashes. Fresh
remote readback verified both complete files.

The copied diagnostic settings allowed **900 seconds per network command**
and a **2,700-second total runtime cap**.

| Observed work | Elapsed seconds |
| --- | ---: |
| Push | 152.805 |
| Fetch for readback | 403.678 |
| Complete diagnostic, including preparation and verification | 970.992 |

The fetch exceeded the former 300-second network window in this observation.
These timings do not explain why the earlier push or original native backup
failed, and they are not a general throughput guarantee.

The terminal observation records `MainPID: 0`, `ActiveState: active`,
`SubState: exited`, `Result: success` and `ExecMainStatus: 0`. Its recorded
receipt hash matches the successful diagnostic receipt. The exited state is
separate evidence from a receipt written before the process finished.

The diagnostic retains **`native_backup_acceptance: false`**. It created no
new snapshot, changed no production runtime or backup receipt, and performed
no automatic retry. This is verified transfer of retained encrypted files,
not acceptance of a fresh native backup operation.

## Reviewed configuration update

The owner configuration receipt at **19:22:24 UTC** confirms that only the
network-command timeout changed, from **300 to 900 seconds**. Its plan binds
the prior configuration and the successful diagnostic and terminal receipts.
The installation remains **4.46.3**; no runtime installation or authority
changed, and no backup was requested. The receipt records
**`delivery_verified: false`**. The 2,700-second cap above belonged to the
isolated diagnostic and was not a production configuration change.

The [first 300-second push failure and original native failure](2026-10-23-backup-transfer-diagnostics.md)
remain preserved. The original 4.46.3 backup is still failed/unconfirmed after
its separate observe-only resolution. Neither the successful diagnostic nor
the configuration update rewrites that outcome or establishes its cause.
No product retry or resume action is added by these observations.

## Original evidence

The private `2026-10-23-backup-transfer-live-4465-r2` evidence directory retains
`observed-completion.private.json`, SHA-256
`67794d681a6a2ebcc7de562918eccae4e39b3d28fb3ecd5c01a3c2bc1b340722`,
and `terminal-state.private.json`, SHA-256
`cdc3230f1d6679d52bbc441eaa3a77acacf95aa13ad4fddcb726b3a3706564d8`.
The separate `2026-10-23-company-backup-window-900/configuration.receipt.json`
has SHA-256
`4312dcdbe441153f8b0f0956d91476a27154763d2558a422402ac40f424028a8`.
Private destinations, paths, credentials and operation identities are excluded.

These receipts do not provide new native-platform, public-update or actual
deployment acceptance, or establish current host readiness. All 66 requirement
texts and states remain unchanged, issues #44/#45 remain open, and V08 product
telemetry remains Planned and inactive.
