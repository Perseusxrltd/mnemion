#ifndef LIFETIME_RECEIPT_H
#define LIFETIME_RECEIPT_H

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#ifndef LIFETIME_HAVE_U_TYPES
#define LIFETIME_HAVE_U_TYPES
typedef uint8_t __u8;
typedef uint32_t __u32;
typedef uint64_t __u64;
#endif
#include "lifetime_abi.h"

/* Fixed little-endian receipt. CAP_NET_ADMIN is not a substitute for
 * (CAP_BPF && CAP_PERFMON) || CAP_SYS_ADMIN.
 * known_fixture_births is ignored by the verdict.
 */

#define LIFETIME_RECEIPT_MAGIC 0x544C4E4Du
#define LIFETIME_RECEIPT_VERSION 1u
#define LIFETIME_RECEIPT_BYTES 29160u
#define LIFETIME_WORK_MS 10000u
#define LIFETIME_CLEANUP_MS 5000u

#define LIFETIME_MODE_ADMIT 1u
#define LIFETIME_MODE_DIRECT 2u
#define LIFETIME_MODE_NESTED 3u
#define LIFETIME_MODE_ORPHAN 4u
#define LIFETIME_MODE_THREAD 5u
#define LIFETIME_MODE_ALLOC 6u
#define LIFETIME_MODE_PRE_EXEC 7u
#define LIFETIME_MODE_NONLEADER_EXEC 8u
#define LIFETIME_MODE_IO_URING 9u
#define LIFETIME_MODE_CAPACITY 10u
#define LIFETIME_MODE_RESET 11u
#define LIFETIME_MODE_COLLECTOR_DEATH 12u

#define LIFETIME_REASON_NONE 0u
#define LIFETIME_REASON_ARCH 1u
#define LIFETIME_REASON_PAGE_SIZE 2u
#define LIFETIME_REASON_BTF 3u
#define LIFETIME_REASON_PROTOTYPE 4u
#define LIFETIME_REASON_CONFIG 5u
#define LIFETIME_REASON_PRIVILEGE 6u
#define LIFETIME_REASON_LOCKDOWN 7u
#define LIFETIME_REASON_RECURSION_FIELD 8u
#define LIFETIME_REASON_CLEAR_REFS 9u
#define LIFETIME_REASON_CGROUP 10u
#define LIFETIME_REASON_CGROUP_KILL 11u
#define LIFETIME_REASON_POPULATED 12u
#define LIFETIME_REASON_DIRECT_LAUNCH 13u
#define LIFETIME_REASON_CPU_STAT 14u
#define LIFETIME_REASON_LINK 15u
#define LIFETIME_REASON_LAUNCH_PATH 16u
#define LIFETIME_REASON_CONTAINMENT 17u
#define LIFETIME_REASON_ATTACH 18u
#define LIFETIME_REASON_COLLECTOR_DEATH 19u
#define LIFETIME_REASON_CENSUS 20u
#define LIFETIME_REASON_RESET 21u
#define LIFETIME_REASON_OVERFLOW 22u
#define LIFETIME_REASON_MAP 23u
#define LIFETIME_REASON_MISS 24u
#define LIFETIME_REASON_DETACH 25u
#define LIFETIME_REASON_MIGRATION 26u
#define LIFETIME_REASON_BYTES 27u
#define LIFETIME_REASON_UNSUPPORTED 28u
#define LIFETIME_REASON_SCENARIO 29u
#define LIFETIME_REASON_DIGEST 30u

#define LIFETIME_ARCH_X86_64 1u
#define LIFETIME_ARCH_AARCH64 2u

#define LIFETIME_CLEAR_ABSENT 1u
#define LIFETIME_CLEAR_ATTACHED 2u
#define LIFETIME_CLEAR_ATTACH_FAILED 3u
#define LIFETIME_CLEAR_UNOBSERVABLE 4u

#define LIFETIME_LAUNCH_NONE 0u
#define LIFETIME_LAUNCH_CLONE3 1u
#define LIFETIME_LAUNCH_PREEXEC 2u

#define LIFETIME_CONTAIN_NONE 0u
#define LIFETIME_CONTAIN_CGROUP_KILL 1u
#define LIFETIME_CONTAIN_PID_SIGNAL 2u
#define LIFETIME_SCOPE_NO_EXTERNAL_MIGRATION 1u

#define LIFETIME_IO_ENCODING_PLAIN 1u
#define LIFETIME_IO_ENCODING_BITFIELD 2u

struct lifetime_summary {
	uint32_t kind;
	uint32_t category;
	uint32_t exec_seen;
	uint32_t overflow;
	uint64_t cookie;
	uint64_t group_cookie;
	uint64_t creator_cookie;
	uint64_t maxrss_pages;
	uint64_t maxrss_bytes;
} __attribute__((packed));

struct lifetime_receipt {
	uint32_t magic;
	uint32_t version;
	uint32_t size;
	uint32_t reason;
	uint32_t mode;
	uint32_t page_size;
	uint32_t work_interval_ms;
	uint32_t cleanup_interval_ms;
	uint32_t summary_count;
	uint32_t active_tasks;
	uint32_t active_groups;
	uint32_t io_thread_encoding;
	uint8_t support_admitted;
	uint8_t fixture_launched;
	uint8_t collection_enabled;
	uint8_t census_clean;
	uint8_t scenario_qualified;
	uint8_t coverage_pass;
	uint8_t cleanup_attempted;
	uint8_t cleanup_pass;
	uint8_t resource_acceptance;
	uint8_t budget_comparison_allowed;
	uint8_t observation_failed;
	uint8_t collector_death;
	uint8_t possible_peak_reset;
	uint8_t clear_refs_state;
	uint8_t launch_path;
	uint8_t containment;
	uint8_t containment_scope;
	uint8_t cpu_aggregate_ok;
	uint8_t prototype_ok;
	uint8_t privileges_ok;
	uint8_t recursion_field_ok;
	uint8_t recursion_final_ok;
	uint8_t detach_or_loss;
	uint8_t migration_outside;
	uint8_t byte_overflow;
	uint8_t arch;
	uint8_t links_verified;
	uint8_t enabled_after_validation;
	uint8_t direct_launch_ok;
	uint8_t containment_ok;
	uint8_t config_taskstats;
	uint8_t config_cgroups;
	uint8_t lockdown_blocks;
	uint8_t page_size_ok;
	uint8_t btf_ok;
	uint8_t cgroup_ok;
	uint8_t cgroup_kill_ok;
	uint8_t populated_ok;
	uint8_t clone3_ok;
	uint8_t cpu_stat_ok;
	uint8_t path_unsupported;
	uint8_t io_thread_seen;
	uint8_t cap_bpf;
	uint8_t cap_perfmon;
	uint8_t cap_sys_admin;
	uint8_t align_pad[3];
	uint64_t cpu_usage_usec;
	uint64_t cpu_user_usec;
	uint64_t cpu_system_usec;
	uint64_t known_fixture_births;
	uint64_t counters[32];
	uint8_t kernel_release[65];
	uint8_t kernel_release_pad[3];
	uint8_t btf_digest[32];
	uint8_t digest_pad[4];
	struct lifetime_summary summaries[512];
} __attribute__((packed));

_Static_assert(sizeof(struct lifetime_summary) == 56, "summary size");
_Static_assert(sizeof(struct lifetime_receipt) == LIFETIME_RECEIPT_BYTES, "receipt size");

static const uint32_t LIFETIME_CENSUS_CTRS[] = {
	LIFETIME_CTR_BIRTHS,
	LIFETIME_CTR_TASK_EXITS,
	LIFETIME_CTR_GROUP_BIRTHS,
	LIFETIME_CTR_GROUP_FINALS,
	LIFETIME_CTR_EXECS,
};

static const uint32_t LIFETIME_INFO_CTRS[] = {
	LIFETIME_CTR_NULL_CHILD,
	LIFETIME_CTR_ERR_PTR,
	LIFETIME_CTR_OUTSIDE_SKIPPED,
	LIFETIME_CTR_DISABLED_SKIPPED,
};

static inline int lifetime_page_size_ok(uint32_t page_size)
{
	return page_size >= 4096u && page_size <= 65536u && (page_size & (page_size - 1u)) == 0;
}

static inline int lifetime_pages_to_bytes(uint64_t pages, uint32_t page_size, uint64_t *out)
{
	if (!lifetime_page_size_ok(page_size))
		return -1;
	if (page_size != 0 && pages > UINT64_MAX / page_size)
		return -1;
	*out = pages * (uint64_t)page_size;
	return 0;
}

static inline void lifetime_summary_at(const struct lifetime_receipt *r, uint32_t index,
				       struct lifetime_summary *out)
{
	size_t off = offsetof(struct lifetime_receipt, summaries) + (size_t)index * sizeof(*out);
	memcpy(out, (const unsigned char *)r + off, sizeof(*out));
}

static inline int lifetime_cover_mode(uint32_t mode)
{
	return mode >= LIFETIME_MODE_DIRECT && mode <= LIFETIME_MODE_IO_URING;
}

static inline uint32_t lifetime_admission_failure(const struct lifetime_receipt *r)
{
	int caps_ok = (r->cap_bpf && r->cap_perfmon) || r->cap_sys_admin;

	if (r->arch != LIFETIME_ARCH_X86_64 && r->arch != LIFETIME_ARCH_AARCH64)
		return LIFETIME_REASON_ARCH;
	if (!r->page_size_ok || !lifetime_page_size_ok(r->page_size))
		return LIFETIME_REASON_PAGE_SIZE;
	if (!r->btf_ok)
		return LIFETIME_REASON_BTF;
	if (!r->prototype_ok)
		return LIFETIME_REASON_PROTOTYPE;
	if (!r->config_taskstats || !r->config_cgroups)
		return LIFETIME_REASON_CONFIG;
	if (!caps_ok)
		return LIFETIME_REASON_PRIVILEGE;
	if (r->lockdown_blocks)
		return LIFETIME_REASON_LOCKDOWN;
	if (!r->recursion_field_ok)
		return LIFETIME_REASON_RECURSION_FIELD;
	if (r->clear_refs_state != LIFETIME_CLEAR_ABSENT && r->clear_refs_state != LIFETIME_CLEAR_ATTACHED)
		return LIFETIME_REASON_CLEAR_REFS;
	if (!r->cgroup_ok)
		return LIFETIME_REASON_CGROUP;
	if (!r->cgroup_kill_ok)
		return LIFETIME_REASON_CGROUP_KILL;
	if (!r->populated_ok)
		return LIFETIME_REASON_POPULATED;
	if (!r->clone3_ok || !r->direct_launch_ok)
		return LIFETIME_REASON_DIRECT_LAUNCH;
	if (!r->cpu_stat_ok)
		return LIFETIME_REASON_CPU_STAT;
	if (!r->links_verified)
		return LIFETIME_REASON_LINK;
	if (r->launch_path != LIFETIME_LAUNCH_CLONE3)
		return LIFETIME_REASON_LAUNCH_PATH;
	if (r->containment != LIFETIME_CONTAIN_CGROUP_KILL || !r->containment_ok)
		return LIFETIME_REASON_CONTAINMENT;
	if (!r->enabled_after_validation)
		return LIFETIME_REASON_ATTACH;
	return LIFETIME_REASON_NONE;
}

static inline uint64_t lifetime_counter(const struct lifetime_receipt *r, uint32_t index)
{
	uint64_t value;

	memcpy(&value,
	       (const unsigned char *)r + offsetof(struct lifetime_receipt, counters) +
		       (size_t)index * sizeof(value),
	       sizeof value);
	return value;
}

static inline uint32_t lifetime_census_failure(const struct lifetime_receipt *r)
{
	uint8_t allow[LIFETIME_CTR_COUNT];
	uint32_t i;
	uint32_t tasks = 0;
	uint32_t groups = 0;
	struct lifetime_summary s;
	struct lifetime_summary zero;
	uint64_t copied[LIFETIME_CTR_COUNT];
	const uint64_t *c;

	memcpy(copied, (const unsigned char *)r + offsetof(struct lifetime_receipt, counters), sizeof copied);
	c = copied;

	if (!r->fixture_launched || !r->collection_enabled)
		return LIFETIME_REASON_CENSUS;
	if (r->collector_death)
		return LIFETIME_REASON_COLLECTOR_DEATH;
	if (r->observation_failed)
		return LIFETIME_REASON_CENSUS;
	if (r->migration_outside || c[LIFETIME_CTR_MIGRATION_EVENTS] != 0)
		return LIFETIME_REASON_MIGRATION;
	if (r->detach_or_loss || c[LIFETIME_CTR_DETACH_EVENTS] != 0)
		return LIFETIME_REASON_DETACH;
	if (r->possible_peak_reset || c[LIFETIME_CTR_RESET_EVENTS] != 0)
		return LIFETIME_REASON_RESET;
	if (!r->recursion_field_ok || !r->recursion_final_ok || c[LIFETIME_CTR_RECURSION_MISS_DELTA] != 0)
		return LIFETIME_REASON_MISS;
	if (r->byte_overflow || c[LIFETIME_CTR_BYTE_OVERFLOW] != 0)
		return LIFETIME_REASON_BYTES;
	if (r->active_tasks != 0 || r->active_groups != 0)
		return LIFETIME_REASON_CENSUS;
	if (!r->cpu_aggregate_ok || !r->page_size_ok || !lifetime_page_size_ok(r->page_size))
		return LIFETIME_REASON_CENSUS;
	if (c[LIFETIME_CTR_TASK_OVERFLOW] || c[LIFETIME_CTR_GROUP_OVERFLOW] ||
	    c[LIFETIME_CTR_COMPLETED_OVERFLOW] || c[LIFETIME_CTR_COOKIE_OVERFLOW])
		return LIFETIME_REASON_OVERFLOW;
	memset(allow, 0, sizeof allow);
	for (i = 0; i < sizeof LIFETIME_CENSUS_CTRS / sizeof LIFETIME_CENSUS_CTRS[0]; i++)
		allow[LIFETIME_CENSUS_CTRS[i]] = 1;
	for (i = 0; i < sizeof LIFETIME_INFO_CTRS / sizeof LIFETIME_INFO_CTRS[0]; i++)
		allow[LIFETIME_INFO_CTRS[i]] = 1;
	for (i = 0; i < LIFETIME_CTR_COUNT; i++) {
		if (!allow[i] && c[i] != 0)
			return LIFETIME_REASON_MAP;
	}
	if (c[LIFETIME_CTR_BIRTHS] < 1 || c[LIFETIME_CTR_BIRTHS] != c[LIFETIME_CTR_TASK_EXITS])
		return LIFETIME_REASON_CENSUS;
	if (c[LIFETIME_CTR_GROUP_BIRTHS] < 1 || c[LIFETIME_CTR_GROUP_BIRTHS] != c[LIFETIME_CTR_GROUP_FINALS])
		return LIFETIME_REASON_CENSUS;
	if (r->summary_count != c[LIFETIME_CTR_BIRTHS] + c[LIFETIME_CTR_GROUP_FINALS])
		return LIFETIME_REASON_CENSUS;
	if (r->summary_count > LIFETIME_SUMMARY_SLOTS)
		return LIFETIME_REASON_CENSUS;
	memset(&zero, 0, sizeof zero);
	for (i = 0; i < r->summary_count; i++) {
		uint64_t bytes = 0;
		lifetime_summary_at(r, i, &s);
		if (s.cookie == 0 || s.overflow)
			return s.overflow ? LIFETIME_REASON_BYTES : LIFETIME_REASON_CENSUS;
		if (lifetime_pages_to_bytes(s.maxrss_pages, r->page_size, &bytes) != 0 || bytes != s.maxrss_bytes)
			return LIFETIME_REASON_BYTES;
		if (s.kind == LIFETIME_KIND_TASK) {
			tasks++;
			if (s.group_cookie == 0)
				return LIFETIME_REASON_CENSUS;
			if (s.category != LIFETIME_CATEGORY_PROCESS && s.category != LIFETIME_CATEGORY_THREAD &&
			    s.category != LIFETIME_CATEGORY_IO_THREAD)
				return LIFETIME_REASON_CENSUS;
		} else if (s.kind == LIFETIME_KIND_GROUP) {
			groups++;
			if (s.category != 0 || s.cookie != s.group_cookie)
				return LIFETIME_REASON_CENSUS;
		} else {
			return LIFETIME_REASON_CENSUS;
		}
	}
	if (tasks != c[LIFETIME_CTR_BIRTHS] || groups != c[LIFETIME_CTR_GROUP_FINALS])
		return LIFETIME_REASON_CENSUS;
	for (i = r->summary_count; i < LIFETIME_SUMMARY_SLOTS; i++) {
		lifetime_summary_at(r, i, &s);
		if (memcmp(&s, &zero, sizeof s) != 0)
			return LIFETIME_REASON_CENSUS;
	}
	return LIFETIME_REASON_NONE;
}

static inline int lifetime_scenario_ok(const struct lifetime_receipt *r)
{
	struct lifetime_summary s;
	uint32_t i;
	int process = 0;
	int thread = 0;
	int thread_exec = 0;
	int process_exec = 0;
	int peak = 0;
	uint64_t births;
	uint64_t groups;

	if (r->collector_death || r->path_unsupported || r->observation_failed)
		return 0;
	if (lifetime_census_failure(r) != LIFETIME_REASON_NONE)
		return 0;
	if (!lifetime_cover_mode(r->mode))
		return 0;
	births = lifetime_counter(r, LIFETIME_CTR_BIRTHS);
	groups = lifetime_counter(r, LIFETIME_CTR_GROUP_BIRTHS);
	for (i = 0; i < r->summary_count; i++) {
		lifetime_summary_at(r, i, &s);
		if (s.kind == LIFETIME_KIND_GROUP && s.maxrss_pages > 0)
			peak = 1;
		if (s.kind != LIFETIME_KIND_TASK)
			continue;
		if (s.category == LIFETIME_CATEGORY_PROCESS) {
			process = 1;
			if (s.exec_seen > 0)
				process_exec = 1;
		} else if (s.category == LIFETIME_CATEGORY_THREAD) {
			thread = 1;
			if (s.exec_seen > 0)
				thread_exec = 1;
		}
	}
	switch (r->mode) {
	case LIFETIME_MODE_DIRECT:
		return process;
	case LIFETIME_MODE_NESTED:
		return births >= 3 && groups >= 3;
	case LIFETIME_MODE_ORPHAN:
		return births >= 2 && groups >= 2;
	case LIFETIME_MODE_THREAD:
		return thread && births >= 2;
	case LIFETIME_MODE_ALLOC:
		return peak;
	case LIFETIME_MODE_PRE_EXEC:
		return process_exec;
	case LIFETIME_MODE_NONLEADER_EXEC:
		return thread_exec && process;
	case LIFETIME_MODE_IO_URING:
		return r->io_thread_seen;
	default:
		return 0;
	}
}

static inline void lifetime_note_io_threads(struct lifetime_receipt *r)
{
	struct lifetime_summary s;
	uint32_t i;

	r->io_thread_seen = 0;
	for (i = 0; i < r->summary_count && i < LIFETIME_SUMMARY_SLOTS; i++) {
		lifetime_summary_at(r, i, &s);
		if (s.kind == LIFETIME_KIND_TASK && s.category == LIFETIME_CATEGORY_IO_THREAD)
			r->io_thread_seen = 1;
	}
}

static inline void lifetime_apply(struct lifetime_receipt *r)
{
	uint32_t admission;
	uint32_t census;

	r->resource_acceptance = 0;
	r->budget_comparison_allowed = 0;
	r->containment_scope = LIFETIME_SCOPE_NO_EXTERNAL_MIGRATION;
	r->work_interval_ms = LIFETIME_WORK_MS;
	r->cleanup_interval_ms = LIFETIME_CLEANUP_MS;
	r->magic = LIFETIME_RECEIPT_MAGIC;
	r->version = LIFETIME_RECEIPT_VERSION;
	r->size = (uint32_t)sizeof(struct lifetime_receipt);
	lifetime_note_io_threads(r);

	admission = lifetime_admission_failure(r);
	r->support_admitted = admission == LIFETIME_REASON_NONE;
	if (!r->support_admitted) {
		r->census_clean = 0;
		r->scenario_qualified = 0;
		r->coverage_pass = 0;
		if (r->reason == LIFETIME_REASON_NONE)
			r->reason = admission;
		return;
	}
	if (!r->fixture_launched || !r->collection_enabled) {
		r->census_clean = 0;
		r->scenario_qualified = 0;
		r->coverage_pass = 0;
		return;
	}
	census = lifetime_census_failure(r);
	r->census_clean = census == LIFETIME_REASON_NONE;
	r->scenario_qualified = lifetime_scenario_ok(r);
	r->coverage_pass = r->census_clean && r->scenario_qualified && !r->path_unsupported &&
		!r->collector_death && lifetime_cover_mode(r->mode);
	if (!r->coverage_pass && r->reason == LIFETIME_REASON_NONE) {
		if (census != LIFETIME_REASON_NONE)
			r->reason = census;
		else if (r->collector_death)
			r->reason = LIFETIME_REASON_COLLECTOR_DEATH;
		else if (r->path_unsupported)
			r->reason = LIFETIME_REASON_UNSUPPORTED;
		else if (!r->scenario_qualified)
			r->reason = LIFETIME_REASON_SCENARIO;
	}
}

static inline int lifetime_mode_exit_ok(const struct lifetime_receipt *r)
{
	int cleanup = r->cleanup_attempted && r->cleanup_pass;
	int overflow = lifetime_counter(r, LIFETIME_CTR_TASK_OVERFLOW) ||
		lifetime_counter(r, LIFETIME_CTR_GROUP_OVERFLOW) ||
		lifetime_counter(r, LIFETIME_CTR_COMPLETED_OVERFLOW) ||
		lifetime_counter(r, LIFETIME_CTR_COOKIE_OVERFLOW);

	if (!cleanup || r->resource_acceptance || r->budget_comparison_allowed)
		return 0;
	switch (r->mode) {
	case LIFETIME_MODE_ADMIT:
		return r->support_admitted && !r->fixture_launched && !r->coverage_pass;
	case LIFETIME_MODE_CAPACITY:
		return !r->coverage_pass && overflow && !r->collector_death;
	case LIFETIME_MODE_RESET:
		return !r->coverage_pass && r->possible_peak_reset && !r->collector_death;
	case LIFETIME_MODE_COLLECTOR_DEATH:
		return !r->coverage_pass && r->collector_death && r->observation_failed;
	case LIFETIME_MODE_IO_URING:
		if (r->path_unsupported)
			return r->fixture_launched && !r->coverage_pass && !r->scenario_qualified;
		return r->coverage_pass && r->io_thread_seen;
	default:
		if (!lifetime_cover_mode(r->mode))
			return 0;
		return r->coverage_pass && !r->collector_death;
	}
}

/* One owned group's final bytes. Task priors are not added. */
static inline int lifetime_owned_group_peak_bytes(const struct lifetime_receipt *r, uint64_t *out)
{
	struct lifetime_summary s;
	uint32_t i;
	int saw = 0;
	uint64_t peak = 0;

	for (i = 0; i < r->summary_count && i < LIFETIME_SUMMARY_SLOTS; i++) {
		lifetime_summary_at(r, i, &s);
		if (s.kind != LIFETIME_KIND_GROUP)
			continue;
		if (s.overflow)
			return -1;
		if (!saw || s.maxrss_bytes > peak)
			peak = s.maxrss_bytes;
		saw = 1;
	}
	if (!saw)
		return -1;
	*out = peak;
	return 0;
}

#endif
