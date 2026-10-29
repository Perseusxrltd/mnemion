# Phase-memory diagnostic — 29 October 2026

This note adds an opt-in measurement. It does not contain a new app comparison,
and it does not pass a resource gate. The original six-case observations stay
as recorded. No source optimization is justified by those observations.

The client change is on branch `grok/telemetry-phase-counters-20261029`, based
on `f10a6cacdf25b93c009a1115357528157a65c36f` (source version 4.46.54). It records
counters only when `--phase-memory` is combined with `--comparison`. The flag
cannot be combined with attribution or the review journey. A normal diagnostic
dispatch leaves the input false, so an unprofiled run does not gain these
fields. `resource_acceptance` stays false. The working-set metric is unchanged.

## What a future comparison would record

At the existing nine `processSample` checkpoints, the main process records two
fixed numeric groups and nothing else:

- Linux `/proc/self/status`, read at most 65,536 bytes: `VmRSS`, `VmHWM`,
  `RssAnon`, `RssFile`, `RssShmem`. Values are converted from kB to bytes.
  [proc_pid_status(5)](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html)
  defines `VmRSS` as `RssAnon + RssFile + RssShmem` and says that value is
  inaccurate. The process `Name` and every other status field are not retained.
- Selected fields from Node `v8.getHeapStatistics()`, as documented for
  [Node.js v24](https://nodejs.org/docs/latest-v24.x/api/v8.html):
  `total_heap_size` (bytes V8 has allocated for the heap),
  `total_physical_size` (committed physical memory, not reserved address space),
  `used_heap_size` (heap bytes currently in use; not proof that all of those objects survive collection), and
  `malloced_memory` (bytes allocated through malloc by V8). Heap-space names
  and the rest of the statistics object are dropped.

A missing, oversized, non-integer, or unsupported counter stays null. Null is
unavailable, not zero. The summary adds phase-matched growth differences beside
the existing working-set differences. It does not emit a new maximum gate.
There is no new recurring sampler, no first-call wrapper, no forced GC, no
idle padding, and no change to workload or control order.

The result, receipt, and summary each carry `phase_memory: true`. The
qualification text says these counters do not replace or pass the working-set
gate. A summary that finds the counters without that flag is rejected, so an
instrumented diagnostic cannot be reread as the old unprofiled acceptance run.

## First failures that remain failed

The completed SQL-read comparison, GitHub Actions run
[40523504727](https://github.com/Perseusxrltd/mnemion/actions/runs/40523504727),
source `3034bc0b78b4b0ca52f2d794a3273a4e71999cca`, still fails the 2 MiB
matched-phase working-set gate. The enabled main-process maxima are 2,572,288
bytes at r1 `96_memory_cycles` and 2,859,008 bytes at r2 `64_memory_cycles`.
That run did not record `RssAnon`, `RssFile`, `RssShmem`, or
`v8.getHeapStatistics()`. Its `heapTotal` growth differences at those two
checkpoints were 2,256,896 and 2,097,152 bytes. Its `heapUsed` growth
differences were 974,236 and 405,492 bytes. Those alignments are not a callsite.

Earlier failures stay failed as well: delivery run 40483350394 (3,768,320 /
3,129,344), catalog run 40477197149, probe-controls run 40470335733,
resource-roles run 40453953300 (3,579,904 / 3,366,912), metadata run
40416923461 (9,261,056 / 2,936,832), scoped-trust `4b8e8a3e` (4,341,760 /
3,428,352), allocation-followup `4779cf11` (3,145,728 / 3,186,688), attribution
`dc98218c` / run 40265207114 (3,608,576 / 3,391,488), storage-followup
`de53ba46` (3,121,152 / 3,235,840), and the SQLite-cleanup sampled peak
3,440,640. The private SQLite alternative was not adopted. CPU percentages on
run 40523504727 (0.397806% and 0.210209%) remain descriptive and do not meet
the separate 0.5% ceiling. The 2,097,152-byte gate is the matched-phase
working-set growth difference, not ending RSS and not a difference of peaks.

## What the next measurement can falsify

Astra decides whether to dispatch one new comparison after this client change.
On that run only:

- If the `RssAnon` growth difference is at or under 2,097,152 bytes and
  `RssFile` accounts for the working-set excess, the gap is file-backed.
  Shrinking preference row objects would not remove it.
- If `RssAnon` stays over 2,097,152 while `used_heap_size` stays under and
  `total_heap_size` tracks the gap, a later source edit is justified only when
  a further measurement shows those live counters falling at r1
  `96_memory_cycles` and r2 `64_memory_cycles` in both replicates.
- If `RssAnon + RssFile + RssShmem` still does not meet the working-set
  difference, there is still no callsite and no source edit.

`PRAGMA shrink_memory` or a forced collection can move ending RSS by returning
pages that the next open allocates again. This diagnostic does not do either.

## Exact next command

Do not treat a local parser check as that measurement. The workflow command,
with `comparison` true, `phase_memory` true, `attribution` false, and
`review_journey` false, is:

```text
xvfb-run -a uv run --no-sync python -m deploy.probe_telemetry_renderer \
  --source "$GITHUB_WORKSPACE" \
  --output "$GITHUB_WORKSPACE/output/telemetry-renderer/workload" \
  --playwright-module "$RUNNER_TEMP/telemetry-controller/node_modules/playwright/index.mjs" \
  --comparison --phase-memory
uv run --no-sync python -m deploy.report_telemetry_renderer \
  output/telemetry-renderer/workload \
  --output output/telemetry-renderer/summary.json
```

Dispatch **Telemetry renderer diagnostic** only for a reviewed 40-hex source
that contains this change. This note does not dispatch it.

## Checks

These checks do not launch the app and do not dispatch GitHub Actions.

- Node parser, on this Windows checkout: `node --test studio/electron/scripts/phase-memory.test.mjs`. Five tests passed and none failed. The non-Linux status read stayed unavailable. That run does not read a live Linux `/proc/self/status`.
- Windows system Python: `py -m pytest tests/test_telemetry_renderer_report.py` failed before collection. `tests/conftest.py` imports `chromadb`, and that interpreter does not have it. This is an environment mismatch, not a product result.
- Astra, 2026-10-29T19:58:47Z, pinned interpreter `/home/jorqu/.local/state/mnemion-release/2026-10-10/release-venv/bin/python -m pytest tests/test_telemetry_renderer_report.py -q --tb=short`. Exit 0. Forty-four tests passed in 9.44s. The worker was stopped, the nine touched files were unchanged by that run, and there was no full app trial.
- After that run, Ruff 0.15.11 from the existing project environment formatted `deploy/probe_telemetry_renderer.py` and `deploy/report_telemetry_renderer.py`. The diff is line wrapping. `ruff check` then passed on those two files and `tests/test_telemetry_renderer_report.py`. The 44 passes were not repeated after the wrap.

## Limits

No check here executed Electron, the six-case workload, or GitHub Actions.
Production collection, destination, and route stay false/null/null. V08 remains
Building. All 66 requirements remain. The 2 MiB matched-phase working-set gate
and the separate 0.5 percent CPU ceiling stay unpassed. No installed, platform,
privacy, or resource acceptance follows from adding the counters.
