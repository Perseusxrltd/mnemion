#include "lifetime_bpf_prelude.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>
#include "lifetime_abi.h"

/* fexit/copy_process, not sched_process_fork: v6.6 create_io_thread returns
 * copy_process directly and never reaches kernel_clone's fork trace.
 * Collection stays off until userspace enables it. No ring buffer.
 */

#ifndef IO_THREAD_AS_BITFIELD
#error IO_THREAD_AS_BITFIELD must be 0 or 1
#endif

char LICENSE[] SEC("license") = "GPL";

#define LIFETIME_BPF_E2BIG 7
#define LIFETIME_BPF_ENOMEM 12
#define LIFETIME_BPF_EEXIST 17

struct pid;

struct kernfs_node {
	__u64 id;
} __attribute__((preserve_access_index));

struct cgroup {
	struct kernfs_node *kn;
} __attribute__((preserve_access_index));

struct css_set {
	struct cgroup *dfl_cgrp;
} __attribute__((preserve_access_index));

struct signal_struct {
	__u64 maxrss;
} __attribute__((preserve_access_index));

struct task_struct {
	__s32 pid;
	__s32 tgid;
	struct css_set *cgroups;
	struct signal_struct *signal;
	struct task_struct *real_parent;
	__u64 start_time;
	__u64 start_boottime;
} __attribute__((preserve_access_index));

#if IO_THREAD_AS_BITFIELD
struct kernel_clone_args {
	__u64 flags;
	__u32 io_thread : 1;
} __attribute__((preserve_access_index));
#else
struct kernel_clone_args {
	__u64 flags;
	__u32 io_thread;
} __attribute__((preserve_access_index));
#endif

struct file;

struct {
	__uint(type, BPF_MAP_TYPE_ARRAY);
	__uint(max_entries, 1);
	__type(key, __u32);
	__type(value, struct lifetime_cfg);
} lifetime_cfg SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_ARRAY);
	__uint(max_entries, LIFETIME_CTR_COUNT);
	__type(key, __u32);
	__type(value, __u64);
} lifetime_counters SEC(".maps");

/* Preallocated hash. BPF_F_NO_PREALLOC and LRU are intentionally absent. */
struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, LIFETIME_TASK_SLOTS);
	__type(key, __u64);
	__type(value, struct lifetime_task_rec);
} lifetime_tasks SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, LIFETIME_GROUP_SLOTS);
	__type(key, __u64);
	__type(value, struct lifetime_group_rec);
} lifetime_groups SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, LIFETIME_SUMMARY_SLOTS);
	__type(key, struct lifetime_done_key);
	__type(value, struct lifetime_summary_rec);
} lifetime_completed SEC(".maps");

#define BUMP(IDX)                                                                          \
	do {                                                                               \
		__u32 _bump_idx = (IDX);                                                   \
		__u64 *_bump_slot = bpf_map_lookup_elem(&lifetime_counters, &_bump_idx);   \
		if (_bump_slot)                                                            \
			__sync_fetch_and_add(_bump_slot, 1);                              \
	} while (0)

static __always_inline int is_err_ptr(__u64 raw)
{
	return raw >= ((__u64)0 - 4095u);
}

static __always_inline int read_cgroup_id(struct task_struct *task, __u64 *out)
{
	struct css_set *cset = NULL;
	struct cgroup *cgrp = NULL;
	struct kernfs_node *kn = NULL;
	__u64 id = 0;

	if (!task || !out)
		return -1;
	/* A failed probe zeroes its destination. That zero is not an outside cgroup. */
	if (BPF_CORE_READ_INTO(&cset, task, cgroups))
		return -1;
	if (!cset)
		return -1;
	if (BPF_CORE_READ_INTO(&cgrp, cset, dfl_cgrp))
		return -1;
	if (!cgrp)
		return -1;
	if (BPF_CORE_READ_INTO(&kn, cgrp, kn))
		return -1;
	if (!kn)
		return -1;
	if (BPF_CORE_READ_INTO(&id, kn, id))
		return -1;
	if (id == 0)
		return -1;
	*out = id;
	return 0;
}

static __always_inline int read_io_thread(struct kernel_clone_args *args, __u32 *out)
{
#if IO_THREAD_AS_BITFIELD
	unsigned long long val = 0;
	long rc;

	if (!args || !out)
		return -1;
	rc = bpf_probe_read_kernel(
		&val, __builtin_preserve_field_info(args->io_thread, BPF_FIELD_BYTE_SIZE),
		(const void *)((unsigned long)args +
			       __builtin_preserve_field_info(args->io_thread, BPF_FIELD_BYTE_OFFSET)));
	if (rc < 0)
		return -1;
	val <<= __builtin_preserve_field_info(args->io_thread, BPF_FIELD_LSHIFT_U64);
	val >>= __builtin_preserve_field_info(args->io_thread, BPF_FIELD_RSHIFT_U64);
	*out = (__u32)val;
	return 0;
#else
	__u32 value = 0;

	if (!args || !out)
		return -1;
	if (BPF_CORE_READ_INTO(&value, args, io_thread))
		return -1;
	*out = value;
	return 0;
#endif
}

static __always_inline __u64 alloc_cookie(__u64 *slot)
{
	__u64 prev = __sync_fetch_and_add(slot, 1);

	if (prev == 0 || prev >= LIFETIME_COOKIE_LIMIT)
		return 0;
	return prev;
}

static __always_inline __u64 creator_cookie(void)
{
	struct task_struct *cur = (struct task_struct *)bpf_get_current_task_btf();
	__u64 key = (__u64)cur;
	struct lifetime_task_rec *rec;
	__u64 cookie = 0;

	if (!key)
		return 0;
	rec = bpf_map_lookup_elem(&lifetime_tasks, &key);
	if (rec)
		cookie = rec->task_cookie;
	return cookie;
}

static __always_inline int owned_or_error(struct task_struct *task, __u64 target, int *owned)
{
	__u64 cgid = 0;

	*owned = 0;
	if (read_cgroup_id(task, &cgid) < 0) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return -1;
	}
	if (cgid == target)
		*owned = 1;
	return 0;
}

static __always_inline void note_update_error(int rc, __u32 overflow_counter, __u32 duplicate_counter)
{
	if (!rc)
		return;
	if (rc == -LIFETIME_BPF_E2BIG || rc == -LIFETIME_BPF_ENOMEM)
		BUMP(overflow_counter);
	else if (rc == -LIFETIME_BPF_EEXIST)
		BUMP(duplicate_counter);
	else
		BUMP(LIFETIME_CTR_INSERT_FAIL);
}

static __always_inline void on_birth(struct kernel_clone_args *args, struct task_struct *child)
{
	__u32 zero = 0;
	struct lifetime_cfg *cfg;
	__u32 enabled;
	__u64 target;
	__u64 raw;
	__u64 cgid = 0;
	__u64 flags;
	__u64 signal_key;
	struct signal_struct *child_sig;
	__u32 io_thread;
	__u32 category;
	int is_thread;
	__u64 creator;
	__u64 start_time;
	__u64 start_boot;
	__s32 pid;
	__s32 tgid;
	__u64 task_cookie;
	__u64 group_cookie = 0;
	struct lifetime_task_rec trec = {};
	int rc;

	cfg = bpf_map_lookup_elem(&lifetime_cfg, &zero);
	if (!cfg) {
		BUMP(LIFETIME_CTR_READ_FAIL);
		return;
	}
	enabled = cfg->enabled;
	target = cfg->target_cgroup_id;
	if (!enabled) {
		BUMP(LIFETIME_CTR_DISABLED_SKIPPED);
		return;
	}
	if (!target) {
		BUMP(LIFETIME_CTR_READ_FAIL);
		return;
	}
	if (!child) {
		BUMP(LIFETIME_CTR_NULL_CHILD);
		return;
	}
	raw = (__u64)child;
	if (is_err_ptr(raw)) {
		BUMP(LIFETIME_CTR_ERR_PTR);
		return;
	}
	if (!args) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	if (read_cgroup_id(child, &cgid) < 0) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	if (cgid != target) {
		BUMP(LIFETIME_CTR_OUTSIDE_SKIPPED);
		return;
	}
	if (BPF_CORE_READ_INTO(&flags, args, flags)) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	if (read_io_thread(args, &io_thread) < 0) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	if (BPF_CORE_READ_INTO(&child_sig, child, signal)) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	signal_key = (__u64)child_sig;
	if (!signal_key) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	is_thread = (flags & LIFETIME_CLONE_THREAD) != 0;
	if (io_thread)
		category = LIFETIME_CATEGORY_IO_THREAD;
	else if (is_thread)
		category = LIFETIME_CATEGORY_THREAD;
	else
		category = LIFETIME_CATEGORY_PROCESS;
	creator = creator_cookie();
	if (BPF_CORE_READ_INTO(&start_time, child, start_time)) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	if (BPF_CORE_READ_INTO(&start_boot, child, start_boottime)) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	if (BPF_CORE_READ_INTO(&pid, child, pid)) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	if (BPF_CORE_READ_INTO(&tgid, child, tgid)) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}

	if (is_thread) {
		struct lifetime_group_rec *group = bpf_map_lookup_elem(&lifetime_groups, &signal_key);

		if (!group) {
			BUMP(LIFETIME_CTR_MISSING_GROUP_THREAD);
			return;
		}
		group_cookie = group->group_cookie;
		__sync_fetch_and_add(&group->live, 1);
	}

	cfg = bpf_map_lookup_elem(&lifetime_cfg, &zero);
	if (!cfg) {
		BUMP(LIFETIME_CTR_READ_FAIL);
		return;
	}
	task_cookie = alloc_cookie(&cfg->next_task_cookie);
	if (!is_thread)
		group_cookie = alloc_cookie(&cfg->next_group_cookie);
	if (!task_cookie || !group_cookie) {
		BUMP(LIFETIME_CTR_COOKIE_OVERFLOW);
		return;
	}

	if (!is_thread) {
		struct lifetime_group_rec grec = {};

		grec.group_cookie = group_cookie;
		grec.live = 1;
		rc = bpf_map_update_elem(&lifetime_groups, &signal_key, &grec, BPF_NOEXIST);
		if (rc) {
			note_update_error(rc, LIFETIME_CTR_GROUP_OVERFLOW, LIFETIME_CTR_DUPLICATE_BIRTH);
			return;
		}
	}

	trec.task_cookie = task_cookie;
	trec.group_cookie = group_cookie;
	trec.creator_cookie = creator;
	trec.signal_key = signal_key;
	trec.birth_start_time = start_time;
	trec.birth_start_boottime = start_boot;
	trec.observed_start_time = start_time;
	trec.observed_start_boottime = start_boot;
	trec.observed_pid = (__u32)pid;
	trec.observed_tgid = (__u32)tgid;
	trec.category = category;
	rc = bpf_map_update_elem(&lifetime_tasks, &raw, &trec, BPF_NOEXIST);
	if (rc) {
		note_update_error(rc, LIFETIME_CTR_TASK_OVERFLOW, LIFETIME_CTR_DUPLICATE_BIRTH);
		if (!is_thread) {
			if (bpf_map_delete_elem(&lifetime_groups, &signal_key))
				BUMP(LIFETIME_CTR_DELETE_FAIL);
		} else {
			struct lifetime_group_rec *group = bpf_map_lookup_elem(&lifetime_groups, &signal_key);

			if (group)
				__sync_fetch_and_sub(&group->live, 1);
		}
		return;
	}
	if (!is_thread)
		BUMP(LIFETIME_CTR_GROUP_BIRTHS);
	BUMP(LIFETIME_CTR_BIRTHS);
}

static __always_inline void on_exec(struct task_struct *task, __s32 old_pid)
{
	__u32 zero = 0;
	struct lifetime_cfg *cfg;
	__u32 enabled;
	__u64 target;
	__u64 raw;
	struct lifetime_task_rec *found;
	struct lifetime_task_rec copy;
	struct signal_struct *sig;
	struct lifetime_group_rec *group;
	__u64 signal_key;
	__u64 pages;
	__u64 start_time;
	__u64 start_boot;
	__s32 pid;
	__s32 tgid;
	int rc;
	int owned = 0;

	cfg = bpf_map_lookup_elem(&lifetime_cfg, &zero);
	if (!cfg) {
		BUMP(LIFETIME_CTR_READ_FAIL);
		return;
	}
	enabled = cfg->enabled;
	target = cfg->target_cgroup_id;
	if (!enabled) {
		BUMP(LIFETIME_CTR_DISABLED_SKIPPED);
		return;
	}
	if (!task) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	raw = (__u64)task;
	found = bpf_map_lookup_elem(&lifetime_tasks, &raw);
	if (!found) {
		if (owned_or_error(task, target, &owned) < 0)
			return;
		if (owned) {
			BUMP(LIFETIME_CTR_UNKNOWN_OWNED);
			BUMP(LIFETIME_CTR_MISSING_BIRTH);
		} else {
			BUMP(LIFETIME_CTR_OUTSIDE_SKIPPED);
		}
		return;
	}
	copy = *found;
	if (BPF_CORE_READ_INTO(&sig, task, signal)) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	signal_key = (__u64)sig;
	if (!sig || signal_key != copy.signal_key) {
		BUMP(LIFETIME_CTR_STALE_IDENTITY);
		return;
	}
	if (BPF_CORE_READ_INTO(&pages, sig, maxrss)) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	group = bpf_map_lookup_elem(&lifetime_groups, &signal_key);
	if (!group || group->group_cookie != copy.group_cookie) {
		BUMP(LIFETIME_CTR_STALE_IDENTITY);
		return;
	}
	if (BPF_CORE_READ_INTO(&pid, task, pid)) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	if (BPF_CORE_READ_INTO(&tgid, task, tgid)) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	if (BPF_CORE_READ_INTO(&start_time, task, start_time)) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	if (BPF_CORE_READ_INTO(&start_boot, task, start_boottime)) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	copy.exec_seen += 1;
	copy.prior_maxrss_pages = pages;
	copy.observed_old_pid = (__u32)old_pid;
	copy.observed_pid = (__u32)pid;
	copy.observed_tgid = (__u32)tgid;
	copy.observed_start_time = start_time;
	copy.observed_start_boottime = start_boot;
	rc = bpf_map_update_elem(&lifetime_tasks, &raw, &copy, BPF_EXIST);
	if (rc)
		BUMP(LIFETIME_CTR_UPDATE_FAIL);
	else
		BUMP(LIFETIME_CTR_EXECS);
}

static __always_inline void on_exit(struct task_struct *task, int group_dead)
{
	__u32 zero = 0;
	struct lifetime_cfg *cfg;
	__u32 enabled;
	__u64 target;
	__u64 raw;
	struct lifetime_task_rec *found;
	struct lifetime_task_rec copy;
	struct lifetime_done_key dkey = {};
	struct lifetime_summary_rec summary = {};
	struct signal_struct *sig;
	__u64 signal_key;
	__u64 pages = 0;
	int rc;
	int owned = 0;

	cfg = bpf_map_lookup_elem(&lifetime_cfg, &zero);
	if (!cfg) {
		BUMP(LIFETIME_CTR_READ_FAIL);
		return;
	}
	enabled = cfg->enabled;
	target = cfg->target_cgroup_id;
	if (!enabled) {
		BUMP(LIFETIME_CTR_DISABLED_SKIPPED);
		return;
	}
	if (!task) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	raw = (__u64)task;
	found = bpf_map_lookup_elem(&lifetime_tasks, &raw);
	if (!found) {
		if (owned_or_error(task, target, &owned) < 0)
			return;
		if (owned) {
			BUMP(LIFETIME_CTR_UNKNOWN_OWNED);
			BUMP(LIFETIME_CTR_MISSING_BIRTH);
		} else {
			BUMP(LIFETIME_CTR_OUTSIDE_SKIPPED);
		}
		return;
	}
	copy = *found;
	dkey.kind = LIFETIME_KIND_TASK;
	dkey.cookie = copy.task_cookie;
	summary.kind = LIFETIME_KIND_TASK;
	summary.category = copy.category;
	summary.exec_seen = copy.exec_seen;
	summary.cookie = copy.task_cookie;
	summary.group_cookie = copy.group_cookie;
	summary.creator_cookie = copy.creator_cookie;
	summary.maxrss_pages = copy.prior_maxrss_pages;
	rc = bpf_map_update_elem(&lifetime_completed, &dkey, &summary, BPF_NOEXIST);
	if (rc)
		note_update_error(rc, LIFETIME_CTR_COMPLETED_OVERFLOW, LIFETIME_CTR_DUPLICATE_EXIT);
	else
		BUMP(LIFETIME_CTR_TASK_EXITS);
	if (bpf_map_delete_elem(&lifetime_tasks, &raw))
		BUMP(LIFETIME_CTR_DELETE_FAIL);

	if (!group_dead)
		return;
	if (BPF_CORE_READ_INTO(&sig, task, signal)) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	signal_key = (__u64)sig;
	if (!sig || signal_key != copy.signal_key) {
		BUMP(LIFETIME_CTR_STALE_IDENTITY);
		return;
	}
	/* A failed final maxrss read is a sticky failure, not a zero peak. */
	if (BPF_CORE_READ_INTO(&pages, sig, maxrss)) {
		BUMP(LIFETIME_CTR_CORE_READ_FAIL);
		return;
	}
	__builtin_memset(&summary, 0, sizeof(summary));
	dkey.kind = LIFETIME_KIND_GROUP;
	dkey.cookie = copy.group_cookie;
	summary.kind = LIFETIME_KIND_GROUP;
	summary.cookie = copy.group_cookie;
	summary.group_cookie = copy.group_cookie;
	summary.maxrss_pages = pages;
	rc = bpf_map_update_elem(&lifetime_completed, &dkey, &summary, BPF_NOEXIST);
	if (rc)
		note_update_error(rc, LIFETIME_CTR_COMPLETED_OVERFLOW, LIFETIME_CTR_DUPLICATE_GROUP_FINAL);
	else
		BUMP(LIFETIME_CTR_GROUP_FINALS);
	if (bpf_map_delete_elem(&lifetime_groups, &signal_key))
		BUMP(LIFETIME_CTR_DELETE_FAIL);
}

SEC("fexit/copy_process")
int BPF_PROG(lifetime_copy_process, struct pid *pid, int trace, int node, struct kernel_clone_args *args,
	     struct task_struct *child)
{
	(void)pid;
	(void)trace;
	(void)node;
	on_birth(args, child);
	return 0;
}

SEC("fentry/taskstats_exit")
int BPF_PROG(lifetime_taskstats_exit, struct task_struct *task, int group_dead)
{
	on_exit(task, group_dead);
	return 0;
}

SEC("raw_tp/sched_process_exec")
int BPF_PROG(lifetime_sched_process_exec, struct task_struct *task, __s32 old_pid, void *bprm)
{
	(void)bprm;
	on_exec(task, old_pid);
	return 0;
}

SEC("fentry/clear_refs_write")
int BPF_PROG(lifetime_clear_refs_write, struct file *file, const char *buf, unsigned long count, long long *ppos)
{
	__u32 zero = 0;
	struct lifetime_cfg *cfg;

	(void)file;
	(void)buf;
	(void)count;
	(void)ppos;
	cfg = bpf_map_lookup_elem(&lifetime_cfg, &zero);
	if (!cfg) {
		BUMP(LIFETIME_CTR_READ_FAIL);
		return 0;
	}
	if (!cfg->enabled)
		return 0;
	cfg->possible_peak_reset = 1;
	BUMP(LIFETIME_CTR_RESET_EVENTS);
	return 0;
}
