# Native model-setup failure diagnostics

**Source checkpoint, 26 October 2026.** The installed model probe now preserves
its first classified failure at a fixed setup phase. This improves evidence
for the unresolved [4.46.10 Windows restart failure](2026-10-26-windows-host-restart.md);
it does not identify that failure's cause or establish a runtime fix. The frozen
4.46.10 candidate remains failed and unpublished.

## Failure handling

The [model probe](../../studio/electron/native-model-probe.ts) records whether
failure occurred during initialization, saving either fixture profile,
inspection, app checks, view restoration or removal of either profile. The
[structured diagnostic](../../studio/electron/native-model-diagnostics.ts)
accepts only fixed phase, reason, state, stage and cleanup values, plus a
validated engine diagnostic. The [outer installed probe](../../studio/electron/scripts/smoke-installed-hosting.mjs)
can retain this as `modelSetup` in its bounded artifact.

A structured startup error is handled immediately even when local state is
still `stopping`, instead of waiting for process closure and reporting an
unrelated restart timeout. Once the model probe fails, it makes no further
fixture configuration mutations; the enclosing installed probe owns application
shutdown. The disposable model endpoint is still closed. The failure path does
not attempt profile removal that could replace the first failure with a later
cleanup error.

Successful enrollment still requires removal of both fixture profiles. A fresh
status inspection afterward rejects either retained profile with
`cleanup_profiles_remain`, even when both removals were acknowledged. A view
restoration or profile-removal failure fails the check with its own fixed phase;
cleanup is not skipped to obtain a pass. The original restart deadline remains
in place when no structured startup error is available.

The [Python database classifier](../../mnemion/local_diagnostics.py) adds only
the fixed `database_reason` enum: `authentication`, `timeout`,
`connection_refused`, `connection_closed`, `tls` or `other`. Driver text is used
only for bounded classification and is never copied into the result. The
[desktop validator](../../studio/electron/local-diagnostics.ts) rejects unknown
fields or reasons. No raw driver message, connection string, credential, private
path or arbitrary error fragment is retained. SQLSTATE remains optional and
validated; this change cannot recover missing fields from the original receipt.
These reason labels are diagnostic categories, not demonstrated root causes.

## Source verification and remaining acceptance

| Focused selection | Result | Duration |
| --- | --- | --- |
| Python diagnostics | 15 passed | 0.05 s |
| Final desktop diagnostics/probe selection | 67 passed, zero failures or skips; exit 0 | 318.656473 ms |

The Electron source build passed before the desktop selection. The
[model-probe regressions](../../studio/electron/scripts/test-native-model-probe.mjs)
exercise fixed-field privacy rejection, preservation of the first startup
error with no second mutation, successful removal of both profiles, cleanup
failure classification, and rejection of acknowledged removals that leave the
profiles present. The preceding 66-pass log is retained separately. These checks use scripted status/window fixtures and
verify closure of the disposable listener; they are not a native installed-app
journey.

| Retained original log | SHA-256 |
| --- | --- |
| Python focused tests | `854be6b5f038a885da628bd4b089fcd4e10a1c1288488c7b13fd5363f0ce3251` |
| Final desktop focused tests | `88424187d560b8417309210fb49cae440bf158534e4cfd579d00bebc059da5f6` |
| Earlier desktop selection, before the final cleanup check | `4d047d12a28bb0eb43d12ecbcd618b46b2934b6071be21054988aa75251736f7` |

The earlier failed scripts, Windows job log and bounded artifact remain
preserved in the linked restart report. No new model phase or database reason
is retroactively assigned to that failure. A Windows x64 native diagnostic run
is planned after integration; it has not qualified these changes, and no new
release is claimed. All 66 requirement texts/states are unchanged; V08 remains
Building and production collection/destination/route remain false/null/null.


## Focused Windows native acceptance

[Run 40251151874](https://github.com/Perseusxrltd/mnemion/actions/runs/40251151874)
completed successfully on **26 October at 01:22 UTC**, with all nine jobs
passing. Its source was `97fce09abc588ed1d4a9a1f09a3144b7f581bfbc`, differing
from reviewed source `14bae7463ecc049cb19a87bf41652c267d79b782` only in
verified generated status files.

The retained installed-hosting artifact reports a real Windows x64 NSIS
installation, native setup, semantic save/recall, restart persistence, backup,
recovery, vault and capture journeys passing. The separate workflow step for
Windows installation, authenticated upgrade and relaunch also passed. The
artifact SHA-256 is `7864da4fc53d161549f9887f422a685d0a592b4c60cc4ffc3b1ff59e4a9a1884`.

This supersedes the earlier planned-validation status for this source. It
qualifies the new Windows run; it does not establish the cause of the original
intermittent restart failure or change the failed frozen 4.46.10 release.
Nothing was published by this diagnostic, and it does not qualify the later
renderer refusal optimization, production telemetry or all native platforms.
