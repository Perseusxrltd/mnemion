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

The cookie instruction is still `BPF_FETCH` on this v1 object. Linux added that immediate in commit `5ca419f2864a` (2021-01-14), and it shipped in Linux 5.12. The loader still admits the running kernel. A finished compile is not permission to load. This repository has not compiled these objects and has not loaded them.

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

Do not point this at a production host. The manual workflow is compile-only unless its dispatch input `run_native` is explicitly true. That input defaults to false. The collector is not qualified, and the workflow does not run it on the compile-only path. Build outputs are retained.

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

## Offline test

```sh
python3 -m pytest tests/test_linux_bpf_lifetime_parse.py -q --noconftest
```
