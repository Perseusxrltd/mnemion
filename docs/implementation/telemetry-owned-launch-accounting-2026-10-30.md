# Owned-launch resource accounting

30 October 2026. Diagnostic adapter only. **Resource acceptance remains
unproven and production collection stays off.** The allowance is still
8,388,608 bytes of additional resident working set per participating process
and 0.5% of one core, both **UNACCEPTED**. This note does not raise that
allowance or rescore an old run.

The compiled observer in `deploy/probe_telemetry_renderer.py` starts after the
app is up, subtracts growth from a later sample, and sums CPU from processes
that are still alive at a 100 ms poll. A helper that has already exited is
absent from that sum. Missing polls were skipped rather than reported.

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
does not call this adapter. `installed_journey_boundary()` is the next call:
one owned launch around the existing 128-cycle workload and one fixed
counterbalance. No extra launches and no retries.

## Platform accounting

Windows creates an unnamed job, sets kill-on-close, and creates the child
suspended inside that job with `PROC_THREAD_ATTRIBUTE_JOB_LIST`. The thread
is resumed only after the PID is on the job list.
`JOBOBJECT_BASIC_ACCOUNTING_INFORMATION.TotalUserTime` and `TotalKernelTime`
include processes that have already terminated (Microsoft, job accounting).
`TotalTerminatedProcesses` counts limit violations only, so it is not used as
the exited-process count. `PeakJobMemoryUsed` is the job commit counter, not
working set. Per-process working set comes from `K32GetProcessMemoryInfo`
while the process can still be opened. That peak is the kernel value at the
last successful query, so working-set coverage stays partial even when the
job's CPU total is complete. An exited process that was never opened has
null RSS, and the identity gap is a count, not a zero.

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
reported as zero.

`setpgrp` puts the child in its own process group. The group remains while
any member is alive, including after the root exits. Activity and cleanup
follow that group through `proc_listpids` with `PROC_PGRP_ONLY` (Apple
`proc_info.h` value 2). They do not scan every pid. Before
`kill(-pgid, SIGKILL)`, a live process whose pid equals the group id must
still have the root's recorded `proc_pid_rusage` start. A different start is
pid reuse: nothing is signaled, and the failure is `pid_reused`. One signal
is sent. If members are still present after it, the failure is
`descendants_survived` and the signal is not repeated. If the group cannot
be listed, the failure is `group_unverified`.

Resident size is current RSS. Physical footprint is not read. `wait4`
includes only descendants the direct child itself reaped. Reparented
descendants stay outside that CPU total, and this adapter has no kernel RSS
high-water for the tree. Coverage stays `partial`. `cpu_lifetime_complete`
and `cpu_includes_exited_descendants` stay false. Partial coverage is the
limit of this counter. It is not a zero CPU result.

The next measurement boundary is unchanged: one owned launch around the
existing 128-cycle workload and one fixed counterbalance, after Astra's
hosted self-check on the six native targets. This note does not attach that
workload. The allowance stays 8,388,608 bytes and 0.5% of one core, both
UNACCEPTED. Production collection stays off.

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
a sleeper through the owned group. On Windows it also records one failed
terminate of an invalid handle and does not retry it. A host that cannot
create a disposable cgroup returns honest unsupported and does not launch an
unmeasured process. The command does not install the app or run the 128-cycle
workload.

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
adapter's honest unsupported result. A macOS receipt with partial coverage
and a positive `wait4` total is the expected limit. A missing or zero CPU
total is not a pass.

## Sources

- Microsoft, `JOBOBJECT_BASIC_ACCOUNTING_INFORMATION`: user and kernel totals
  include terminated processes.
- Microsoft, nested jobs and `PROC_THREAD_ATTRIBUTE_JOB_LIST`: assignment at
  creation, before the new process runs.
- Linux kernel cgroup v2: `cpu.stat` `usage_usec` covers the cgroup and its
  descendants; `memory.peak` is the cgroup's recorded memory usage.
- Apple `proc_info.h`: `pti_resident_size` is resident memory. The adapter
  uses `proc_pid_rusage` `ri_resident_size` and does not use footprint.
  `PROC_PGRP_ONLY` is 2 and lists one process group.
- Python `os.wait4` returns `(pid, status, rusage)`. `resource.getrusage`
  documents `ru_utime` and `ru_stime` as float seconds.
- POSIX `kill`: a pid less than -1 signals the process group whose id is
  the absolute value. The group remains until its members are gone.
- systemd `Delegate=`: a scope with delegation is the cut at which the unit
  may create child cgroups. The service manager keeps the cgroup tree at
  and above that unit. `Delegate=yes` does not by itself write the host
  `cgroup.subtree_control`.
