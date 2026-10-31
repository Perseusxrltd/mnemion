# Native memory counters and cleanup

31 October 2026. These diagnostic improvements support the
[whole-product efficiency requirement](../implementation/runtime-efficiency.md).
They do not establish an application CPU/RAM saving or accept the telemetry
overhead budget. Production collection remains off.

## Windows

The owned-launch observer now retains bounded, limited-query handles for
processes verified to belong to its job. It acquires the root's query handle
before allowing the root to run and reuses handles across samples. After the
job reports zero active processes, it reads each retained process's kernel
working-set peak again before closing the handles.

A native Windows AMD64 capability probe demonstrated that these reads work
after exit. Both final peaks were 12,288 bytes higher than their last live
sample. The original probe used an equality check and recorded false flags;
the raw values show that the final counters retained and extended the peak.
Those original results were preserved, not rerun or rewritten.

The subsequent native backend self-check exited successfully and reported
484,375 microseconds of lifetime CPU, zero active processes and successful
cleanup. It observed five identities out of six processes. Its final reads
covered the five retained identities; the sixth process remained an explicit
gap. This is one Windows AMD64 component result, not Windows ARM acceptance
or an installed-app overhead comparison.

Review found that a failed five-second job drain could still produce
`cleanup.ok=true` when handle closure succeeded. The corrected finish path
records `drain_timeout`, preserves an earlier failure and still closes each
handle once. It adds no second cleanup wait. Lifetime CPU remains incomplete
while job processes are active.

A failed query-handle open is now described as an unavailable observation:
access denial and other failures do not prove that a process exited. This
observation count is separate from `identities_missing`, which reconciles the
job's process count with recorded identities.

The original Windows fixture run had one incorrect handle-count assertion:
the test omitted the job handle from its expected closures. After correcting
that assertion, 29 tests passed. After the review corrections, 12 focused
Windows and report-normalization tests passed in 0.61 seconds. They include
failed-drain, successful and already-drained cleanup, membership and identity
checks, handle limits, final reads and preservation of unknowns.

`peak_working_set_final` identifies a successful post-drain read.
`kernel_high_water_while_observed` retains its separate live-observation
meaning. Both normalized report formats preserve the new flag; missing flags
remain unknown. Coverage stays partial, including when every observed handle
has a final peak. Unseen processes and truncated ledgers are not declared
covered. Job commit bytes are not reported as resident memory.

## macOS

Apple's public XNU sources define `MACH_TASK_BASIC_INFO.resident_size_max` as
the lifetime maximum of the resident-memory ledger. The basic-info flavor
accepts a task-name port. The current Mach timebase conversion is supported
by those sources; no CPU-unit correction was made.

The manual `native-residency-counters.yml` workflow tests this capability on
`macos-26` ARM64 and `macos-15-intel` x64. It compiles against the actual SDK,
starts one disposable child, observes a baseline and a touched 8 MiB
allocation, records the child's `getrusage` peak and attempts one final
query after exit. It requests no debugger or VM-read port. A denied counter
stays unavailable; a post-exit denial does not erase a successful live read.
The probe has a ten-second internal deadline and a bounded outer timeout.

The receipt validator's 19 pure tests passed on Windows after correcting a
test portability failure involving the unavailable Windows `SIGKILL`
constant. A separate source check confirmed that the workflow and runner use
`MNEMION_RESIDENCY_ARCH`, preserving GitHub's own `RUNNER_ARCH` variable.
**The two native Mac runs are pending at this source checkpoint.** The
production Darwin backend is unchanged.

The reviewed public XNU commit is
[`f6217f8`](https://github.com/apple-oss-distributions/xnu/tree/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea),
dated 16 October 2025. Its
[basic-info structure](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/mach/task_info.h),
[task-info and power counters](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/kern/task.c),
and [rusage assignment](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/kern/bsd_kern.c)
are source evidence, not proof of macOS 27 behavior.

## Remaining acceptance

Complete the targeted Mac capability check, preserve any unsupported result,
and finish process coverage and the actual fixed-work CPU/RAM comparison.
The existing 8 MiB per-process and 0.5% of one-core allowances remain
**UNACCEPTED**. No historical installed workload was rescored or repeated by
this batch. All 66 product requirements retain their existing states.
