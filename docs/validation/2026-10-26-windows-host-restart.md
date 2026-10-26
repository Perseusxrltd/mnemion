# Windows installed host restart observation

**Native validation checkpoint, 26 October 2026.** The official
[4.46.10 run 40245659798](https://github.com/Perseusxrltd/mnemion/actions/runs/40245659798)
failed [Windows x64 job 121327653027](https://github.com/Perseusxrltd/mnemion/actions/runs/40245659798/job/121327653027)
at **Installed app creates, searches and reopens a real local workspace**, after
packaging. The checked-out source was
`52c57eb493e2ecd31d0473664f8b4a38f2977205`. Publication is withheld pending
installed Windows acceptance; other target checks were still running at this
checkpoint. See [current release status](../RELEASE_STATUS.md).

## Observed failure

All timestamps below are **25 October, UTC**. The installed probe entered
`backup-resume` at **23:50:25** and reported failure at **23:54:13**:

| Evidence field | Recorded value |
| --- | --- |
| `passed` | `false` |
| Platform / architecture | `win32` / `x64` |
| Phase / stage | `backup-resume` / `installed-local-hosting` |
| Last stage | `startup-error` |
| Fixed error message in the job log | `Native host did not resume before the model-setup deadline.` |
| Engine diagnostic category | `database` |
| SQLSTATE | Not recorded |
| Engine diagnostic exit | `3221225477` (`0xC0000005`), signal `null` |
| App-child observation | `childExitCode: null`, `childSignal: null` |

The [model-setup probe](https://github.com/Perseusxrltd/mnemion/blob/52c57eb493e2ecd31d0473664f8b4a38f2977205/studio/electron/native-model-probe.ts)
waits for the native host to return to `running` around model-configuration
changes. The retained result identifies a failed restart observation in that
journey; it does not identify which underlying component caused it. The null
app-child fields provide no recorded exit code or signal at capture time.
They must not be interpreted as proof that the application exited.

The bounded JSON records these source locations:

| Module | Function | Recorded line |
| --- | --- | --- |
| [mnemion.local_workspace](https://github.com/Perseusxrltd/mnemion/blob/52c57eb493e2ecd31d0473664f8b4a38f2977205/mnemion/local_workspace.py#L877) | `dispatch` | 877 |
| [mnemion.local_workspace](https://github.com/Perseusxrltd/mnemion/blob/52c57eb493e2ecd31d0473664f8b4a38f2977205/mnemion/local_workspace.py#L348) | `run` | 348 |
| [mnemion.local_database](https://github.com/Perseusxrltd/mnemion/blob/52c57eb493e2ecd31d0473664f8b4a38f2977205/mnemion/local_database.py#L361) | `provision` | 361 |

These are diagnostic locations, not a demonstrated root cause. The report
establishes neither data loss nor a correction. Further investigation and
installed Windows acceptance remain necessary.

## Earlier checks and retained evidence

The desktop npm suite had already completed with **399 passed, zero failures
and two skipped**, followed by **20 passing updater tests**. Its telemetry
helper-lifecycle and five-second native-deadline tests both passed. The present
failure is later installed hosting; the earlier
[deadline validation](2026-10-25-native-telemetry-deadline.md) keeps its own scope.

Only the bounded `installed-hosting-evidence.json` member was read from the
artifact. Private runner paths and raw logs are not reproduced here.

| Original evidence | SHA-256 |
| --- | --- |
| Official Windows x64 job log | `10e3234ea9bee71ca83cc22a21b089dfe40c84e0cf965eb7f9975fca5c1f8283` |
| Installed-hosting artifact ZIP | `73cb579a19c69b749c432587b8c64d5184ff5d97c52590a117ebd653a02c5035` |
| Bounded JSON member | `a82a5e6af507943dd404848807e065fdd0878ea21334829b02dcdc23c1f697a9` |

All 66 requirement texts/states remain unchanged. V08 remains Building and
product collection remains disabled, with no production destination or route.
This failed native checkpoint is not release, installed-update or full
telemetry acceptance.

## Source diagnostic follow-up — 26 October

The [native model diagnostic follow-up](2026-10-26-native-model-diagnostics.md)
preserves the first classified setup error, avoids further fixture changes after
failure, and retains fixed database reasons without raw driver text. Its source
checks passed; Windows x64 native diagnostics remain planned. This does not
assign a cause or a fix to the original failure, whose evidence above is unchanged.
