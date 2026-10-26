# Installed model action diagnostics — 26 October 2026

The 4.46.17 macOS ARM installed-workspace check failed while saving a librarian
model during backup recovery. Its retained report identifies
`backup-resume / save_librarian / action_failed`, with the last observed host
`running / ready`. **The underlying cause is unknown.** Those host fields are
the last observation before the action, not proof that the failed action left
the host healthy.

The [original job](https://github.com/Perseusxrltd/mnemion/actions/runs/40303268742/job/121508256690)
and its bounded diagnostic artifact are retained. The artifact ZIP SHA-256 is
`e95ee64b5fafd35fa2d438c5b670799431ef7dbd4d88bf60ec65e9964e447f99`.
Frozen 4.46.18 was held before native dispatch after this failure was observed.
The existing source CI and other already-running native jobs continue.

## Diagnostic correction

The [installed model probe](../../studio/electron/native-model-probe.ts) now
records the operation within the setup phase: status, app-idle check, settings
application, restart observation, private-state inspection or app inspection.
It classifies exact known failures such as a settings timeout, changed revision,
busy app, stopped host, invalid runtime result or failed operator exchange.
Unknown exceptions remain `unclassified`.

The [closed diagnostic parser](../../studio/electron/native-model-diagnostics.ts)
accepts only fixed operation and failure values. Arbitrary messages, stack traces,
paths, URLs, credentials and provider responses are not included. Older saved
reports without the new optional fields remain readable. An initial status
failure now retains that operation instead of being mislabeled as listener
startup. The last observed host state remains explicitly historical.

This changes diagnostic evidence only. It does not retry uncertain writes,
change deadlines or permission checks, mutate a failed host for cleanup, or
claim to repair the original Mac failure.

## Validation

The Electron build and **eight focused Node checks passed**, with zero failures,
cancellations or skips. The regression simulates a librarian save that takes
effect but whose acknowledgement fails: both profiles remain in the disposable
fixture, no save is replayed, no cleanup write occurs, the first failure is
classified and the loopback listener closes. Other checks cover initial status
failure, strict redaction, older artifacts and normal successful cleanup.

This is source-component evidence. A changed-source Mac installed-app check and
the usual release gates remain necessary. V08 stays Building with production
collection disabled; the diagnostic work does not qualify telemetry or a release.
