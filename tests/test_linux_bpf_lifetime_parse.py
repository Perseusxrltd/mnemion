"""Offline checks for the cgroup-path parser, cookie seed, and BTF export validator.

The cgroup cases are a model of the loader's path rules. They do not load BPF,
drop privileges, or accept a receipt.

The BTF cases run retain_btf_parse_diag from the diagnostic workflow. They do
not reimplement that function. The C capture and refusal code is source-reviewed
and uncompiled. These checks do not fault-inject it, and they do not stand in
for a later compile or native admission proof.

The checks stay in this file. It is already on the diagnostic allowlist.
A new test path is not, and would pull the full product matrix.
"""

import re
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIFETIME = ROOT / "deploy" / "linux_bpf_lifetime"


def path_is_normalized(path):
    if not path or path[0] != "/":
        return False
    if len(path) > 1 and path.endswith("/"):
        return False
    for index, ch in enumerate(path):
        code = ord(ch)
        if code <= ord(" ") or ch == "\\" or code >= 0x7F:
            return False
        if ch == "/" and index + 1 < len(path) and path[index + 1] == "/":
            return False
    if ".." in path or "(deleted)" in path:
        return False
    return True


def line_is_other_cgroup(line):
    if not line or not line[0].isdigit():
        return False
    index = 0
    while index < len(line) and line[index].isdigit():
        index += 1
    if index == 0 or index >= len(line) or line[index] != ":":
        return False
    index += 1
    while index < len(line) and line[index] != ":":
        index += 1
    if index >= len(line) or line[index] != ":":
        return False
    if index + 1 >= len(line):
        return False
    return True


def parse_exact_cgroup2_path(text):
    if not text:
        return None
    found = None
    cursor = 0
    while cursor < len(text):
        newline = text.find("\n", cursor)
        if newline < 0:
            line = text[cursor:]
            cursor = len(text)
            finished = True
        else:
            line = text[cursor:newline]
            cursor = newline + 1
            finished = cursor >= len(text)
        if line == "":
            return None
        if line.endswith("\r"):
            return None
        if line.startswith("0::"):
            if found is not None:
                return None
            path = line[3:]
            if not path_is_normalized(path):
                return None
            found = path
        elif not line_is_other_cgroup(line):
            return None
        if finished:
            break
    return found


def parent_cgroup_path(text):
    path = parse_exact_cgroup2_path(text)
    if path is None or path == "/":
        return None
    return path


def seed_cookies(task, group, enabled):
    task = int(task)
    group = int(group)
    if not enabled:
        if task == 0:
            task = 1
        if group == 0:
            group = 1
    return task, group


def function_body(text, signature):
    start = text.index(signature)
    rest = text[start:]
    nxt = rest.find("\nstatic ", 1)
    if nxt < 0:
        return rest
    return rest[:nxt]


def test_exact_cgroup_line_keeps_the_newline_out_of_the_path():
    text = "0::/parent/mnemion-bpf-life-abcd\n"
    leaf = "mnemion-bpf-life-abcd"
    assert not text.endswith(leaf)
    assert parse_exact_cgroup2_path(text) == "/parent/" + leaf


def test_exact_cgroup_line_without_a_newline():
    assert parse_exact_cgroup2_path("0::/parent/leaf") == "/parent/leaf"


def test_other_controller_lines_are_kept_and_a_second_v2_line_is_rejected():
    hybrid = "12:cpu,cpuacct:/\n0::/parent/leaf\n1:name=systemd:/parent\n"
    assert parse_exact_cgroup2_path(hybrid) == "/parent/leaf"
    doubled = "0::/parent/leaf\n0::/parent/leaf\n"
    assert parse_exact_cgroup2_path(doubled) is None


def test_malformed_cgroup_text_is_rejected():
    assert parse_exact_cgroup2_path("0::/parent/leaf/\n") is None
    assert parse_exact_cgroup2_path("0::/parent/../leaf\n") is None
    assert parse_exact_cgroup2_path("0::/parent/leaf(deleted)\n") is None
    assert parse_exact_cgroup2_path("0::/parent/leaf\n\n") is None
    assert parse_exact_cgroup2_path("0::/parent/leaf\r\n") is None
    assert parse_exact_cgroup2_path("not-a-cgroup-line\n") is None
    assert parse_exact_cgroup2_path("10::/parent/leaf\n") is None
    assert parse_exact_cgroup2_path("") is None


def test_full_path_is_required_rather_than_a_leaf_suffix():
    expected = "/parent/mnemion-bpf-life-abcd"
    same_leaf_elsewhere = "0::/other/mnemion-bpf-life-abcd\n"
    longer = "0::/parent/mnemion-bpf-life-abcd-extra\n"
    assert parse_exact_cgroup2_path(same_leaf_elsewhere) != expected
    assert parse_exact_cgroup2_path(longer) != expected
    assert parse_exact_cgroup2_path("0::" + expected + "\n") == expected


def test_root_cgroup_is_not_a_parent_for_the_owned_leaf():
    assert parse_exact_cgroup2_path("0::/\n") == "/"
    assert parent_cgroup_path("0::/\n") is None
    assert parent_cgroup_path("0::/parent\n") == "/parent"


def test_cookie_allocators_seed_once_while_disabled_and_survive_final_disable():
    task, group = seed_cookies(0, 0, enabled=0)
    assert (task, group) == (1, 1)
    task, group = seed_cookies(task, group, enabled=1)
    assert (task, group) == (1, 1)
    task, group = 40, 12
    task, group = seed_cookies(task, group, enabled=0)
    assert (task, group) == (40, 12)
    assert seed_cookies(0, 9, enabled=0) == (1, 9)
    assert seed_cookies(0, 0, enabled=1) == (0, 0)


def test_corrected_source_keeps_the_six_fixes_and_the_existing_hooks():
    bpf = (LIFETIME / "lifetime.bpf.c").read_text(encoding="utf-8")
    prelude = (LIFETIME / "lifetime_bpf_prelude.h").read_text(encoding="utf-8")
    makefile = (LIFETIME / "Makefile").read_text(encoding="utf-8")
    receipt = (LIFETIME / "lifetime_receipt.h").read_text(encoding="utf-8")
    loader = (LIFETIME / "lifetime_loader.c").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "linux-bpf-lifetime-diagnostic.yml").read_text(
        encoding="utf-8"
    )

    assert bpf.index('#include "lifetime_bpf_prelude.h"') < bpf.index(
        "#include <bpf/bpf_helpers.h>"
    )
    assert prelude.index("#include <linux/types.h>") < prelude.index("#include <linux/bpf.h>")
    assert "/usr/include/x86_64-linux-gnu" in makefile
    assert "/usr/include/aarch64-linux-gnu" in makefile
    assert "r->counters" not in receipt
    assert "offsetof(struct lifetime_receipt, counters)" in receipt
    assert "BPF_CORE_READ(" not in bpf
    assert "BPF_CORE_READ_INTO(" in bpf
    assert "BPF_MAP_TYPE_LRU_HASH" not in bpf
    assert "__uint(map_flags, BPF_F_NO_PREALLOC)" not in bpf
    assert "intentionally absent" in bpf
    assert 'SEC("fexit/copy_process")' in bpf
    assert 'SEC("fentry/taskstats_exit")' in bpf
    assert "if (prev == 0 || prev >= LIFETIME_COOKIE_LIMIT)" in bpf

    exit_body = function_body(bpf, "static __always_inline void on_exit")
    failed = exit_body.index("BPF_CORE_READ_INTO(&pages, sig, maxrss)")
    stored = exit_body.index("summary.maxrss_pages = pages")
    assert failed < exit_body.index("LIFETIME_CTR_CORE_READ_FAIL", failed) < stored

    cfg = function_body(loader, "static int set_cfg(")
    assert "if (!enabled)" in cfg
    assert "cfg.next_task_cookie = 1" in cfg
    assert "cfg.next_group_cookie = 1" in cfg
    assert "next_task_cookie = 0" not in cfg
    assert "next_group_cookie = 0" not in cfg

    drop = function_body(loader, "static int drop_privs(")
    assert drop.index("setgroups(") < drop.index("setresgid(") < drop.index("setresuid(")
    assert drop.index("setresuid(") < drop.index("__NR_capset") < drop.index("PR_SET_NO_NEW_PRIVS")
    assert "parse_exact_cgroup2_path(" in loader
    assert "ends_with_leaf" not in loader

    assert "default: false" in workflow
    assert "contents: read" in workflow
    assert "timeout-minutes: 20" in workflow
    assert "persist-credentials: false" in workflow
    assert "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803" in workflow
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in workflow
    assert "if: always()" in workflow
    native_if = workflow.index("if: ${{ inputs.run_native == true }}")
    assert native_if < workflow.index("lifetime_diag")
    assert "tests/test_linux_bpf_lifetime_receipt.py" not in workflow


# Closed names for the captured number. 4002 is absent on purpose.
BTF_CLASSES = (
    (1, "access"),
    (2, "absent"),
    (7, "size"),
    (12, "memory"),
    (13, "access"),
    (22, "invalid"),
    (27, "size"),
    (38, "unsupported"),
    (61, "format"),
    (71, "format"),
    (75, "size"),
    (95, "unsupported"),
    (4000, "elf"),
    (4001, "format"),
    (4003, "endian"),
    (4004, "internal"),
)
BTF_CATEGORY_GROUP = (
    "null|access|absent|memory|size|invalid|unsupported|format|elf|endian|internal|unknown"
)
CLOSED_RECORD = (
    "stage=btf_parse pointer=error_pointer errno=0 libbpf_error=-22 "
    "category=invalid worker_reason=3 build_header=unavailable "
    "runtime_linkage=unavailable\n"
)
CLOSED_FALLBACK = (
    "stage=btf_parse pointer=unknown errno=0 libbpf_error=0 category=unknown "
    "worker_reason=0 build_header=unavailable runtime_linkage=unavailable\n"
)
CANARY = b"CANARY-LEAK"
VERDICT_PREFIX = b"admission_verdict=fail\n"


def export_validator_source():
    """The workflow function itself. Not a Python copy of its pattern."""
    workflow = (ROOT / ".github" / "workflows" / "linux-bpf-lifetime-diagnostic.yml").read_text(
        encoding="utf-8"
    )
    marker = "          retain_btf_parse_diag() {"
    start = workflow.index(marker)
    line_start = workflow.rfind("\n", 0, start) + 1
    pos = start
    end = None
    while pos < start + 8000:
        next_nl = workflow.index("\n", pos)
        if workflow[pos:next_nl] == "          }":
            end = next_nl
            break
        pos = next_nl + 1
    if end is None:
        raise AssertionError("retain_btf_parse_diag did not close")
    program = workflow[line_start:end]
    assert program.startswith(marker)
    assert "head -c 241 --" in program
    assert "wc -l" not in program
    assert 'cat "$src"' not in program and 'cat -- "$src"' not in program
    assert "sudo" not in program
    assert "admission_guard_owner" not in program
    assert CLOSED_FALLBACK.strip("\n") in program
    return program


def append_diag(payload, src_exists=True, verdict_exists=True):
    program = export_validator_source() + '\nretain_btf_parse_diag "$1" "$2"\n'
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "lifetime-admit.bin.btf-diag"
        verdict = Path(tmp) / "admission-verdict.txt"
        if src_exists:
            src.write_bytes(b"" if payload is None else payload)
        if verdict_exists:
            verdict.write_bytes(VERDICT_PREFIX)
        completed = subprocess.run(
            [
                "bash",
                "--noprofile",
                "--norc",
                "-eo",
                "pipefail",
                "-c",
                program,
                "retain_btf_parse_diag",
                src.as_posix(),
                verdict.as_posix(),
            ],
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
        if not verdict_exists:
            assert not verdict.exists()
            return None
        return verdict.read_bytes()


def test_export_validator_appends_one_closed_record():
    verdict = append_diag(CLOSED_RECORD.encode("ascii"))
    assert verdict == VERDICT_PREFIX + CLOSED_RECORD.encode("ascii")
    assert CANARY not in verdict
    assert verdict.count(b"stage=btf_parse") == 1


def test_export_validator_rejects_a_trailing_fragment_or_second_record():
    valid = CLOSED_RECORD.encode("ascii")
    unterminated = append_diag(valid + CANARY)
    assert unterminated == VERDICT_PREFIX + CLOSED_FALLBACK.encode("ascii")
    assert CANARY not in unterminated
    assert b"libbpf_error=-22" not in unterminated

    extra_newline = append_diag(valid + b"\n")
    assert extra_newline == VERDICT_PREFIX + CLOSED_FALLBACK.encode("ascii")
    assert b"libbpf_error=-22" not in extra_newline

    second = valid.replace(b"worker_reason=3", b"worker_reason=15")
    two_records = append_diag(valid + second)
    assert two_records == VERDICT_PREFIX + CLOSED_FALLBACK.encode("ascii")
    assert b"worker_reason=15" not in two_records
    assert b"worker_reason=3" not in two_records
    assert CANARY not in two_records


def test_export_validator_closes_oversized_malformed_and_missing_input():
    valid = CLOSED_RECORD.encode("ascii")
    oversized = append_diag((b"A" * 230) + CANARY + CANARY)
    assert len((b"A" * 230) + CANARY) == 241
    assert oversized == VERDICT_PREFIX + CLOSED_FALLBACK.encode("ascii")
    assert CANARY not in oversized

    prefixed = append_diag(valid + CANARY + (b"A" * 200))
    assert prefixed == VERDICT_PREFIX + CLOSED_FALLBACK.encode("ascii")
    assert CANARY not in prefixed
    assert b"libbpf_error=-22" not in prefixed

    malformed = append_diag(
        b"stage=btf_parse pointer=error_pointer errno=0 libbpf_error=-22 "
        b"category=canaryleak worker_reason=3 build_header=unavailable "
        b"runtime_linkage=unavailable\n"
    )
    assert malformed == VERDICT_PREFIX + CLOSED_FALLBACK.encode("ascii")
    assert b"canaryleak" not in malformed

    embedded_nul = append_diag(valid + b"\x00" + CANARY)
    assert embedded_nul == VERDICT_PREFIX + CLOSED_FALLBACK.encode("ascii")
    assert CANARY not in embedded_nul
    assert b"libbpf_error=-22" not in embedded_nul

    missing = append_diag(None, src_exists=False)
    assert missing == VERDICT_PREFIX
    assert CLOSED_FALLBACK.encode("ascii") not in missing
    assert CANARY not in missing

    absent_verdict = append_diag(valid + CANARY, verdict_exists=False)
    assert absent_verdict is None


def c_btf_classes(text):
    start = text.index("static const struct lifetime_btf_class lifetime_btf_classes[] = {")
    end = text.index("};", start)
    return [
        (int(code), name) for code, name in re.findall(r"\{(\d+), \"([a-z]+)\"\}", text[start:end])
    ]


def test_btf_diagnostic_source_keeps_the_record_and_the_receipt_schema():
    loader = (LIFETIME / "lifetime_loader.c").read_text(encoding="utf-8")
    receipt = (LIFETIME / "lifetime_receipt.h").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "linux-bpf-lifetime-diagnostic.yml").read_text(
        encoding="utf-8"
    )
    build = (LIFETIME / "BUILD.md").read_text(encoding="utf-8")

    assert c_btf_classes(loader) == list(BTF_CLASSES)
    assert 4002 not in {code for code, _name in c_btf_classes(loader)}
    assert 'return "unknown"' in function_body(
        loader, "static const char *lifetime_btf_class_name("
    )
    assert "category=(%s)" % BTF_CATEGORY_GROUP in workflow
    assert BTF_CATEGORY_GROUP in workflow

    collector = function_body(loader, "static void collector(")
    parse = collector.index('btf__parse("/sys/kernel/btf/vmlinux", NULL);')
    assert collector.rfind("errno = 0;", 0, parse) > parse - 200
    assert collector.index("saved_errno = errno;", parse) < collector.index(
        "saved_libbpf = libbpf_get_error(btf);", parse
    )
    fail = collector.index("if (!btf || saved_libbpf)", parse)
    retain = collector.index("lifetime_btf_retain_parse_failure(", fail)
    finish = collector.index("collector_finish(", retain)
    assert "btf = NULL;" in collector[retain:finish]
    assert "LIFE_MSG_REFUSED" in collector[finish : finish + 180]
    assert "LIFETIME_REASON_BTF" in collector[finish : finish + 180]
    assert collector.count("lifetime_btf_retain_parse_failure(") == 1
    assert "collection_enabled" not in collector[fail:finish]
    assert "g_receipt.btf_ok = 0;" in collector[fail:retain]
    assert "g_receipt.prototype_ok = 0;" in collector[fail:retain]

    retain_body = function_body(loader, "static void lifetime_btf_retain_parse_failure(")
    for forbidden in (
        "observation_failed",
        "collection_enabled",
        "resource_acceptance",
        "budget_comparison_allowed",
        "support_admitted",
        "btf_ok",
    ):
        assert forbidden not in retain_body
    keep_body = function_body(loader, "static void lifetime_keep_worker_reason(")
    assert "receipt->reason = worker_reason;" in keep_body
    assert "observation_failed" not in keep_body
    worker = function_body(loader, "static int run_validate_worker(")
    assert worker.count("lifetime_keep_worker_reason(") == 2
    first = worker.index("if (msg.code == LIFE_MSG_REFUSED)")
    assert worker.index("lifetime_keep_worker_reason(", first) < worker.index(
        "g_receipt.observation_failed = 1;", first
    )
    second = worker.index("if (msg.code == LIFE_MSG_REFUSED)", first + 1)
    assert "if (msg.code == LIFE_MSG_REFUSED)" in worker[second : second + 400]
    assert worker.index("lifetime_keep_worker_reason(", second) > second

    assert "libbpf_strerror" not in loader
    assert "libbpf_set_strict_mode" not in loader
    assert "libbpf_version_string" not in loader
    assert "extern unsigned int libbpf_major_version(void) __attribute__((weak));" in loader
    assert "extern unsigned int libbpf_minor_version(void) __attribute__((weak));" in loader
    assert "#ifndef LIBBPF_MAJOR_VERSION" in loader
    assert "package_provenance" not in loader
    quiet = function_body(loader, "static int quiet_libbpf(")
    assert "return 0;" in quiet
    assert "(void)fmt;" in quiet
    assert "#define LIFETIME_RECEIPT_BYTES 29160u" in receipt
    assert "if (r->reason == LIFETIME_REASON_NONE)" in receipt
    assert "#define LIFETIME_ADMISSION_MS 20000u" in receipt
    assert "#define LIFETIME_CLEANUP_MS 5000u" in receipt
    assert "#define LIFETIME_REASON_DIGEST 30u" in receipt

    install = "sudo apt-get install -y clang llvm gcc libc6-dev make pkg-config libbpf-dev libelf-dev zlib1g-dev linux-libc-dev python3 python3-pytest"
    assert install in workflow
    assert "libbpf-dev=" not in workflow
    assert "record=package_provenance" in workflow
    assert "field=installed_package_not_runtime_linkage" in workflow
    assert workflow.count("ci-receipts/libbpf-package.txt") >= 2
    assert "retain_btf_parse_diag" in workflow
    assert (
        'if [ "$admit_rc" -ne 0 ] || [ "$export_rc" -ne 0 ] || [ "$reader_rc" -ne 0 ]; then'
        in workflow
    )
    assert "--run-ms 60000 --cleanup-ms 5000" in workflow
    assert "not established as the cause" in build
    assert "unavailable" in build
    assert "29160" in build
