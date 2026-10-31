#ifndef LIFETIME_ABI_H
#define LIFETIME_ABI_H

/* Included by the BPF object and the native loader.
 * Callers provide __u8, __u32 and __u64.
 * Kernel pointers are map keys only. Values below are cookies and counters.
 */

#define LIFETIME_TASK_SLOTS 256
#define LIFETIME_GROUP_SLOTS 128
#define LIFETIME_SUMMARY_SLOTS 512
#define LIFETIME_COOKIE_LIMIT 1000000u
#define LIFETIME_CTR_COUNT 32

/* uapi linux/sched.h CLONE_THREAD. v6.6 copy_signal shares the
 * existing signal when this flag is set, so a thread must not invent a group.
 */
#define LIFETIME_CLONE_THREAD 0x00010000ull

#define LIFETIME_KIND_TASK 1u
#define LIFETIME_KIND_GROUP 2u

#define LIFETIME_CATEGORY_PROCESS 1u
#define LIFETIME_CATEGORY_THREAD 2u
#define LIFETIME_CATEGORY_IO_THREAD 3u

#define LIFETIME_CTR_BIRTHS 0u
#define LIFETIME_CTR_TASK_EXITS 1u
#define LIFETIME_CTR_GROUP_BIRTHS 2u
#define LIFETIME_CTR_GROUP_FINALS 3u
#define LIFETIME_CTR_EXECS 4u
#define LIFETIME_CTR_NULL_CHILD 5u
#define LIFETIME_CTR_ERR_PTR 6u
#define LIFETIME_CTR_INSERT_FAIL 7u
#define LIFETIME_CTR_UPDATE_FAIL 8u
#define LIFETIME_CTR_DELETE_FAIL 9u
#define LIFETIME_CTR_READ_FAIL 10u
#define LIFETIME_CTR_TASK_OVERFLOW 11u
#define LIFETIME_CTR_GROUP_OVERFLOW 12u
#define LIFETIME_CTR_COMPLETED_OVERFLOW 13u
#define LIFETIME_CTR_COOKIE_OVERFLOW 14u
#define LIFETIME_CTR_MISSING_BIRTH 15u
#define LIFETIME_CTR_DUPLICATE_BIRTH 16u
#define LIFETIME_CTR_DUPLICATE_EXIT 17u
#define LIFETIME_CTR_DUPLICATE_GROUP_FINAL 18u
#define LIFETIME_CTR_MISSING_GROUP_THREAD 19u
#define LIFETIME_CTR_UNKNOWN_OWNED 20u
#define LIFETIME_CTR_STALE_IDENTITY 21u
#define LIFETIME_CTR_RESET_EVENTS 22u
#define LIFETIME_CTR_CORE_READ_FAIL 23u
#define LIFETIME_CTR_OUTSIDE_SKIPPED 24u
#define LIFETIME_CTR_DISABLED_SKIPPED 25u
#define LIFETIME_CTR_RECURSION_MISS_DELTA 26u
#define LIFETIME_CTR_BYTE_OVERFLOW 27u
#define LIFETIME_CTR_DETACH_EVENTS 28u
#define LIFETIME_CTR_MIGRATION_EVENTS 29u

struct lifetime_cfg {
	__u32 enabled;
	__u32 possible_peak_reset;
	__u32 reserved0;
	__u32 reserved1;
	__u64 target_cgroup_id;
	__u64 next_task_cookie;
	__u64 next_group_cookie;
};

struct lifetime_task_rec {
	__u64 task_cookie;
	__u64 group_cookie;
	__u64 creator_cookie;
	__u64 signal_key;
	__u64 birth_start_time;
	__u64 birth_start_boottime;
	__u64 observed_start_time;
	__u64 observed_start_boottime;
	__u32 observed_pid;
	__u32 observed_tgid;
	__u32 observed_old_pid;
	__u32 category;
	__u32 exec_seen;
	__u32 reserved;
	__u64 prior_maxrss_pages;
};

struct lifetime_group_rec {
	__u64 group_cookie;
	__u32 live;
	__u32 reserved;
};

struct lifetime_done_key {
	__u32 kind;
	__u32 pad;
	__u64 cookie;
};

struct lifetime_summary_rec {
	__u32 kind;
	__u32 category;
	__u32 exec_seen;
	__u32 reserved;
	__u64 cookie;
	__u64 group_cookie;
	__u64 creator_cookie;
	__u64 maxrss_pages;
};

#endif
