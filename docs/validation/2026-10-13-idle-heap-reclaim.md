# Returning released model memory to the OS — 2026-10-13

This is the **unreleased 4.2.1 follow-up**, separate from the frozen 4.2.0
candidate. It addresses retained memory reported in
[issue 13](https://github.com/Perseusxrltd/mnemion/issues/13). It does not close
the wider peak-memory and separate API/worker allocation work.

After a local model unloads, glibc can retain freed allocations in the process.
An extra Python garbage collection did not reduce this retained memory in
either measured profile. A glibc allocator hint returned additional free pages
to the operating system without changing model files, vectors or source spans.

The follow-up applies that hint after ordinary model cleanup and after
memory-budget eviction. It retains the existing exclusive inference gate,
idle policy, active/queued-work protection and opt-out. It resolves only the
current Linux process's glibc allocator. Windows, macOS, musl and unavailable
allocator interfaces retain ordinary cleanup. No working-set eviction is used.
The idle-eviction counter is published after cleanup completes, so an observer
cannot record memory before the allocator hint has finished.

## Measured result

Each row used a fresh offline Linux x64 process, glibc 2.39, one CPU, a 1,536 MiB
process-group limit and no swap. The pinned CPU model embedded synthetic source
text into 10–11 chunks, became idle for the configured ten-second test interval,
unloaded through the actual background monitor, and then reloaded offline.
The normal shipping idle default remains 300 seconds.

| Profile | Previous cleanup: idle RSS, MiB | Automatic follow-up: idle RSS, MiB | Reduction in this run |
| --- | ---: | ---: | ---: |
| Multilingual E5 small | 432.0 | 107.0 | 75.2% |
| English BGE small | 144.9 | 106.2 | 26.7% |

All four runs preserved query/document vectors within 1e-6, exact source spans,
on-disk model generations, offline reload and monitor shutdown. The
[numeric records](2026-10-13-idle-heap-measurements.json) identify the baseline
commit and follow-up source-file hashes. A separate manual allocator call after
automatic cleanup produced no further RSS decrease in either follow-up run.

These are isolated model-process observations, not whole-worker, API, database,
desktop or whole-host minimum requirements. The API and worker still load
separate models. Peak inference memory, other allocators, larger datasets and
other hardware can differ. No production memory or cloud model was used.

## Validation state

All **37 focused checks passed**, including actual database budget/purge
behavior, exclusion of active inference, publication of completion after heap
cleanup, pressure-triggered cleanup and safe handling of unsupported platforms
or unavailable native symbols. Python static checks also passed. The real
automatic-cleanup measurements above passed for both supported small models.

Full product/native release checks and delivery remain pending for 4.2.1.
The current public release is reported separately in
[release status](../RELEASE_STATUS.md).
