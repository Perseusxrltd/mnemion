# Build the CO-RE object and the native loader. This does not load or attach BPF.
# Required packages are listed in BUILD.md. bpftool is not used.

CC ?= gcc
CLANG ?= clang
PKG_CONFIG ?= pkg-config

UNAME_M := $(shell uname -m)
ifeq ($(UNAME_M),x86_64)
TARGET_ARCH := x86
# x64 public UAPI asm headers (asm/types.h).
MULTIARCH_INC := /usr/include/x86_64-linux-gnu
endif
ifeq ($(UNAME_M),aarch64)
TARGET_ARCH := arm64
# ARM64 public UAPI asm headers (asm/types.h).
MULTIARCH_INC := /usr/include/aarch64-linux-gnu
endif
ifeq ($(TARGET_ARCH),)
$(error unsupported architecture $(UNAME_M); this diagnostic is x86_64 or aarch64)
endif
ifeq ($(MULTIARCH_INC),)
$(error missing UAPI include path for $(UNAME_M))
endif

LIBBPF_CFLAGS := $(shell $(PKG_CONFIG) --cflags libbpf 2>/dev/null)
LIBBPF_LIBS := $(shell $(PKG_CONFIG) --libs libbpf 2>/dev/null)
ifeq ($(LIBBPF_LIBS),)
LIBBPF_LIBS := -lbpf -lelf -lz
endif
# Clang 14 smallest explicit CPU is v1. 64-bit atomic_fetch_add (XFADDD) is
# not predicated on HasAlu32, so alloc_cookie's used return is BPF_FETCH here.
# The pre-emit check rejects a live def only for non-fetch XADDW/XADDD/XADDW32.
# The live counter's unused add of -1 stays that non-fetch XADD. v3 is not
# required and would enable alu32 and jmp32 for the whole object.
# Loading stays a later gate: BPF_FETCH needs Linux 5.12.
BPF_CFLAGS := -O2 -g -Wall -Werror -target bpf -mcpu=v1 -D__TARGET_ARCH_$(TARGET_ARCH) \
	$(LIBBPF_CFLAGS) -I$(MULTIARCH_INC) -I/usr/include

.PHONY: all clean test-sha256 test-admission-guard

# Compile the loader, the unprivileged guard check, and the external owner. Do not run them.
all: lifetime_plain.bpf.o lifetime_bitfield.bpf.o lifetime_diag sha256_selftest admission_guard_check admission_guard_owner

lifetime_plain.bpf.o: lifetime.bpf.c lifetime_abi.h lifetime_bpf_prelude.h
	$(CLANG) $(BPF_CFLAGS) -DIO_THREAD_AS_BITFIELD=0 -c lifetime.bpf.c -o $@

lifetime_bitfield.bpf.o: lifetime.bpf.c lifetime_abi.h lifetime_bpf_prelude.h
	$(CLANG) $(BPF_CFLAGS) -DIO_THREAD_AS_BITFIELD=1 -c lifetime.bpf.c -o $@

lifetime_diag: lifetime_loader.c admission_guard.c admission_guard.h lifetime_receipt.h lifetime_abi.h lifetime_sha256.h
	$(CC) -O2 -Wall -Wextra -Werror $(LIBBPF_CFLAGS) -o $@ lifetime_loader.c admission_guard.c $(LIBBPF_LIBS)

# Unprivileged supervision and IPC check. It does not create a cgroup or load BPF.
admission_guard_check: admission_guard_check.c admission_guard.c admission_guard.h admission_guard_owner.c admission_guard_owner.h lifetime_receipt.h lifetime_abi.h
	$(CC) -O2 -Wall -Wextra -Werror -DEXTERNAL_OWNER_LIB -o $@ admission_guard_check.c admission_guard.c admission_guard_owner.c

# External deadline owner. The guard-only lane and the later admission lane's guard check use it.
admission_guard_owner: admission_guard_owner.c admission_guard_owner.h
	$(CC) -O2 -Wall -Wextra -Werror -o $@ admission_guard_owner.c

test-admission-guard: admission_guard_check
	./admission_guard_check

sha256_selftest: sha256_selftest.c lifetime_sha256.h
	$(CC) -O2 -Wall -Wextra -Werror -o $@ sha256_selftest.c

test-sha256: sha256_selftest
	./sha256_selftest

clean:
	rm -f lifetime_plain.bpf.o lifetime_bitfield.bpf.o lifetime_diag sha256_selftest admission_guard_check admission_guard_owner
