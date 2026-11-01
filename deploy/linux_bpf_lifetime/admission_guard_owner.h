#ifndef ADMISSION_GUARD_OWNER_H
#define ADMISSION_GUARD_OWNER_H

#include <stdint.h>

/* External owner for one command and the descendants that come back to it.
 * The run deadline and the cleanup deadline are absolute monotonic instants.
 * A timeout or unconfirmed cleanup fails even when the command exits 0.
 * Callers do not receive a pid or a process-group id to signal.
 */
struct external_owner_spec {
	char **argv;
	uint32_t run_ms;
	uint32_t cleanup_ms;
};

struct external_owner_result {
	int started;
	int child_exited;
	int child_exit_code;
	int child_signaled;
	int child_term_signal;
	int timed_out;
	int interrupted;
	int cleanup_confirmed;
	int ownership_unresolved;
};

/* 0 means the attempt finished and *out is filled. -1 means it could not start.
 * A finished attempt can still be a timeout or an unconfirmed cleanup.
 */
int external_owner_run(const struct external_owner_spec *spec, struct external_owner_result *out);

#endif
