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

The receipt validator's original 19 pure tests passed on Windows after
correcting a test portability failure involving the unavailable Windows
`SIGKILL` constant. A separate source check confirmed that the workflow and
runner use `MNEMION_RESIDENCY_ARCH`, preserving GitHub's own `RUNNER_ARCH`
variable. Those checks did not catch the native decoder defect below.

[Run 41149389299](https://github.com/Perseusxrltd/mnemion/actions/runs/41149389299)
completed with GitHub `success` on both targets for requested source
`e38cb8d2a6f7c9ed2d42056d08df546b427bb04b`. Workflow HEAD
`bd12b7c4a9b03946cfb9b2b0095325ad442f6b5f` differs only in generated status
files; the workflow and probe source bytes are identical. Both targets
obtained task-name ports and returned successful direct `task_info` calls
with SDK count 12 (48 bytes). The parent recorded these values in bytes:

| Target | Baseline resident peak | Live resident peak |
|---|---:|---:|
| `macos-26` ARM64 | 950,272 | 9,371,648 |
| `macos-15-intel` x64 | 405,504 | 8,798,208 |

The 8 MiB allocation was observed on both. After exit, both queries returned
`268435459`; final resident values stayed null and post-exit support false.
Both children were reaped, task-name ports were deallocated and cleanup
succeeded. These direct parent observations remain valid.

Manual review rejected the child `ru_maxrss` cross-check. `write_frame`
stores its 64-bit value at byte 4, but `read_frame` decoded at byte 0. The
original ARM64 and x64 receipts report `40250921669623811` and
`37788015623405571`, respectively: each is the live peak shifted left
32 bits, combined with `OP_DONE` value 3. Those are corrupt child values,
not independent peak measurements. The defect does not affect the direct
parent `task_info` calls or cleanup. **The original whole probe is not
accepted.** Its artifacts and failed cross-check are preserved without
rewriting values, replaying the run or rescoring it.

The decoder now reads the value at byte 4. Both C and Python check
`baseline peak <= child peak <= live peak`, allowing valid unequal values.
The Darwin adapter records live per-process kernel peaks. Final post-exit
and unseen-process coverage remain false; the Mach CPU timebase conversion
is unchanged.

The first pure Darwin test selection on Windows recorded 4 failed,
31 passed and 25 deselected in 2.78 seconds. The failures concerned a
pointer test double and fixtures without a timebase. After those fixture
corrections, 35 passed and 25 were deselected in 2.39 seconds. Both original
outputs are retained; the passing selection was not repeated. These pure
checks did not execute native Mach APIs.

Further review reproduced two faults: a failed port release was reported as
successful, and a live CPU read could charge a reused root during reaping.
The correction retains a failed release as failed cleanup and synchronizes live CPU with
`wait4`, checking the frozen root identity. Eight focused pure regressions
passed once in 2.55 seconds. The mixed current/kernel coverage check had
already passed; it was not a third fault.

Both Mac component jobs passed once in
[run 41154499871](https://github.com/Perseusxrltd/mnemion/actions/runs/41154499871)
on source `5a5ee191e965903417fa161029c555544e5fff0c`. The corrected C probe and
actual Python adapter have separate source-bound receipts. All four original
artifact ZIP digests were checked without rerunning binaries.

The corrected C probe recorded these peaks in bytes. Both SDK counts were
12; both post-exit queries returned `268435459` and remained unsupported.

| Target | Baseline peak | Live peak and child peak |
|---|---:|---:|
| `macos-15-intel` x64 | 401,408 | 8,794,112 |
| `macos-26` ARM64 | 933,888 | 9,355,264 |

The Python adapter's disposable-child self-check recorded:

| Target | Observed kernel peak (bytes) | `wait4` CPU (microseconds) |
|---|---:|---:|
| `macos-15-intel` x64 | 10,833,920 | 2,100,162 |
| `macos-26` ARM64 | 16,826,368 | 356,263 |

All four receipts record successful cleanup. Each adapter check observed
one identity; total and missing process counts remain unknown. Coverage stays
partial and `cpu_lifetime_complete` stays false. Final-peak and unseen-exited
coverage remain false; descendant memory coverage is unproven. These small
component checks do not measure whole-app RAM, compare hardware speed or
qualify the resource budget. Telemetry, workload and resource acceptance
remain false.

The reviewed public XNU commit is
[`f6217f8`](https://github.com/apple-oss-distributions/xnu/tree/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea),
dated 16 October 2025. Its
[basic-info structure](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/mach/task_info.h),
[task-info and power counters](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/kern/task.c),
and [rusage assignment](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/kern/bsd_kern.c)
are source evidence, not proof of macOS 27 behavior.

## Remaining acceptance

Whole-lifetime process coverage, the actual fixed-work CPU/RAM comparison
and qualification of an operated collector remain open. The existing 8 MiB
per-process and 0.5% of one-core allowances remain
**UNACCEPTED**. No historical installed workload was rescored or repeated by
this batch. All 66 product requirements retain their existing states.
