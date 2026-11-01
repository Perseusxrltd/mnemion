#ifndef ADMISSION_GUARD_H
#define ADMISSION_GUARD_H

/* Independent of libbpf. The guardian process waits on an absolute
 * timer and supervisory pidfds. It does not treat a clock read after a
 * blocking call as the deadline. SIGKILL does not finish uninterruptible
 * kernel work; at the deadline the result is unconfirmed and owned
 * identities are kept for disposable-VM retirement.
 */

#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>
#include <time.h>

/* Linux UAPI types, before the receipt header's own typedefs. The loader
 * also includes linux/types.h; the macro keeps those typedefs from colliding.
 */
#include <linux/types.h>
#define LIFETIME_HAVE_U_TYPES
#include "lifetime_receipt.h"

#define GUARD_PATH 1u
#define GUARD_PATH_OK 2u
#define GUARD_PATH_NO 3u
#define GUARD_CUSTODY 4u
#define GUARD_CUSTODY_OK 5u
#define GUARD_CUSTODY_NO 6u
#define GUARD_CLONE 7u
#define GUARD_CLONE_OK 8u
#define GUARD_CLONE_NO 9u
#define GUARD_WATCH 10u
#define GUARD_WATCH_OK 11u
#define GUARD_WATCH_NO 12u
#define GUARD_RESULT 13u
#define GUARD_DONE 14u

struct guard_head {
	uint32_t type;
	int32_t pid;
	uint32_t nbytes;
	uint32_t aux;
};

struct admission_guard_ops {
	int (*kill_write)(int dirfd, void *ctx);
	int (*read_populated)(int dirfd, int *out, void *ctx);
	int (*remove_leaf)(void *ctx);
	void *ctx;
};

struct admission_outcome {
	int controller_lost;
	int timed_out;
	int protocol_failed;
	int cleanup_confirmed;
	int custody_held;
	int clone_permits;
	int have_result;
	int custody_fd;
	int controller_exited;
	int controller_exit_code;
	int controller_signaled;
	struct lifetime_receipt receipt;
	pid_t owned_controller;
	pid_t owned_cleanup;
	pid_t owned_verify;
	pid_t owned_watched;
	pid_t unreaped_controller;
	pid_t unreaped_cleanup;
	pid_t unreaped_verify;
	pid_t unreaped_watched;
	int reap_unconfirmed;
	int owned_directory;
	/* Adopted descendants that are not one of the four named roles.
	 * unreaped_adopted keeps identities still alive at the deadline.
	 * adopted_unresolved means the child set was not proven empty.
	 * ECHILD from a specific pid is not that proof.
	 */
	int adopted_unresolved;
	int unreaped_adopted_count;
	pid_t unreaped_adopted[8];
	/* Held open only while that role's termination is unconfirmed.
	 * Callers close these. They are not a license to signal the pid number.
	 */
	int held_cleanup_pidfd;
	int held_verify_pidfd;
	int held_watched_pidfd;
};

static inline void guard_add_ms(struct timespec *ts, uint32_t ms)
{
	ts->tv_sec += (time_t)(ms / 1000u);
	ts->tv_nsec += (long)(ms % 1000u) * 1000000L;
	if (ts->tv_nsec >= 1000000000L) {
		ts->tv_sec += 1;
		ts->tv_nsec -= 1000000000L;
	}
}

/* Positive remaining milliseconds, or -1 when the absolute deadline has passed. */
static inline int guard_remaining_ms(const struct timespec *deadline, int *remain_ms)
{
	struct timespec now;
	int64_t ms;

	if (!deadline || clock_gettime(CLOCK_MONOTONIC, &now) != 0)
		return -1;
	ms = (int64_t)(deadline->tv_sec - now.tv_sec) * 1000 +
		(int64_t)(deadline->tv_nsec - now.tv_nsec) / 1000000;
	if (ms <= 0)
		return -1;
	if (ms > 600000)
		ms = 600000;
	if (remain_ms)
		*remain_ms = (int)ms;
	return 0;
}

int guard_send_simple(int fd, uint32_t type, int32_t pid);
int guard_send_path(int fd, const char *path);
int guard_send_fd(int fd, int fd_to_send);
int guard_send_result(int fd, const struct lifetime_receipt *receipt);
int guard_recv_reply(int fd, const struct timespec *deadline, uint32_t *type_out);

/* Observe this child's exit without reaping it. ECHILD is not an exit status. */
int guard_observe_exit(pid_t pid, int *status, const struct timespec *deadline);
/* pidfd_open, then signal, then close. A pid that cannot be pinned is not signaled. */
int guard_signal_pinned(pid_t pid, int sig);

/* release_fd, when not -1, is written only after the admission timer is armed.
 * The guardian closes it. Production passes the controller's park write end.
 */
int admission_supervise(pid_t controller, int controller_pidfd, int ctrl,
			const struct timespec *admission_deadline, uint32_t cleanup_ms,
			const char *leaf_name, const char *path_prefix, char *accepted_path,
			size_t accepted_cap, const struct admission_guard_ops *ops, int release_fd,
			struct admission_outcome *out);

/* stall_fd and progress_fd are -1 in production. See receipt_publish_supervised. */
int receipt_commit_exclusive(const char *path, const void *buf, size_t len, int stall_fd,
			     int progress_fd);

/* Worker-only lstat. 0 means the worker saw ENOENT and was reaped inside the
 * deadline. -2 means the path was present. -1 is timeout, loss, or any other
 * unconfirmed result. The caller does not lstat or unlink.
 */
int receipt_confirm_absent(const char *path, const struct timespec *deadline, pid_t *unreaped_out);

/* Publish inside the deadline. stall_fd and progress_fd are -1 in production.
 * When stall_fd is open, the worker reads until it sees the phase byte:
 * 'I' before inspection, 'C' before the final link, 'U' before the unnamed
 * temporary is abandoned, 'P' after a successful commit and before exiting.
 * progress_fd, when open, receives that phase byte first. The temporary has
 * no directory name, so a same-uid replacement cannot be unlinked by this
 * path. Timeout, a non-zero exit, or an unreaped worker is a failed
 * invocation even if a file appears. The worker's exit is the publication
 * result. A published final name is left in place. This function does not
 * lstat or unlink; an earlier absence is not authority to remove a path.
 * *unreaped_out is a log identity, not a pid the caller may signal.
 */
int receipt_publish_supervised(const char *path, const void *buf, size_t len,
			       const struct timespec *deadline, int stall_fd, int progress_fd,
			       pid_t *unreaped_out);

#endif
