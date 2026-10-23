# Windows frozen host-client correction

**23 October 2026; unpublished 4.46.0 candidate.** This records the original
Windows failure and the source correction. Corrected native and live acceptance
remain pending. Current availability belongs to [release status](../RELEASE_STATUS.md).

## Original native failure

[Release run 39884444351](https://github.com/Perseusxrltd/mnemion/actions/runs/39884444351)
used frozen source
[`82925e7aa82826029fb576e7d39dc21166d09f6f`](https://github.com/Perseusxrltd/mnemion/commit/82925e7aa82826029fb576e7d39dc21166d09f6f).
Its [Windows x64 job 120193591209](https://github.com/Perseusxrltd/mnemion/actions/runs/39884444351/job/120193591209)
passed installed local hosting at **02:18:11 UTC**, then failed the packaged
window/bridge host-control check at **02:18:47 UTC**. The job ended in failure
at **02:18:53 UTC**. The subsequent Windows authenticated-update/relaunch step
was skipped; local-hosting success did not qualify the independent host client.

At the **02:44:45 UTC** observation, Windows ARM64
[job 120193591236](https://github.com/Perseusxrltd/mnemion/actions/runs/39884444351/job/120193591236)
had also failed its packaged host-control step, while all four Linux/macOS
native jobs had passed. Both Windows packages use the **same frozen x64 service
engine**, as required by the [desktop workflow](../../.github/workflows/desktop.yml);
ARM64 runs that engine in x64 compatibility mode. The parent run still reported
`in_progress` during final bookkeeping, with no active jobs. This snapshot does
not establish publication or a passing six-target release.

An isolated diagnostic copy of the original frozen engine changed only its
entry point; the bundled module archive and other runtime entries were retained.
Inspection reproduced exit code **2** and the bounded `invalid_request` reply,
with the underlying exception:

```text
ModuleNotFoundError: No module named 'win32timezone'
```

AsyncSSH constructed its Windows GSS/SSPI context before checking the disabled
GSS authentication flags. That unused authentication path reached the missing
module. The original job, failed receipt and diagnostic evidence remain
preserved privately. The diagnostic copy did not replace the installed app or
become a published artifact; raw traces and private paths are omitted here.

## Source correction and earlier gate

The [client](../../mnemion/host_control/transport.py) and
[listener](../../mnemion/host_control/server.py) now explicitly pass
`gss_host=None`, alongside the existing disabled GSS authentication/key-exchange
flags. This prevents initialization of the unused platform GSS context. The
protocol still requires its enrolled Ed25519 key and exact server fingerprint;
password, keyboard-interactive and ambient agent authentication remain disabled.
No shell or forwarding is added.

The [native engine builder](../../deploy/build_native_engine.py) now invokes an
[early frozen-engine probe](../../deploy/probe_native_host_control.py) before
archiving the engine for the longer desktop jobs. It requires the actual frozen
executable to generate an operator key, inspect status and history over pinned
loopback SSH, and refuse a changed server fingerprint with
`host_identity_changed`. Engine calls have finite deadlines. The disposable peer
has no memory service and the probe executes no service effects.

This early check supplements the installed UI, OS-protected key, process restart, native-agent,
authority and public-recovery-archive journey in the
[independent-host validation](2026-10-22-independent-host-control.md).

## Bounded source and diagnostic verification

**18 targeted source tests passed.** One existing Studio-built journey was
skipped because the fresh checkout had no compiled desktop output. That skip
remains explicit; the earlier Studio journey evidence is separate.

On native Windows, the early gate rejected the **original frozen binary** at
pinned SSH inspection in **6.17 seconds**. A second, separate diagnostic copy
retained the original bootloader, entry point and runtime dependencies, replacing
only the reviewed `mnemion.host_control.transport` and
`mnemion.host_control.server` module bytecode. That copy passed pinned inspection
and wrong-host-pin refusal in **8.15 seconds**, with clean stderr and **no service
effects**. This is diagnostic proof, not a rebuilt release or installed-package
acceptance result.

An initial Windows probe also exposed a temporary-directory cleanup failure.
The [fixture](../../deploy/native_host_control_fixture.py) now explicitly closes
its SQLite connection; the original cleanup failure remains preserved separately
from the transport failure and final diagnostic result.

## Deployment guidance and remaining acceptance

The [host-control guide](../guides/company-host-control.md#create-a-custodian-and-adopt-the-actual-host)
now separates firewall policy for the default TCP port **7893** from ordinary
OS SSH. Standard UFW `limit` rejects the sixth connection from one source IP
within 30 seconds. Successful desktop inspection uses two or three short pinned
SSH sessions; the visible host view polls every 15 seconds. Teams sharing one
public IP need reviewed allow rules or an appropriately sized rate policy for
this key-only protocol. This does not authorize additional network access or
change the separate OS SSH policy. The deployment plan was revised; production
firewall/controller adoption changes have not been applied.

Corrected frozen-engine, installed-platform and live independent-host results
remain pending. The earlier source and Linux preview evidence stays separate
from this Windows packaging failure. Published and actual Windows/Hostinger
acceptance remain at [4.45.1](2026-10-23-4451-live-acceptance.md) at this checkpoint.
Independent production host adoption is prepared, not applied. Boot/login
registration, whole-machine provider wake, full authority-state backup and
replacement-host recovery remain open. All 65 requirement states, issues
#44/#45, the separate PC publisher pause and administrator-owned stopped client
tests remain unchanged.
