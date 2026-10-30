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
Resident size is current RSS. Physical footprint is not read. `wait4` does
not cover descendants reparented outside the child, so macOS stays partial
and its CPU lifetime is not marked complete. There is no kernel RSS high-water
for the tree in this adapter. Cleanup signals the process group created for
that child.

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

## Sources

- Microsoft, `JOBOBJECT_BASIC_ACCOUNTING_INFORMATION`: user and kernel totals
  include terminated processes.
- Microsoft, nested jobs and `PROC_THREAD_ATTRIBUTE_JOB_LIST`: assignment at
  creation, before the new process runs.
- Linux kernel cgroup v2: `cpu.stat` `usage_usec` covers the cgroup and its
  descendants; `memory.peak` is the cgroup's recorded memory usage.
- Apple `proc_info.h`: `pti_resident_size` is resident memory. The adapter
  uses `proc_pid_rusage` `ri_resident_size` and does not use footprint.
