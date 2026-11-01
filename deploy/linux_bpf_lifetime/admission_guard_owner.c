#define _GNU_SOURCE

/* Bounded owner for one unprivileged command. It does not load BPF or open a
 * cgroup. The child calls setsid so it is not in this process's group. This
 * file never signals a pid or a process-group id. pidfd_open(2) after fork,
 * before any reap, still refers to that child even if it is already a zombie.
 */

#include "admission_guard_owner.h"

#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/signalfd.h>
#include <sys/syscall.h>
#include <sys/timerfd.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#ifndef __NR_pidfd_open
#define __NR_pidfd_open 434
#endif
#ifndef __NR_pidfd_send_signal
#define __NR_pidfd_send_signal 424
#endif

#define OWNER_RUN_MAX_MS 120000u
#define OWNER_CLEANUP_MAX_MS 30000u

static int pidfd_open_child(pid_t pid)
{
	return (int)syscall(__NR_pidfd_open, pid, 0);
}

static int pidfd_kill(int pidfd)
{
	if (pidfd < 0)
		return -1;
	return (int)syscall(__NR_pidfd_send_signal, pidfd, SIGKILL, NULL, 0);
}

static void add_ms(struct timespec *ts, uint32_t ms)
{
	ts->tv_sec += (time_t)(ms / 1000u);
	ts->tv_nsec += (long)(ms % 1000u) * 1000000L;
	if (ts->tv_nsec >= 1000000000L) {
		ts->tv_sec += 1;
		ts->tv_nsec -= 1000000000L;
	}
}

/* -1 when the absolute deadline has passed or the clock cannot be read. */
static int remain_ms(const struct timespec *deadline)
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
	return (int)ms;
}

static int arm_absolute(int tfd, const struct timespec *when)
{
	struct itimerspec spec;

	memset(&spec, 0, sizeof spec);
	spec.it_value = *when;
	if (spec.it_value.tv_sec == 0 && spec.it_value.tv_nsec == 0)
		spec.it_value.tv_nsec = 1;
	return timerfd_settime(tfd, TFD_TIMER_ABSTIME, &spec, NULL);
}

/* One read on a nonblocking timerfd. Eight bytes and a nonzero expiration
 * count are the consumed coalesced count. EAGAIN, EINTR, a short or empty
 * read, and any other error are not a consumed expiration and are not
 * retried. Callers still keep the timeout they already took from poll or
 * from the absolute deadline.
 */
static void consume_timer(int tfd)
{
	uint64_t ticks = 0;
	ssize_t n;

	if (tfd < 0)
		return;
	n = read(tfd, &ticks, sizeof ticks);
	if (n == (ssize_t)sizeof ticks && ticks > 0)
		return;
	if (n < 0 && (errno == EINTR || errno == EAGAIN))
		return;
	/* Short, empty, or another errno. The read did not return an expiration. */
	return;
}

/* One read on a nonblocking signalfd. A full signalfd_siginfo with a signal
 * number is one consumed signal. EAGAIN, EINTR, a short or empty read, and
 * any other error are not a consumed signal and are not retried. Callers
 * still keep the interruption they already took from poll.
 */
static void consume_signal(int sfd)
{
	struct signalfd_siginfo info = {0};
	ssize_t n;

	if (sfd < 0)
		return;
	n = read(sfd, &info, sizeof info);
	if (n == (ssize_t)sizeof info && info.ssi_signo != 0)
		return;
	if (n < 0 && (errno == EINTR || errno == EAGAIN))
		return;
	/* Short, empty, or another errno. The read did not return a signal. */
	return;
}

static void note_child_status(struct external_owner_result *out, int status)
{
	if (WIFEXITED(status)) {
		out->child_exited = 1;
		out->child_exit_code = WEXITSTATUS(status);
		out->child_signaled = 0;
		out->child_term_signal = 0;
		return;
	}
	if (WIFSIGNALED(status)) {
		out->child_exited = 0;
		out->child_exit_code = -1;
		out->child_signaled = 1;
		out->child_term_signal = WTERMSIG(status);
	}
}

static int reap_pid(pid_t pid, int *status_out)
{
	int status = 0;
	pid_t got;

	if (pid <= 0)
		return 0;
	got = waitpid(pid, &status, WNOHANG);
	if (got != pid)
		return 0;
	if (status_out)
		*status_out = status;
	return 1;
}

static int child_ppid_is_us(pid_t pid)
{
	char path[64];
	char buf[512];
	char *line;
	int fd;
	int n;

	if (snprintf(path, sizeof path, "/proc/%d/status", (int)pid) >= (int)sizeof path)
		return 0;
	fd = open(path, O_RDONLY | O_CLOEXEC);
	if (fd < 0)
		return 0;
	n = (int)read(fd, buf, sizeof buf - 1);
	close(fd);
	if (n <= 0)
		return 0;
	buf[n] = 0;
	line = buf;
	for (;;) {
		char *next = strchr(line, '\n');
		long ppid;
		char *end = NULL;

		if (next)
			*next = 0;
		if (strncmp(line, "PPid:", 5) == 0) {
			ppid = strtol(line + 5, &end, 10);
			return end != line + 5 && ppid == (long)getpid();
		}
		if (!next)
			return 0;
		line = next + 1;
	}
}

/* Hint only. An empty or short read does not prove that no child remains.
 * waitpid(-1) returning ECHILD is that proof.
 */
static int read_child_tids(pid_t *ids, int cap, int *truncated)
{
	char path[80];
	char buf[256];
	char *cursor;
	int fd;
	int n;
	int count = 0;

	*truncated = 0;
	if (snprintf(path, sizeof path, "/proc/%d/task/%d/children", (int)getpid(), (int)getpid()) >=
	    (int)sizeof path)
		return -1;
	fd = open(path, O_RDONLY | O_CLOEXEC);
	if (fd < 0)
		return -1;
	n = (int)read(fd, buf, sizeof buf - 1);
	close(fd);
	if (n < 0)
		return -1;
	if (n == (int)sizeof buf - 1)
		*truncated = 1;
	buf[n] = 0;
	cursor = buf;
	while (*cursor) {
		char *end = NULL;
		long value = strtol(cursor, &end, 10);

		if (end == cursor)
			break;
		if (value > 0) {
			if (count >= cap)
				*truncated = 1;
			else
				ids[count++] = (pid_t)value;
		}
		cursor = end;
	}
	return count;
}

/* Signal adopted children through a pidfd opened while they remain our child.
 * The direct child is not signalled here; its pidfd is the one taken at fork.
 */
static void signal_adopted(pid_t direct, int *unresolved)
{
	pid_t ids[16];
	int truncated = 0;
	int n;
	int i;

	n = read_child_tids(ids, 16, &truncated);
	if (n < 0 || truncated) {
		*unresolved = 1;
		if (n < 0)
			return;
	}
	for (i = 0; i < n; i++) {
		int pinned;

		if (ids[i] == direct)
			continue;
		pinned = pidfd_open_child(ids[i]);
		if (pinned < 0) {
			/* ESRCH means that pid is already gone. Do not signal it. */
			if (errno != ESRCH)
				*unresolved = 1;
			continue;
		}
		if (!child_ppid_is_us(ids[i])) {
			close(pinned);
			continue;
		}
		(void)pidfd_kill(pinned);
		close(pinned);
	}
}

static int no_children(void)
{
	int status = 0;
	pid_t got = waitpid(-1, &status, WNOHANG);

	if (got > 0)
		return 0;
	if (got < 0 && errno == ECHILD)
		return 1;
	if (got < 0 && errno == EINTR)
		return 0;
	return 0;
}

int external_owner_run(const struct external_owner_spec *spec, struct external_owner_result *out)
{
	sigset_t block;
	sigset_t saved;
	struct timespec run_deadline;
	struct timespec cleanup_deadline;
	int previous_subreaper = 0;
	int have_saved_mask = 0;
	int have_subreaper = 0;
	int sfd = -1;
	int run_tfd = -1;
	int cleanup_tfd = -1;
	int pidfd = -1;
	pid_t child = -1;
	int child_reaped = 0;

	if (!out)
		return -1;
	memset(out, 0, sizeof *out);
	out->child_exit_code = -1;
	if (!spec || !spec->argv || !spec->argv[0] || spec->run_ms == 0 || spec->run_ms > OWNER_RUN_MAX_MS ||
	    spec->cleanup_ms == 0 || spec->cleanup_ms > OWNER_CLEANUP_MAX_MS)
		return -1;
	sigemptyset(&block);
	sigaddset(&block, SIGINT);
	sigaddset(&block, SIGTERM);
	sigaddset(&block, SIGHUP);
	if (sigprocmask(SIG_BLOCK, &block, &saved) != 0)
		return -1;
	have_saved_mask = 1;
	sfd = signalfd(-1, &block, SFD_CLOEXEC | SFD_NONBLOCK);
	if (sfd < 0)
		goto finish;
	if (prctl(PR_GET_CHILD_SUBREAPER, &previous_subreaper, 0, 0, 0) != 0 ||
	    prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0)
		goto finish;
	have_subreaper = 1;
	if (clock_gettime(CLOCK_MONOTONIC, &run_deadline) != 0)
		goto finish;
	add_ms(&run_deadline, spec->run_ms);
	run_tfd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC | TFD_NONBLOCK);
	if (run_tfd < 0 || arm_absolute(run_tfd, &run_deadline) != 0)
		goto finish;
	child = fork();
	if (child < 0)
		goto finish;
	if (child == 0) {
		if (sfd >= 0)
			close(sfd);
		if (run_tfd >= 0)
			close(run_tfd);
		if (sigprocmask(SIG_SETMASK, &saved, NULL) != 0)
			_exit(127);
		if (setsid() < 0)
			_exit(127);
		execv(spec->argv[0], (char *const *)spec->argv);
		_exit(127);
	}
	out->started = 1;
	pidfd = pidfd_open_child(child);
	if (pidfd < 0)
		out->ownership_unresolved = 1;
	for (;;) {
		struct pollfd pfds[3];
		int remain;
		int nfds = 0;
		int rc;
		int timer_slot = -1;
		int signal_slot = -1;
		int child_slot = -1;

		if (out->timed_out || out->interrupted || child_reaped)
			break;
		if (pidfd < 0 && !child_reaped) {
			int status = 0;

			if (reap_pid(child, &status)) {
				note_child_status(out, status);
				child_reaped = 1;
				break;
			}
		}
		remain = remain_ms(&run_deadline);
		if (remain < 0) {
			out->timed_out = 1;
			break;
		}
		pfds[nfds].fd = run_tfd;
		pfds[nfds].events = POLLIN;
		timer_slot = nfds++;
		pfds[nfds].fd = sfd;
		pfds[nfds].events = POLLIN;
		signal_slot = nfds++;
		if (pidfd >= 0) {
			pfds[nfds].fd = pidfd;
			pfds[nfds].events = POLLIN;
			child_slot = nfds++;
		}
		rc = poll(pfds, (nfds_t)nfds, remain);
		if (rc < 0 && errno == EINTR)
			continue;
		if (rc < 0) {
			out->ownership_unresolved = 1;
			break;
		}
		if (rc == 0 || (pfds[timer_slot].revents & POLLIN)) {
			consume_timer(run_tfd);
			out->timed_out = 1;
		}
		if (pfds[signal_slot].revents & POLLIN) {
			consume_signal(sfd);
			out->interrupted = 1;
		}
		if (child_slot >= 0 && (pfds[child_slot].revents & POLLIN)) {
			int status = 0;

			if (reap_pid(child, &status)) {
				note_child_status(out, status);
				child_reaped = 1;
			}
		}
	}
	if (clock_gettime(CLOCK_MONOTONIC, &cleanup_deadline) != 0) {
		out->ownership_unresolved = 1;
		if (!child_reaped && pidfd >= 0)
			(void)pidfd_kill(pidfd);
		goto finish;
	}
	add_ms(&cleanup_deadline, spec->cleanup_ms);
	cleanup_tfd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC | TFD_NONBLOCK);
	if (cleanup_tfd < 0 || arm_absolute(cleanup_tfd, &cleanup_deadline) != 0) {
		out->ownership_unresolved = 1;
		if (!child_reaped && pidfd >= 0)
			(void)pidfd_kill(pidfd);
		if (!child_reaped) {
			int status = 0;

			if (reap_pid(child, &status)) {
				note_child_status(out, status);
				child_reaped = 1;
			}
		}
		goto finish;
	}
	if (!child_reaped && pidfd >= 0)
		(void)pidfd_kill(pidfd);
	/* Same cap as the adopted-child hint read. One WNOHANG call does not
	 * bound this loop. Each pass checks the absolute deadline, reaps at
	 * most that many exited children, then signals adopted live children.
	 * EINTR retries land on the deadline check. Expiry is unconfirmed.
	 * waitpid stays WNOHANG. ECHILD from no_children is the empty proof.
	 */
	for (;;) {
		int remain = remain_ms(&cleanup_deadline);
		int status = 0;
		int batch_reaped = 0;
		int expired = 0;
		int empty_children = 0;
		pid_t got;

		if (remain < 0) {
			out->ownership_unresolved = 1;
			out->cleanup_confirmed = 0;
			break;
		}
		if (!child_reaped && reap_pid(child, &status)) {
			note_child_status(out, status);
			child_reaped = 1;
		}
		while (batch_reaped < 16) {
			if (remain_ms(&cleanup_deadline) < 0) {
				expired = 1;
				break;
			}
			status = 0;
			got = waitpid(-1, &status, WNOHANG);
			if (got < 0 && errno == EINTR)
				continue;
			if (got <= 0)
				break;
			batch_reaped++;
			if (got == child && !child_reaped) {
				note_child_status(out, status);
				child_reaped = 1;
			}
		}
		if (expired || remain_ms(&cleanup_deadline) < 0) {
			out->ownership_unresolved = 1;
			out->cleanup_confirmed = 0;
			break;
		}
		if (child_reaped)
			signal_adopted(child, &out->ownership_unresolved);
		/* Record ECHILD before confirmation. The check below is the existing
		 * expiry path. Success is assigned only when that absolute monotonic
		 * deadline is still readable and ahead. An expired deadline does not
		 * prove that stuck kernel work was reaped.
		 */
		if (child_reaped && !out->ownership_unresolved && no_children())
			empty_children = 1;
		remain = remain_ms(&cleanup_deadline);
		if (remain < 0) {
			out->ownership_unresolved = 1;
			out->cleanup_confirmed = 0;
			break;
		}
		if (empty_children) {
			out->cleanup_confirmed = 1;
			break;
		}
		{
			struct pollfd pfd;
			int rc;

			pfd.fd = cleanup_tfd;
			pfd.events = POLLIN;
			rc = poll(&pfd, 1, remain > 20 ? 20 : remain);
			if (rc < 0 && errno == EINTR)
				continue;
			if (rc < 0) {
				out->ownership_unresolved = 1;
				break;
			}
			if (rc == 0)
				continue;
			if (pfd.revents & POLLIN) {
				consume_timer(cleanup_tfd);
				out->ownership_unresolved = 1;
				break;
			}
		}
	}
	if (!child_reaped || out->ownership_unresolved)
		out->cleanup_confirmed = 0;
finish:
	if (pidfd >= 0)
		close(pidfd);
	if (cleanup_tfd >= 0)
		close(cleanup_tfd);
	if (run_tfd >= 0)
		close(run_tfd);
	if (sfd >= 0)
		close(sfd);
	if (have_subreaper)
		(void)prctl(PR_SET_CHILD_SUBREAPER, previous_subreaper, 0, 0, 0);
	if (have_saved_mask)
		(void)sigprocmask(SIG_SETMASK, &saved, NULL);
	if (!out->started && !out->ownership_unresolved && !out->timed_out && !out->interrupted)
		return -1;
	return 0;
}

#ifndef EXTERNAL_OWNER_LIB
static int parse_u32(const char *text, uint32_t max_value, uint32_t *out)
{
	char *end = NULL;
	unsigned long value;

	if (!text || !text[0] || !out)
		return -1;
	errno = 0;
	value = strtoul(text, &end, 10);
	if (end == text || *end || errno || value == 0 || value > max_value)
		return -1;
	*out = (uint32_t)value;
	return 0;
}

static int write_all(int fd, const char *buf, size_t len)
{
	size_t off = 0;

	while (off < len) {
		ssize_t n = write(fd, buf + off, len - off);

		if (n < 0 && errno == EINTR)
			continue;
		if (n <= 0)
			return -1;
		off += (size_t)n;
	}
	return 0;
}

/* 0 only when path was exclusively created, fully written, and closed.
 * An existing final component is left in place. A partial file this call
 * created is unlinked so it is not a current record. Unlink failure still
 * returns -1 and does not change the child result fields.
 */
static int publish_status(const char *path, const struct external_owner_result *out)
{
	char body[512];
	int len;
	int fd;
	int saved;

	len = snprintf(body, sizeof body,
		       "child_exited=%d\n"
		       "child_exit_code=%d\n"
		       "child_signaled=%d\n"
		       "child_term_signal=%d\n"
		       "timed_out=%d\n"
		       "interrupted=%d\n"
		       "cleanup_confirmed=%d\n"
		       "ownership_unresolved=%d\n",
		       out->child_exited, out->child_exit_code, out->child_signaled, out->child_term_signal,
		       out->timed_out, out->interrupted, out->cleanup_confirmed, out->ownership_unresolved);
	if (len < 0 || (size_t)len >= sizeof body) {
		errno = EMSGSIZE;
		return -1;
	}
	fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0644);
	if (fd < 0)
		return -1;
	if (write_all(fd, body, (size_t)len) != 0) {
		saved = errno;
		(void)close(fd);
		(void)unlink(path);
		errno = saved;
		return -1;
	}
	if (close(fd) != 0) {
		saved = errno;
		(void)unlink(path);
		errno = saved;
		return -1;
	}
	return 0;
}

static void report_publication_failure(const struct external_owner_result *out, int child_result, int err)
{
	char body[640];
	int len;

	len = snprintf(body, sizeof body,
		       "owner_status_publication=failed\n"
		       "owner_status_errno=%d\n"
		       "child_exited=%d\n"
		       "child_exit_code=%d\n"
		       "child_signaled=%d\n"
		       "child_term_signal=%d\n"
		       "timed_out=%d\n"
		       "interrupted=%d\n"
		       "cleanup_confirmed=%d\n"
		       "ownership_unresolved=%d\n"
		       "owner_child_result=%d\n",
		       err, out->child_exited, out->child_exit_code, out->child_signaled, out->child_term_signal,
		       out->timed_out, out->interrupted, out->cleanup_confirmed, out->ownership_unresolved,
		       child_result);
	if (len > 0 && (size_t)len < sizeof body)
		(void)write_all(STDERR_FILENO, body, (size_t)len);
}

/* Starts no child. Exit 0 means only that this path was published.
 * It is not a guard result. Neither workflow lane selects this entry.
 */
static int publish_status_fixture(const char *path)
{
	struct external_owner_result sample;
	int saved;

	memset(&sample, 0, sizeof sample);
	sample.started = 1;
	sample.child_exited = 1;
	sample.child_exit_code = 0;
	sample.cleanup_confirmed = 0;
	if (publish_status(path, &sample) != 0) {
		saved = errno;
		report_publication_failure(&sample, 0, saved);
		return 1;
	}
	return 0;
}

static int owner_exit_code(const struct external_owner_result *out)
{
	if (!out->started || out->timed_out || out->interrupted || !out->cleanup_confirmed ||
	    out->ownership_unresolved)
		return 1;
	if (out->child_signaled)
		return 1;
	if (!out->child_exited)
		return 1;
	return out->child_exit_code == 0 ? 0 : out->child_exit_code;
}

static void usage(void)
{
	dprintf(STDERR_FILENO,
		"usage: admission_guard_owner --run-ms N --cleanup-ms N --status PATH -- command [args]\n"
		"       admission_guard_owner --status-fixture --status PATH\n");
}

int main(int argc, char **argv)
{
	const char *status_path = NULL;
	uint32_t run_ms = 0;
	uint32_t cleanup_ms = 0;
	int sep = -1;
	int status_fixture = 0;
	int i;
	int child_result;
	int saved;
	struct external_owner_spec spec;
	struct external_owner_result result;

	for (i = 1; i < argc; i++) {
		if (strcmp(argv[i], "--") == 0) {
			sep = i;
			break;
		}
		if (strcmp(argv[i], "--run-ms") == 0 && i + 1 < argc) {
			if (parse_u32(argv[++i], OWNER_RUN_MAX_MS, &run_ms) != 0)
				return 2;
		} else if (strcmp(argv[i], "--cleanup-ms") == 0 && i + 1 < argc) {
			if (parse_u32(argv[++i], OWNER_CLEANUP_MAX_MS, &cleanup_ms) != 0)
				return 2;
		} else if (strcmp(argv[i], "--status") == 0 && i + 1 < argc) {
			status_path = argv[++i];
		} else if (strcmp(argv[i], "--status-fixture") == 0) {
			status_fixture = 1;
		} else {
			usage();
			return 2;
		}
	}
	if (status_fixture) {
		if (sep >= 0 || run_ms != 0 || cleanup_ms != 0 || !status_path || !status_path[0]) {
			usage();
			return 2;
		}
		return publish_status_fixture(status_path);
	}
	if (sep < 0 || sep + 1 >= argc || !status_path || !status_path[0] || run_ms == 0 || cleanup_ms == 0) {
		usage();
		return 2;
	}
	memset(&spec, 0, sizeof spec);
	spec.argv = &argv[sep + 1];
	spec.run_ms = run_ms;
	spec.cleanup_ms = cleanup_ms;
	memset(&result, 0, sizeof result);
	if (external_owner_run(&spec, &result) != 0)
		result.ownership_unresolved = 1;
	child_result = owner_exit_code(&result);
	if (publish_status(status_path, &result) != 0) {
		saved = errno;
		report_publication_failure(&result, child_result, saved);
		return child_result == 0 ? 1 : child_result;
	}
	return child_result;
}
#endif
