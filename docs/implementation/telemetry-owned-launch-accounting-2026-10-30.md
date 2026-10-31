# Owned-launch resource accounting

30 October 2026. Diagnostic adapter only. **Resource acceptance remains
unproven and production collection stays off.** The allowance is still
8,388,608 bytes of additional resident working set per participating process
and 0.5% of one core, both **UNACCEPTED**. This note does not raise that
allowance or rescore an old run.

The earlier sampled-only observer started after the app was up, subtracted
growth from a later sample and summed CPU from processes still alive at a
100 ms poll. Exited helpers were absent from that sum. The adapter below
records owned lifetimes and keeps remaining coverage gaps explicit. See the
[31 October counter and cleanup follow-up](../validation/2026-10-31-native-memory-counters.md)
for current Windows behavior, Mac live-counter and descendant checks, and
the preserved original child-counter failure.

## API

`deploy/owned_launch_accounting.py`

`start_owned_launch(argv)` creates the OS group and only then lets the child
run. `mark_phase` records a monotonic offset and the cumulative count of
completed canonical operations. A phase named `idle`, `settlement`,
`send-settlement`, or `wait` cannot be marked active. Time before the first
mark is inactive. Active CPU is the sum of kernel-counter deltas on active
phases only. A missing counter stays null. A measured delta of zero stays zero.

`finish` returns lifetime CPU, the PID plus creation-identity ledger,
per-process working-set values when the kernel still has them, sampled peaks,
coverage, and cleanup. Cold start is the first observed absolute working set,
not a subtracted delta. The report's qualification is `unqualified`.

The installed launcher `studio/electron/scripts/smoke-installed-hosting.mjs`
calls `deploy.owned_installed_launch` only when
`MNEMION_TELEMETRY_INSTALLED_RESOURCE` is `1`. That branch runs the existing
128-cycle counterbalance. The two-launch delivery check stays separate and is
not this workload. Workflow input `resource_comparison` is a boolean and
defaults to false. It does not select or replace delivery targets. Omitted
or false runs the selected delivery targets, all six when that selection is
empty. True prepares one inactive package and one active package from the
same declared source.
Windows x64 freezes both engines. Windows ARM reuses those x64 archives and
does not freeze an engine. The observer stays outside each measured app
group. `MNEMION_OWNED_LAUNCH_PYTHON` is the native client interpreter; on
Windows ARM that is not `MNEMION_ENGINE_PYTHON`. Resource acceptance stays
false and both budgets stay unaccepted. Terminal markers carry the verified
cumulative count. Unknown crash progress sets `completed_known` false and
does not invent a count. The existing installed results and the separate
admission diagnostic are tracked in the
[CPU admission follow-up](../validation/2026-10-30-telemetry-cpu-admission.md).
Counter changes do not authorize repeating or rescoring those runs.

The [installed process-role RSS note](../validation/2026-10-31-installed-process-roles.md)
describes separate Electron checkpoint evidence retained in
`build-notes/telemetry-installed-resources.json`. Its focused source checks
passed; native installed verification remains pending. It does not replace
this OS ledger or accept the resource budget.

Windows reads the direct child with `GetExitCodeProcess` before finish closes
the process handle. Microsoft documents `STILL_ACTIVE` as 259
(`STATUS_PENDING`). A missing code or 259 is not success.

The compiled-source probe still calls `start_owned_launch` on
`probe-telemetry-renderer.mjs` for the existing six-launch counterbalance
(`--comparison` or `--attribution`). Review and the three-case journey are
unchanged. That remains a Linux source-app bridge.

## Platform accounting

Windows creates an unnamed job, sets kill-on-close, and creates the child
suspended inside that job with `PROC_THREAD_ATTRIBUTE_JOB_LIST`. The thread
is resumed only after membership and identity are verified on its process
handle and a limited-query handle is retained.
`JOBOBJECT_BASIC_ACCOUNTING_INFORMATION.TotalUserTime` and `TotalKernelTime`
include processes that have already terminated (Microsoft, job accounting).
`TotalTerminatedProcesses` counts limit violations only, so it is not used as
the exited-process count. `PeakJobMemoryUsed` is the job commit counter, not
working set. Per-process working set comes from `K32GetProcessMemoryInfo`.
The observer retains at most 512 verified query handles and reads their final
peaks after the job reports zero active processes. A failed final read keeps
the earlier bytes without labeling them final. The final flag survives both
report normalizers; an absent flag remains unknown. Lifetime CPU is complete
only after a drained-job accounting read. A failed bounded drain is a cleanup
failure even when handles close successfully. Unavailable query observations
do not imply process exit, and missing identities remain separate counts.
Working-set coverage stays partial because a process can disappear before
the observer obtains its handle. No missing value is replaced with zero.

Linux, when the process may create one child of its own cgroup v2 directory,
reads `cpu.stat` `usage_usec`. The kernel documents that counter as covering
the cgroup and descendant cgroups, whether or not the cpu controller is
enabled. The adapter does not write `cgroup.subtree_control`, `memory.max`,
or any host cgroup outside that disposable directory. `memory.peak` is cgroup
memory (anonymous, cache, and kernel) and is never copied into an RSS field.
Per-process `VmHWM` is kept per identity. Linux does not expose a lifetime
process count, so overall coverage stays partial even when CPU is complete.
Cleanup signals only pidfds whose start ticks still match, then removes the
directory. A removal failure is recorded and not retried.

macOS uses `proc_pid_rusage` resident size and `wait4` on the direct child.
`os.wait4` is the only call that reaps that child. `Popen.poll` is not used
on this path, because it reaps with `waitpid` and leaves a later `wait4`
with no rusage. Python's `rusage.ru_utime` and `ru_stime` are float seconds,
the same fields as `resource.getrusage`. After the root has exited, lifetime
CPU is that waited sum in microseconds. A missing or non-float result stays
null. It is not replaced from a live `proc_pid_rusage` reading and it is not
reported as zero. Memory sampling, live CPU reads and `wait4` share one
lock. A live CPU reading must match the frozen root creation identity;
unknown or reused identities stay unmeasured.

`setpgrp` puts the child in its own process group. The group remains while
any member is alive, including after the root exits. Activity and cleanup
follow that group through one bounded `proc_listpids` call with
`PROC_PGRP_ONLY` (Apple `proc_info.h` value 2). They do not scan every pid.
A null buffer is not a size probe: xnu `proc_info.c` answers it with
`(nprocs + 20) * sizeof(int)`, which is every process plus a margin, and
libproc turns a failed `__proc_info` (`-1`) into `0` while setting errno. A
real empty group is also `0` bytes, with errno clear. The adapter clears
errno, reads at most 64 pids, and treats a zero-byte result with errno clear
as empty. Errno, a short count that is not a whole pid list, a non-positive
pid in that list, or a buffer that comes back full stays unverified. The
kernel stops at the buffer, so a full buffer can omit a later member. A
group of 64 or more is unverified. Missing data is not an empty group and
it is not zero processes.

The root identity is the `proc_pid_rusage` start from the first sample that
reads the launched root. `spawn` takes that sample immediately. If that read
fails, the next successful read while the root is unreaped freezes the
identity. A reaped root with no frozen identity cannot adopt a later
process with the same pid.
A later sample whose start differs is dropped. It is not stored, and it does
not replace the identity used for cleanup. Before `kill(-pgid, SIGKILL)`, a
live process whose pid equals the group id must still have that frozen
start. A different start is pid reuse: nothing is signaled, and the failure
is `pid_reused`. One signal is sent. If members are still present after it,
the failure is `descendants_survived` and the signal is not repeated. If the
group cannot be listed, the failure is `group_unverified`.

Child listing uses one `proc_listchildpids` call with a fixed 64-PID buffer.
Its return is a PID count; the buffer length remains bytes. There is no null
size probe. A zero count with errno clear is empty; a full buffer, error,
out-of-range count or malformed PID list stays unverified.

Resident size is current RSS. Physical footprint is not read. `wait4`
includes only descendants the direct child itself reaped. Reparented
descendants stay outside that CPU total. Live per-process kernel peaks do
not cover the full tree lifetime. Coverage stays `partial`. `cpu_lifetime_complete`
and `cpu_includes_exited_descendants` stay false. Partial coverage is the
limit of this counter. It is not a zero CPU result.

The adapter lazily reads `MACH_TASK_BASIC_INFO.resident_size_max` through
`task_name_for_pid` and `task_info`, checking the kernel return and SDK count
12 (48 bytes). It requests a task-name right only, with no VM-read right or
broader fallback. Each obtained right receives one deallocation attempt.
A failed release remains a cleanup failure even after the owned group is
empty; an earlier cleanup failure is preserved. Ports are not kept for
later samples.

Within the existing bounded traversal, memory sampling checks each child's
creation identity and parent relationship before and after the memory query.
It also rechecks the parent's creation against the identity recorded earlier
in that sample, so a reused parent PID cannot admit unrelated memory.
A genuine live peak enters the identity ledger with
`kernel_high_water_while_observed` true. A denied or partial query may keep
validated current RSS; it does not create a peak or erase a previously
observed one. `peak_working_set_final` stays false, coverage stays partial
and unseen exited processes stay uncovered. Mixed current/kernel observations
report `live_kernel_high_water_partial`; that review check passed. The Mach CPU
timebase conversion and `wait4` limits are unchanged.

The corrected C probe and actual Python adapter passed the two Mac component
jobs in run 41154499871 on source `5a5ee191e965903417fa161029c555544e5fff0c`.
The workflow preserves separate `residency-counters-<os>-<arch>` and
`owned-launch-adapter-<os>-<arch>` artifacts with source and cleanup evidence.
Each adapter check in that run observed one identity and did not prove
descendant memory coverage. The cause of those observations remains unproven;
those historical results are unchanged. The original run 41149389299's
corrupt child cross-check also remains unaccepted and unchanged.

The later run 41159112141 passed once on both Mac targets at source
`300b5e7e362a46af93b53d5f15b2aae90b0b73a5`. Each deterministic fixture observed
one held live descendant. The separate ordinary work ledger recorded three
identities on Intel and two on ARM. Cleanup succeeded; lifetime CPU remains
incomplete, coverage partial, and final-peak and unseen-exited-process coverage
false. These component checks do not qualify app overhead.

Native workflow run 41009326091 on source `23835d6f1a0f085f82ef9bf68ebfab263eee6f33`
passed all six targets. Windows and Linux lifetime CPU were complete. macOS
descendant CPU stayed incomplete. Linux `memory.peak` was missing. Windows ARM
had two sampled identities missing. None of those receipts accept app overhead.

The compiled-source comparison in `.github/workflows/telemetry-renderer.yml`
runs without attribution, phase-memory, or review. That job is Linux compiled
source on `ubuntu-22.04` only. When that mode is selected, a short `id -u` child must
print the runner uid. The journey then runs as one transient service with
`Delegate=yes`, `User=` and `Group=` set to that runner, `WorkingDirectory`
set to the workspace, and only the tool/home environment (`PATH`, `HOME`,
and the other listed names). `sudo -n` does not preserve the caller's
environment. A root scope is not used: it would run PostgreSQL and git as
root and drop the runner `PATH`. The native self-check remains a scope
because that command is stdlib and does not start this fixture. The service
does not write host `cgroup.subtree_control`. If the probe does not show
the runner uid, the journey runs once as the runner without the service and
the adapter's unsupported result stays unqualified. `Delegate=yes` with
`User=` makes that service's cgroup writable by the runner. The controller
is moved into the disposable child before exec, so its children stay there
and exited processes remain in the cgroup CPU counter. The builder, the
frontend server, and the Python observer stay outside that child. The
adapter sampler still stops at 120 seconds. Lifetime and phase CPU are read
from the counter at each mark and at finish. RSS samples may truncate. The
cap is not raised. The probe still waits up to 240 seconds, then `finish()`
terminates the owned group once. `--collect` unloads the transient unit
after it exits. The allowance stays 8,388,608 bytes and 0.5% of one core,
both UNACCEPTED. Production collection stays off. Old results are not rescored.

Any platform that cannot account for the whole lifetime reports `partial` or
`unsupported` and stays unqualified.

## Self-check

```
python -m deploy.owned_launch_self_check
```

Run that one command on each hosted native target the release already builds
(Windows, macOS, and Linux, x64 and arm64). It launches a short CPU worker
and a descendant, checks that exited CPU is still in the OS counter after
the processes are gone, records identities and null counters, then terminates
a sleeper through the owned group. The work launch's own cleanup is checked
before the sleeper starts, so a failed work cleanup is not hidden by a later
successful sleeper termination. The failure string is the cleanup code
(`descendants_survived`, `pid_reused`, `group_unverified`, or another real
code). On Windows the command also records one failed terminate of an invalid
handle and does not retry it. That exercise is `invalid_handle_exercise`
(`terminate_job_6` on Windows). It is not `cleanup_failure`. A host that
cannot create a disposable cgroup returns honest unsupported and does not
launch an unmeasured process. That receipt does not claim cleanup succeeded.
The command does not install the app or run the 128-cycle workload.

On Darwin, a separate FIFO handshake holds a root and child live until the
sampler records both. It requires root exit code zero and successful owned
cleanup. If the second FIFO descriptor cannot open, the first is closed;
all held descriptors close on exit. Its descendant count is separate from
the ordinary work ledger and does not establish whole-lifetime coverage.

`.github/workflows/telemetry-owned-launch.yml` is manual
(`workflow_dispatch` only). It runs that command once on the six runners
already used for the native desktop builds: `windows-2022`, `windows-11-arm`,
`macos-15-intel`, `macos-26`, `ubuntu-22.04`, and `ubuntu-22.04-arm`. The
caller passes the exact 40-character source. The job checks that `HEAD`
matches it and uploads the JSON receipt, including a failed run. It does not
install the app, download a model, or run a benchmark. On a hosted Linux
runner it may put that one command in a disposable `systemd-run --scope`
unit with `Delegate=yes`, so the process can create a child of its own
cgroup. The workflow does not write the host `cgroup.subtree_control` and
does not change a developer machine's group permissions. If the scope cannot
be created, the same command runs once in the job and the receipt stays the
adapter's honest unsupported result. A held receipt qualifies only when
`cleanup_ok` is true and `cleanup_failure` is null, including a receipt
whose process exited zero. Missing or failed cleanup does not qualify.
Honest unsupported is recorded and does not qualify. A macOS receipt with
partial coverage, `cpu_lifetime_complete` false, a positive `wait4` total,
and cleanup ok is the expected limit. A missing or zero CPU total is not a
pass.

## Sources

- Microsoft, `GetExitCodeProcess`: `STILL_ACTIVE` is 259 (`STATUS_PENDING`).
  A process that has not exited is not a successful exit code.
- Microsoft, `JOBOBJECT_BASIC_ACCOUNTING_INFORMATION`: user and kernel totals
  include terminated processes.
- Microsoft, nested jobs and `PROC_THREAD_ATTRIBUTE_JOB_LIST`: assignment at
  creation, before the new process runs.
- Linux kernel cgroup v2: `cpu.stat` `usage_usec` covers the cgroup and its
  descendants; `memory.peak` is the cgroup's recorded memory usage.
- Apple `proc_info.h`: `pti_resident_size` is resident memory. The adapter
  uses `proc_pid_rusage` `ri_resident_size` and does not use footprint.
  `PROC_PGRP_ONLY` is 2 and lists one process group.
- Apple xnu `bsd/kern/proc_info.c`: a null `proc_listpids` buffer returns
  `(nprocs + 20) * sizeof(int)` and does not filter by process group. With a
  buffer, `PROC_PGRP_ONLY` keeps processes whose `p_pgrpid` matches, and an
  empty match returns 0 bytes. The walk stops when the buffer is full.
- Apple libproc `libproc.c`: if `__proc_info` returns `-1`, `proc_listpids`
  returns `0` and errno is set. A successful call returns the byte count,
  including `0`. Its `proc_listchildpids` wrapper returns a PID count while
  the buffer length remains bytes.
- Python `os.wait4` returns `(pid, status, rusage)`. `resource.getrusage`
  documents `ru_utime` and `ru_stime` as float seconds.
- POSIX `kill`: a pid less than -1 signals the process group whose id is
  the absolute value. The group remains until its members are gone.
- systemd `Delegate=` and cgroup delegation: delegation is the cut at which
  the unit may create child cgroups. For a service with `User=`, systemd
  chowns that subtree to the user. `Delegate=yes` does not by itself write
  the host `cgroup.subtree_control`. `systemd-run` without `--scope` starts
  a transient service in a clean environment, so the caller must set
  `User=`, `Group=`, `WorkingDirectory=`, and the variables it needs.
  `--collect` unloads that unit after it exits.
