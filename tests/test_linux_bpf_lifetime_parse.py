"""Offline model of the cgroup-path parser and cookie seed.

This does not load BPF, drop privileges, or accept a receipt.
The C parser in deploy/linux_bpf_lifetime/lifetime_loader.c is the one
that will run on a Linux builder. These cases lock that behavior and
the source shape of this correction.
"""

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
