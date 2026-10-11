# Native hosting and access integration

Current source combines native engine/database packaging, local RAM-policy
repair, optional organization OAuth and service initialization acknowledgements.
The public release remains 4.0.10 until the integrated package gates pass.

The independent component reports retain their scopes:

- [Native database/Windows storage](2026-10-11-windows-private-state.md).
- [Installed Linux wizard, model inference and reopen](2026-10-11-native-installer-bundling.md).
- [Policy repair and browser/native Windows checks](2026-10-11-native-policy-recovery.md).
- [OAuth identity isolation and protocol fixtures](2026-10-11-oauth-foundation.md).
- [Initialized workers and compatible rollback](2026-10-11-service-readiness.md).

On the combined source, OAuth, memory-policy recovery, local readiness and real
HTTP/PostgreSQL clients passed **76 tests in 19.36 seconds**, with the Node SDK
required and no skips. Generated OpenAPI and agent contracts match their checked
in files. The current catalog has 87 operations. Frontend production build passed.

The full Electron suite passed **60 tests** after a further cancellation fix:
an update remembers whether it stopped a running local workspace. Cancellation
does not start a previously paused workspace, duplicate callbacks reopen at
most once, and a slow shutdown reopens after completion unless the user explicitly
stops it. This also preserves manual running state independently of the separate
start-with-app preference. Closing the app cancels deferred reopening.

The earlier native desktop matrix at `a703e41` passed all six targets, including
real installer/update/relaunch fixtures with awaited workspace-stop callbacks.
It predates the new bundled runtime and is not combined-package acceptance.
The combined source requires fresh Windows, Mac and both Linux architectures,
including installed real-model checks and native updates. Windows ARM deliberately
uses x64 service/model/PostgreSQL compatibility with a native desktop/client.

Local commands used memory/CPU scopes and disposable state. A secret scan of the
21 implementation commits preceding final integration found no leaks. Public
4.0.9 → 4.0.10 updates passed Windows and Mac; both Linux public restarts remain
under investigation. Developer diagnostics do not replace that public gate.
