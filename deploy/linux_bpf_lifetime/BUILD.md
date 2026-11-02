# Linux BPF lifetime diagnostic

This is an optional, manual diagnostic. It does not replace `LinuxCgroupBackend`, does not activate telemetry, and does not accept a resource budget. `resource_acceptance` and `budget_comparison_allowed` stay false.

The birth hook is `fexit/copy_process`. A pre-exec write to `cgroup.procs` is a different mechanism and is not used. `create_io_thread` returns `copy_process` directly, so a fork tracepoint would miss io_uring workers.

## What a host must have

Build on the runner that will later run the diagnostic, or on another machine of the same architecture. Do not infer the kernel from an `ubuntu-22.04` label. The loader admits the running kernel at startup.

Free distro packages used by the manual workflow:

```sh
sudo apt-get update
sudo apt-get install -y clang llvm gcc libc6-dev make pkg-config libbpf-dev libelf-dev zlib1g-dev linux-libc-dev python3 python3-pytest
```

`clang` must accept `-target bpf`. `libbpf` must provide `bpf_object__open_file`, `bpf_program__attach`, and `libbpf_get_error`. The kernel UAPI header must define `struct bpf_prog_info.recursion_misses`. `bpftool` is not required to compile. Runtime admission still needs `/sys/kernel/btf/vmlinux`, fentry/fexit, and the privileges below.

## Compiler compatibility

The Makefile pins Clang 14 to `-mcpu=v1` for both objects. That is the smallest explicit BPF CPU. In LLVM 14, 64-bit `atomic_fetch_add` (`XFADDD`) is not gated on `HasAlu32`. It encodes `BPF_ADD | BPF_FETCH` and returns the old value. `alloc_cookie` keeps that return, so two births do not receive the same cookie. The pre-emit checker rejects a live result only for the non-fetch opcodes `XADDW`, `XADDD`, and `XADDW32`.

The group `live` counter stays an unused sequentially consistent add, including an add of `(__u32)-1`. A 32-bit `__sync_fetch_and_sub` was the operation Clang 14 could not select (`AtomicLoadSub` i32). The unused add stays a non-fetch XADD. `-mcpu=v3` is not required for the cookie return. It would also enable alu32 and jmp32 for the whole translation unit. v1 leaves those off.

The cookie instruction is still `BPF_FETCH` on this v1 object. Linux added that immediate in commit `5ca419f2864a` (2021-01-14), and it shipped in Linux 5.12. The loader still admits the running kernel. A finished compile is not permission to load. [Run 41240313726](https://github.com/Perseusxrltd/mnemion/actions/runs/41240313726) compiled the earlier objects and loader for x64 and ARM64 without loading BPF. The current admission and owner changes still require their first compilation and separate runtime checks.

Windows and a WSL userland without those packages can review and run the offline receipt tests. They cannot produce `lifetime.bpf.o`.

## Build

From the repository root:

```sh
make -C deploy/linux_bpf_lifetime
make -C deploy/linux_bpf_lifetime test-sha256
python3 -m pytest tests/test_linux_bpf_lifetime_parse.py -q --noconftest
```

`lifetime.bpf.c` includes `lifetime_bpf_prelude.h` before the libbpf helpers. That prelude includes the public `<linux/types.h>` and `<linux/bpf.h>` headers. The Makefile adds `/usr/include/x86_64-linux-gnu` on x64 and `/usr/include/aarch64-linux-gnu` on ARM64 so `asm/types.h` resolves. The receipt parity module `tests/test_linux_bpf_lifetime_receipt.py` is not in this correction and is not a build gate.

Outputs, next to the sources:

- `lifetime_plain.bpf.o` — `io_thread` is a normal field
- `lifetime_bitfield.bpf.o` — `io_thread` is a BTF bitfield
- `lifetime_diag` — loader, fixture, and cleanup owner

The loader reads BTF and opens the matching object. If `kernel_clone_args.io_thread` is absent, it refuses. It does not guess the layout.

## Run later, as root, on a disposable machine

Do not point this at a production host. `run_native=false` with the default `compile-only` lane does not execute a new native binary. `run_native=false` with `guard-only` executes the unprivileged guard under its external owner. `run_native=true` is refused. The collector is not qualified. Build outputs are retained.

`admission_guard_owner` exits 0 only when the child result is success and the status file was exclusively created, fully written, and closed. An existing status path is left in place. Publication failure prints `owner_status_publication=failed`, the checker, timeout, interruption, and cleanup fields, and `owner_child_result`. A child result of 0 then exits 1. A nonzero child result is the process status. Those fields are not rewritten to hide the publication failure. Guard-only and admission-only both keep that current file, including every status line, before guard success or admit. A failed copy stops the lane.

Cleanup uses `WNOHANG` only. Each pass reads the absolute cleanup deadline, reaps at most the existing 16-child hint, then signals adopted live children through a pidfd. `EINTR` retries the deadline check. Expiry leaves cleanup unconfirmed. `waitpid(-1)` returning `ECHILD` is still the empty-child proof. There is no blocking final wait.

`admission_guard_check` calls `external_owner_run` in process for the hanging checker and the early-exit child. That does not exec `admission_guard_owner` and does not prove status create, write, or close. `--status-fixture --status PATH` is the publication entry. It starts no child. Neither lane selects it. This tree has not run it.

```sh
sudo ./deploy/linux_bpf_lifetime/lifetime_diag --mode admit --receipt /tmp/lifetime-admit.bin
sudo ./deploy/linux_bpf_lifetime/lifetime_diag --mode direct --receipt /tmp/lifetime-direct.bin
```

Modes: `admit`, `direct`, `nested`, `orphan`, `thread`, `alloc`, `pre-exec`, `nonleader-exec`, `io-uring`, `capacity`, `reset`, `collector-death`.

`admit` attaches with collection disabled and does not launch a workload. The other modes enable collection only after the links are up, then `clone3` with `CLONE_INTO_CGROUP` into an empty cgroup. The work window is at most 10 seconds. Cleanup has its own 5 second bound. Short tasks are not kept alive so a poller can see them.

Exit 0 means the selected mode's expected result was recorded. It does not mean a resource budget was accepted. Read the receipt. Coverage, cleanup, support, and resource acceptance are separate fields.

## Receipt

`deploy/linux_bpf_lifetime/receipt.py` parses `lifetime_receipt.h`. A file is rejected when `resource_acceptance` or `budget_comparison_allowed` is nonzero, or when the stored verdict disagrees with the counters. `known_fixture_births` is ignored. NULL and ERR_PTR births are counted and do not by themselves fail an owned census, because a failed `copy_process` has no child. Map failures, duplicate identity, overflow, unknown owned tasks, recursion misses, detach, migration, and a reset all keep coverage false.

Group peak bytes come from the group summary only. Task records are not added together. Bytes are `maxrss` pages times the admitted page size, with the multiplication checked. Page size must be a power of two from 4096 through 65536.

## Containment

The process that stays alive is the cleanup owner. It is outside the cgroup and keeps the cgroup directory descriptor. The collector is its child. If the collector is killed, the owner writes `1` to that cgroup's `cgroup.kill` and waits for `populated 0`. It does not signal numeric pids taken from `cgroup.procs`. There is no descendant pidfd offer.

The fixture drops to uid 65534 and loses capabilities. The cgroup stays owned by the cleanup owner. Scope is `no external migration`: a process that a privileged outsider moves out of the cgroup is outside this claim. Cgroup emptiness alone is not a census.

Aggregate CPU is `usage_usec`, `user_usec`, and `system_usec` from the owned cgroup `cpu.stat`. Task CPU is not invented. `memory.peak` and `memory.current` are not read.

`clear_refs_write` sets a sticky reset on any call during the enabled window, including calls for other cgroups. That is the conservative guard. If `/proc/self/clear_refs` exists and the guard cannot attach, the loader refuses before the fixture. If the proc interface and the BTF function are both absent, that configuration is recorded and measurement may continue.

## First BTF parse refusal

Run 41361356839 refused on both architectures at `btf__parse` of kernel BTF, before prototype inspection, load, attach, or the fixture. The controller had already hashed BTF. The worker cleared `btf_ok` and sent refusal reason 3, then the parent kept the receipt and dropped that message. The published reason was filled later because the receipt reason was still 0. The parser's errno and libbpf error were not kept. That happened about 60–66 ms after custody was announced. The longer step also contains the guard. It is not an admission-deadline expiry.

The loader still refuses that parse. It does not change the kernel, the package list, privileges, or which BTF it accepts. On failure it writes one bounded line beside the receipt, named `<receipt>.btf-diag`. The admission lane reads at most 241 bytes of that file. It appends those bytes to the existing `admission-verdict.txt` only when they are exactly one record of the fixed pattern, one final newline, and no other byte. A path, a library sentence, an address, a second record, or a trailing fragment is not copied. A rejected file is replaced by one fixed `pointer=unknown` / `category=unknown` line. A missing file is left untouched. Neither case turns the refusal into success.

The line's stage is `btf_parse`. `errno` and `libbpf_error` are the numbers captured immediately after the call. `category` is a fixed name for that number, or `null` when the pointer is NULL and both numbers are 0, or `unknown` when the number is not in the list. `worker_reason` is the refusal code passed with the message. The parent stores that code on the existing receipt reason field when it is one of the defined reason codes, so publication does not replace it with a broader code derived from `btf_ok=0`.

`build_header` is the libbpf header macro when that header defines one. `runtime_linkage` is `libbpf_major_version` / `libbpf_minor_version` only when the loaded library exports them. libbpf.map places those symbols in `LIBBPF_0.6.0`, which inherits `LIBBPF_0.5.0`, so the 0.5 baseline leaves both calls weak and reports `unavailable`. That is not the apt package. The workflow writes `ci-receipts/libbpf-package.txt` with `record=package_provenance` from `dpkg-query` and does not pin `libbpf-dev`. The original run's apt log showed `1:0.5.0-1ubuntu22.04.1`. That package version is not established as the cause of the refusal.

The binary receipt stays 29160 bytes. Collection, fixture launch, coverage, and resource acceptance stay off on this refusal.

## Offline test

```sh
python3 -m pytest tests/test_linux_bpf_lifetime_parse.py -q --noconftest
```

That command runs the workflow export check and the existing source locks. It needs `bash`, because the export check is the shell function in the workflow. It does not compile the loader, and it is not a fault injection of the C capture path. That C behavior is source-reviewed and still uncompiled. A later `make -C deploy/linux_bpf_lifetime lifetime_diag` on distro libbpf is the compile check. It is not this test.
