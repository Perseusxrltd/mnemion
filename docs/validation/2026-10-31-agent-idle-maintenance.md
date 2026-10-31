# Desktop agent maintenance on the existing background schedule

**31 October 2026 — source validation for the 4.46.61 batch.** Actual Grok
implementation `a3ca2405aa1b7a2e53ee1357a88d1e37848a37c3` was adopted as
`1f9ff11c15d2444c760a02eb664f067a5aa28f7a`, on parent
`3813930b341480a1237e1b63d00623e6ff7401ee`. At this source checkpoint, native
and public 4.46.61 acceptance remain pending.

## Source behavior

[DesktopAgents](../../studio/electron/desktop-agents.ts) still launches a
private helper at startup and on the existing five-minute schedule when idle.
Its background request is now `maintain`. The
[Python handler](../../mnemion/desktop_agents.py) reads the private setup records
under the existing lock, preserving identity validation, runtime repair and
publication, abandoned-stage cleanup and live-lease retention. The small reply
contains runtime attention only. It skips the client profile discovery,
external configuration parsing/hashing and runtime-version fields that the
background caller previously discarded.

Full status still performs maintenance and freshly builds the complete result
for people and agents; no status cache or partial-result substitution was added.
The private dispatcher rejects extra fields on `maintain`. The controller counts
maintenance as busy, makes status and mutations wait for it, defers update
suspension while work is active, and aborts/drains owned calls on close. The
public agent API is unchanged.

## Original verification

One finite check plan completed without retries or repeated successful checks:

| Check | Result | Scope |
| --- | --- | --- |
| Python desktop setup and agent runtime suites | 13 passed in 25.81 seconds | Temporary runtime files and existing setup/runtime fixtures |
| Strict Electron TypeScript compilation | Passed; 14.009 seconds driver time | Existing project configuration |
| Desktop agent controller script | 4/4 passed; 130.676807 ms Node duration | Controlled helper overlap, update suspension and close |
| Reviewed source inputs after checks | All four hashes matched | Two implementation files and their two test files |

The Python source review found no concrete regression in the shared maintenance
path. Its unchanged setup lock and saved-record validation were inspected; the
new case does not establish lock-contention, corrupt-record or live-launcher
race coverage. Existing full-status tests retain external-configuration
freshness checks. These boundaries do not imply an installed-app result.

The batch also includes the
[capture display and supervised-host setup corrections](2026-10-31-capture-ui-and-service-bootstrap.md).
The earlier strict frontend typecheck passed once in 24.462 seconds, after the
preserved incomplete Windows dependency-cache failure. The bootstrap guide check
passed 62 documentation links. Those checks were not repeated for this note.

## Acceptance limits

The maintenance helper and five-minute wake remain. Skipping unused status work
is not a measured CPU/RAM saving. The changes add no dependency, alter no user
RAM limit and activate no telemetry. Whole-product acceptance remains open
under the [runtime efficiency contract](../implementation/runtime-efficiency.md).
F06/R04 stays Partial; V08 stays Building with collection off. All 66 requirement
states are unchanged. Native builds and public update acceptance for 4.46.61
require their own evidence, tracked in [release status](../RELEASE_STATUS.md).
