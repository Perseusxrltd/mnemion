#define _GNU_SOURCE

#include "admission_guard.h"

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/timerfd.h>
#include <sys/wait.h>
#include <unistd.h>

#ifndef MSG_CMSG_CLOEXEC
#define MSG_CMSG_CLOEXEC 0x40000000
#endif

static int send_all_msg(int fd, const void *buf, size_t len, int send_fd)
{
	char control[CMSG_SPACE(sizeof(int))];
	struct msghdr msg;
	struct iovec iov;
	struct cmsghdr *cmsg;

	memset(&msg, 0, sizeof msg);
	iov.iov_base = (void *)buf;
	iov.iov_len = len;
	msg.msg_iov = &iov;
	msg.msg_iovlen = 1;
	if (send_fd >= 0) {
		memset(control, 0, sizeof control);
		msg.msg_control = control;
		msg.msg_controllen = sizeof control;
		cmsg = CMSG_FIRSTHDR(&msg);
		cmsg->cmsg_level = SOL_SOCKET;
		cmsg->cmsg_type = SCM_RIGHTS;
		cmsg->cmsg_len = CMSG_LEN(sizeof(int));
		memcpy(CMSG_DATA(cmsg), &send_fd, sizeof(int));
	}
	for (;;) {
		ssize_t n = sendmsg(fd, &msg, MSG_NOSIGNAL);
		if (n < 0 && errno == EINTR)
			continue;
		return n == (ssize_t)len ? 0 : -1;
	}
}

/* Guardian replies only. A blocked send cannot extend the deadline. */
static int send_until(int fd, const void *buf, size_t len, int send_fd, const struct timespec *deadline)
{
	char control[CMSG_SPACE(sizeof(int))];
	struct msghdr msg;
	struct iovec iov;
	struct cmsghdr *cmsg;

	if (fd < 0 || !deadline)
		return -1;
	memset(&msg, 0, sizeof msg);
	iov.iov_base = (void *)buf;
	iov.iov_len = len;
	msg.msg_iov = &iov;
	msg.msg_iovlen = 1;
	if (send_fd >= 0) {
		memset(control, 0, sizeof control);
		msg.msg_control = control;
		msg.msg_controllen = sizeof control;
		cmsg = CMSG_FIRSTHDR(&msg);
		cmsg->cmsg_level = SOL_SOCKET;
		cmsg->cmsg_type = SCM_RIGHTS;
		cmsg->cmsg_len = CMSG_LEN(sizeof(int));
		memcpy(CMSG_DATA(cmsg), &send_fd, sizeof(int));
	}
	for (;;) {
		int remain = 0;
		struct pollfd pfd;
		int rc;
		ssize_t n;

		if (guard_remaining_ms(deadline, &remain) != 0)
			return -1;
		pfd.fd = fd;
		pfd.events = POLLOUT;
		rc = poll(&pfd, 1, remain);
		if (rc < 0) {
			if (errno == EINTR)
				continue;
			return -1;
		}
		if (rc == 0)
			return -1;
		n = sendmsg(fd, &msg, MSG_NOSIGNAL | MSG_DONTWAIT);
		if (n < 0 && (errno == EINTR || errno == EAGAIN))
			continue;
		return n == (ssize_t)len ? 0 : -1;
	}
}

static int reply_simple(int fd, uint32_t type, const struct timespec *deadline)
{
	struct guard_head head;

	memset(&head, 0, sizeof head);
	head.type = type;
	return send_until(fd, &head, sizeof head, -1, deadline);
}

static int set_nonblock(int fd)
{
	int flags = fcntl(fd, F_GETFL);

	if (flags < 0)
		return -1;
	if (flags & O_NONBLOCK)
		return 0;
	return fcntl(fd, F_SETFL, flags | O_NONBLOCK);
}

static void close_received_fds(struct msghdr *msg)
{
	struct cmsghdr *cmsg;

	for (cmsg = CMSG_FIRSTHDR(msg); cmsg; cmsg = CMSG_NXTHDR(msg, cmsg)) {
		int fd;
		if (cmsg->cmsg_level != SOL_SOCKET || cmsg->cmsg_type != SCM_RIGHTS)
			continue;
		if (cmsg->cmsg_len < CMSG_LEN(sizeof(int)))
			continue;
		memcpy(&fd, CMSG_DATA(cmsg), sizeof fd);
		if (fd >= 0)
			close(fd);
	}
}

int guard_send_simple(int fd, uint32_t type, int32_t pid)
{
	struct guard_head head;

	memset(&head, 0, sizeof head);
	head.type = type;
	head.pid = pid;
	return send_all_msg(fd, &head, sizeof head, -1);
}

int guard_send_path(int fd, const char *path)
{
	char buf[sizeof(struct guard_head) + PATH_MAX];
	struct guard_head *head = (struct guard_head *)buf;
	size_t len;

	if (!path)
		return -1;
	len = strlen(path);
	if (len == 0 || len + 1 > PATH_MAX)
		return -1;
	memset(buf, 0, sizeof(struct guard_head));
	head->type = GUARD_PATH;
	head->nbytes = (uint32_t)len + 1;
	memcpy(buf + sizeof *head, path, len + 1);
	return send_all_msg(fd, buf, sizeof *head + len + 1, -1);
}

int guard_send_fd(int fd, int fd_to_send)
{
	struct guard_head head;

	if (fd_to_send < 0)
		return -1;
	memset(&head, 0, sizeof head);
	head.type = GUARD_CUSTODY;
	return send_all_msg(fd, &head, sizeof head, fd_to_send);
}

int guard_send_result(int fd, const struct lifetime_receipt *receipt)
{
	char buf[sizeof(struct guard_head) + sizeof(struct lifetime_receipt)];
	struct guard_head *head = (struct guard_head *)buf;

	if (!receipt)
		return -1;
	memset(head, 0, sizeof *head);
	head->type = GUARD_RESULT;
	head->nbytes = (uint32_t)sizeof(*receipt);
	memcpy(buf + sizeof *head, receipt, sizeof(*receipt));
	return send_all_msg(fd, buf, sizeof *head + sizeof(*receipt), -1);
}

int guard_recv_reply(int fd, const struct timespec *deadline, uint32_t *type_out)
{
	struct guard_head head;

	for (;;) {
		int remain = 0;
		struct pollfd pfd;
		int rc;
		ssize_t n;

		if (guard_remaining_ms(deadline, &remain) != 0)
			return -1;
		pfd.fd = fd;
		pfd.events = POLLIN;
		rc = poll(&pfd, 1, remain);
		if (rc < 0) {
			if (errno == EINTR)
				continue;
			return -1;
		}
		if (rc == 0)
			return -1;
		n = recv(fd, &head, sizeof head, 0);
		if (n < 0 && errno == EINTR)
			continue;
		if (n != (ssize_t)sizeof head)
			return -1;
		if (type_out)
			*type_out = head.type;
		return 0;
	}
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

static int consume_timer(int tfd)
{
	uint64_t ticks = 0;
	ssize_t n = read(tfd, &ticks, sizeof ticks);

	if (n < 0 && (errno == EINTR || errno == EAGAIN))
		return 0;
	return n == (ssize_t)sizeof ticks ? 0 : -1;
}

static int timespec_after(const struct timespec *a, const struct timespec *b)
{
	return a->tv_sec > b->tv_sec || (a->tv_sec == b->tv_sec && a->tv_nsec > b->tv_nsec);
}

static int path_matches_leaf(const char *path, const char *prefix, const char *leaf)
{
	const char *slash;
	size_t i;

	if (!path || !prefix || !leaf || !path[0] || !leaf[0])
		return 0;
	if (strncmp(path, prefix, strlen(prefix)) != 0)
		return 0;
	if (path[strlen(prefix)] != '/')
		return 0;
	if (path[strlen(path) - 1] == '/')
		return 0;
	if (strstr(path, "..") || strstr(path, "//") || strstr(path, "(deleted)"))
		return 0;
	for (i = 0; path[i]; i++) {
		unsigned char ch = (unsigned char)path[i];
		if (ch <= ' ' || ch == '\\' || ch >= 0x7f)
			return 0;
	}
	slash = strrchr(path, '/');
	if (!slash || strcmp(slash + 1, leaf) != 0)
		return 0;
	return 1;
}

/* Same numbers on x86_64 and aarch64. glibc 2.35 does not always wrap them. */
#ifndef __NR_pidfd_open
#define __NR_pidfd_open 434
#endif
#ifndef __NR_pidfd_send_signal
#define __NR_pidfd_send_signal 424
#endif

static int open_pidfd(pid_t pid)
{
	return (int)syscall(__NR_pidfd_open, pid, 0);
}

static int signal_pidfd(int pidfd, int sig)
{
	if (pidfd < 0)
		return -1;
	return (int)syscall(__NR_pidfd_send_signal, pidfd, sig, NULL, 0);
}

int guard_signal_pinned(pid_t pid, int sig)
{
	int pidfd;
	int rc;

	if (pid <= 0)
		return -1;
	pidfd = open_pidfd(pid);
	if (pidfd < 0)
		return -1;
	rc = signal_pidfd(pidfd, sig);
	close(pidfd);
	return rc == 0 ? 0 : -1;
}

/* WNOWAIT leaves the zombie for the reaping owner. ECHILD means this pid is
 * not our child, or is already gone. That is not an exit status.
 */
int guard_observe_exit(pid_t pid, int *status_out, const struct timespec *deadline)
{
	if (pid <= 0 || !deadline)
		return -1;
	for (;;) {
		siginfo_t info;
		int remain = 0;

		memset(&info, 0, sizeof info);
		if (waitid(P_PID, (id_t)pid, &info, WEXITED | WNOHANG | WNOWAIT) != 0) {
			if (errno == EINTR)
				continue;
			return -1;
		}
		if (info.si_pid == pid) {
			int status;

			if (info.si_code == CLD_EXITED)
				status = (info.si_status & 0xff) << 8;
			else if (info.si_code == CLD_KILLED || info.si_code == CLD_DUMPED)
				status = info.si_status & 0x7f;
			else
				return -1;
			if (status_out)
				*status_out = status;
			return 0;
		}
		if (guard_remaining_ms(deadline, &remain) != 0)
			return -1;
		if (poll(NULL, 0, remain > 20 ? 20 : remain) < 0 && errno != EINTR)
			return -1;
	}
}

/* Returns 1 when this exact child was reaped. Never blocks. */
static int reap_nowait(pid_t pid, int *status_out)
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

static int verify_custody(int dirfd, const char *path)
{
	char proc[64];
	char link[PATH_MAX];
	ssize_t n;
	struct stat st;

	if (dirfd < 0 || !path || !path[0])
		_exit(2);
	if (snprintf(proc, sizeof proc, "/proc/self/fd/%d", dirfd) >= (int)sizeof proc)
		_exit(2);
	n = readlink(proc, link, sizeof link - 1);
	if (n <= 0 || (size_t)n >= sizeof link - 1)
		_exit(2);
	link[n] = 0;
	if (strcmp(link, path) != 0)
		_exit(2);
	if (fstat(dirfd, &st) != 0 || !S_ISDIR(st.st_mode))
		_exit(2);
	_exit(0);
}

/* owned_fd is a verified directory descriptor. This process does not open a
 * path by name, and populated==0 does not mean the outside observer exited.
 */
static int cleanup_worker(int owned_fd, int report, int ack, const struct admission_guard_ops *ops)
{
	char ready = '1';
	char go = 0;

	if (owned_fd < 0)
		_exit(3);
	if (!ops || !ops->kill_write || !ops->read_populated || !ops->remove_leaf)
		_exit(2);
	if (ops->kill_write(owned_fd, ops->ctx) != 0)
		_exit(2);
	for (;;) {
		int populated = -1;
		if (ops->read_populated(owned_fd, &populated, ops->ctx) == 0 && populated == 0)
			break;
		if (poll(NULL, 0, 20) < 0 && errno != EINTR)
			_exit(2);
	}
	close(owned_fd);
	if (write(report, &ready, 1) != 1)
		_exit(2);
	if (read(ack, &go, 1) != 1)
		_exit(2);
	if (ops->remove_leaf(ops->ctx) != 0)
		_exit(2);
	_exit(0);
}

static void note_status(struct admission_outcome *out, pid_t pid, pid_t controller, int status,
			int *controller_reaped, int *cleanup_status, int *have_cleanup_status,
			pid_t cleanup_pid, int *verify_status, int *have_verify_status, pid_t verify_pid)
{
	if (pid == controller) {
		*controller_reaped = 1;
		out->controller_exited = WIFEXITED(status) ? 1 : 0;
		out->controller_exit_code = WIFEXITED(status) ? WEXITSTATUS(status) : -1;
		out->controller_signaled = WIFSIGNALED(status) ? 1 : 0;
		if (!(WIFEXITED(status) && out->have_result && !out->timed_out))
			out->controller_lost = 1;
		if (WIFSIGNALED(status))
			out->controller_lost = 1;
		return;
	}
	if (cleanup_pid > 0 && pid == cleanup_pid) {
		*have_cleanup_status = 1;
		*cleanup_status = status;
		return;
	}
	if (verify_pid > 0 && pid == verify_pid) {
		*have_verify_status = 1;
		*verify_status = status;
	}
}

static void note_pid(const char *name, pid_t pid)
{
	if (pid > 0)
		dprintf(STDERR_FILENO, "admission_guard: %s=%d\n", name, (int)pid);
}

static void apply_verify_exit(struct admission_outcome *out, int status, int cleanup_started, int ctrl,
			      const struct timespec *active, int *pending_fd, pid_t *verify_pid,
			      int *verify_pidfd, int *verify_for, int *verify_reaped, int *owned_directory)
{
	int ok = WIFEXITED(status) && WEXITSTATUS(status) == 0 && !out->timed_out && !cleanup_started;

	*verify_reaped = 1;
	if (*verify_pidfd >= 0)
		close(*verify_pidfd);
	*verify_pidfd = -1;
	*verify_pid = -1;
	if (*verify_for == (int)GUARD_CUSTODY) {
		if (ok && *pending_fd >= 0) {
			out->custody_fd = *pending_fd;
			*pending_fd = -1;
			out->custody_held = 1;
			*owned_directory = 1;
			out->owned_directory = 1;
			if (reply_simple(ctrl, GUARD_CUSTODY_OK, active) != 0)
				out->protocol_failed = 1;
		} else {
			if (*pending_fd >= 0)
				close(*pending_fd);
			*pending_fd = -1;
			out->custody_fd = -1;
			out->custody_held = 0;
			*owned_directory = 0;
			if (reply_simple(ctrl, GUARD_CUSTODY_NO, active) != 0)
				out->protocol_failed = 1;
		}
	} else if (*verify_for == (int)GUARD_CLONE) {
		if (ok && out->custody_held && out->clone_permits == 0) {
			out->clone_permits = 1;
			if (reply_simple(ctrl, GUARD_CLONE_OK, active) != 0)
				out->protocol_failed = 1;
		} else if (reply_simple(ctrl, GUARD_CLONE_NO, active) != 0) {
			out->protocol_failed = 1;
		}
	}
	*verify_for = 0;
}

struct guard_reap {
	struct admission_outcome *out;
	pid_t controller;
	pid_t *verify_pid;
	int *verify_pidfd;
	int *verify_for;
	int *verify_reaped;
	pid_t *saw_verify;
	pid_t *cleanup_pid;
	int *have_cleanup_status;
	int *cleanup_status;
	pid_t *saw_cleanup;
	pid_t *collector_pid;
	int *watched_reaped;
	pid_t *saw_watched;
	int *controller_reaped;
	int *controller_status;
	int *cleanup_started;
	int *pending_fd;
	int *ctrl;
	int *owned_directory;
	const struct timespec *admission_deadline;
	struct timespec *cleanup_deadline;
};

static int reap_is_named(const struct guard_reap *g, pid_t pid)
{
	if (pid <= 0)
		return 0;
	if (pid == g->controller || pid == *g->saw_verify || pid == *g->saw_cleanup || pid == *g->saw_watched)
		return 1;
	if (*g->verify_pid > 0 && pid == *g->verify_pid)
		return 1;
	if (*g->cleanup_pid > 0 && pid == *g->cleanup_pid)
		return 1;
	if (*g->collector_pid > 0 && pid == *g->collector_pid)
		return 1;
	return 0;
}

static void account_wait_status(struct guard_reap *g, pid_t pid, int status)
{
	if (pid == g->controller) {
		*g->controller_status = status;
		note_status(g->out, pid, g->controller, status, g->controller_reaped, g->cleanup_status,
			    g->have_cleanup_status, *g->cleanup_pid, NULL, NULL, -1);
		return;
	}
	if ((*g->saw_verify > 0 && pid == *g->saw_verify) || (*g->verify_pid > 0 && pid == *g->verify_pid)) {
		if (!*g->verify_reaped) {
			const struct timespec *active =
				*g->cleanup_started ? g->cleanup_deadline : g->admission_deadline;
			if (*g->verify_for == (int)GUARD_CUSTODY || *g->verify_for == (int)GUARD_CLONE)
				apply_verify_exit(g->out, status, *g->cleanup_started, *g->ctrl, active, g->pending_fd,
						  g->verify_pid, g->verify_pidfd, g->verify_for, g->verify_reaped,
						  g->owned_directory);
			else {
				*g->verify_reaped = 1;
				*g->verify_pid = -1;
			}
		}
		return;
	}
	if ((*g->saw_cleanup > 0 && pid == *g->saw_cleanup) || (*g->cleanup_pid > 0 && pid == *g->cleanup_pid)) {
		*g->have_cleanup_status = 1;
		*g->cleanup_status = status;
		return;
	}
	if ((*g->saw_watched > 0 && pid == *g->saw_watched) || (*g->collector_pid > 0 && pid == *g->collector_pid))
		*g->watched_reaped = 1;
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
	n = read(fd, buf, sizeof buf - 1);
	close(fd);
	if (n <= 0)
		return 0;
	buf[n] = 0;
	line = buf;
	for (;;) {
		char *next = strchr(line, '\n');
		if (next)
			*next = 0;
		if (strncmp(line, "PPid:", 5) == 0) {
			char *end = NULL;
			long ppid = strtol(line + 5, &end, 10);
			return end != line + 5 && ppid == (long)getpid();
		}
		if (!next)
			return 0;
		line = next + 1;
	}
}

/* Hint only. proc_tid_children(5) can omit a child if another exits during
 * the read, so an empty read is not proof the child set is empty.
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
	n = read(fd, buf, sizeof buf - 1);
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

static void retain_adopted(struct admission_outcome *out, pid_t pid)
{
	int i;

	if (pid <= 0)
		return;
	for (i = 0; i < out->unreaped_adopted_count; i++) {
		if (out->unreaped_adopted[i] == pid)
			return;
	}
	if (out->unreaped_adopted_count >= (int)(sizeof out->unreaped_adopted / sizeof out->unreaped_adopted[0])) {
		out->adopted_unresolved = 1;
		return;
	}
	out->unreaped_adopted[out->unreaped_adopted_count++] = pid;
}

/* 0: waitpid(-1) returned ECHILD, so this process has no children.
 * 1: some child is still alive or the reap cap left the set unproven.
 * Specific-pid ECHILD is not used here and is not an exit status.
 */
static int reap_ready_children(struct guard_reap *g)
{
	int pass;

	for (pass = 0; pass < 32; pass++) {
		int status = 0;
		pid_t got = waitpid(-1, &status, WNOHANG);

		if (got > 0) {
			account_wait_status(g, got, status);
			continue;
		}
		if (got < 0 && errno == EINTR)
			continue;
		if (got < 0 && errno == ECHILD) {
			g->out->unreaped_adopted_count = 0;
			g->out->adopted_unresolved = 0;
			return 0;
		}
		if (got < 0) {
			g->out->adopted_unresolved = 1;
			return 1;
		}
		return 1;
	}
	{
		int status = 0;
		pid_t got = waitpid(-1, &status, WNOHANG);

		if (got > 0)
			account_wait_status(g, got, status);
		if (got < 0 && errno == ECHILD) {
			g->out->unreaped_adopted_count = 0;
			g->out->adopted_unresolved = 0;
			return 0;
		}
	}
	g->out->adopted_unresolved = 1;
	return 1;
}

/* 1 when an adopted child is still outstanding or its identity could not be kept.
 * A live named role does not count. The children file is only a hint.
 */
static int unnamed_outstanding(struct guard_reap *g)
{
	pid_t ids[8];
	int truncated = 0;
	int n;
	int i;
	int unnamed = 0;

	g->out->unreaped_adopted_count = 0;
	if (!*g->controller_reaped)
		return 0;
	n = read_child_tids(ids, 8, &truncated);
	if (n < 0) {
		g->out->adopted_unresolved = 1;
		return 1;
	}
	if (truncated)
		g->out->adopted_unresolved = 1;
	for (i = 0; i < n; i++) {
		int pidfd;
		int status = 0;

		if (reap_is_named(g, ids[i]))
			continue;
		unnamed = 1;
		pidfd = open_pidfd(ids[i]);
		if (pidfd < 0) {
			retain_adopted(g->out, ids[i]);
			g->out->adopted_unresolved = 1;
			continue;
		}
		/* The pidfd pins the task. Do not signal a pid that is not our child. */
		if (!child_ppid_is_us(ids[i])) {
			close(pidfd);
			continue;
		}
		signal_pidfd(pidfd, SIGKILL);
		if (reap_nowait(ids[i], &status))
			account_wait_status(g, ids[i], status);
		else
			retain_adopted(g->out, ids[i]);
		close(pidfd);
	}
	return unnamed || truncated || g->out->unreaped_adopted_count > 0 || g->out->adopted_unresolved;
}

int admission_supervise(pid_t controller, int controller_pidfd, int ctrl,
			const struct timespec *admission_deadline, uint32_t cleanup_ms,
			const char *leaf_name, const char *path_prefix, char *accepted_path,
			size_t accepted_cap, const struct admission_guard_ops *ops, int release_fd,
			struct admission_outcome *out)
{
	int admission_tfd = -1;
	int cleanup_tfd = -1;
	int verify_pidfd = -1;
	int cleanup_pidfd = -1;
	int collector_pidfd = -1;
	int cleanup_report = -1;
	int cleanup_ack = -1;
	int pending_fd = -1;
	pid_t verify_pid = -1;
	pid_t cleanup_pid = -1;
	pid_t collector_pid = -1;
	pid_t saw_verify = -1;
	pid_t saw_cleanup = -1;
	pid_t saw_watched = -1;
	int verify_for = 0;
	int cleanup_started = 0;
	int controller_reaped = 0;
	int have_cleanup_status = 0;
	int cleanup_status = 1;
	int verify_reaped = 0;
	int watched_reaped = 0;
	int cleanup_ready = 0;
	int cleanup_expired = 0;
	int owned_directory = 0;
	int skip_ctrl = 0;
	int skip_verify = 0;
	int skip_watched = 0;
	int skip_cleanup = 0;
	int controller_status = 0;
	int adopted_pending = 0;
	char path[PATH_MAX];
	struct timespec cleanup_deadline;
	struct timespec ceiling;
	struct guard_reap reap;

	if (!out || !admission_deadline || !leaf_name || !path_prefix || !ops)
		return -1;
	memset(out, 0, sizeof *out);
	out->custody_fd = -1;
	out->held_cleanup_pidfd = -1;
	out->held_verify_pidfd = -1;
	out->held_watched_pidfd = -1;
	out->owned_controller = controller > 0 ? controller : 0;
	memset(&reap, 0, sizeof reap);
	reap.out = out;
	reap.controller = controller;
	reap.verify_pid = &verify_pid;
	reap.verify_pidfd = &verify_pidfd;
	reap.verify_for = &verify_for;
	reap.verify_reaped = &verify_reaped;
	reap.saw_verify = &saw_verify;
	reap.cleanup_pid = &cleanup_pid;
	reap.have_cleanup_status = &have_cleanup_status;
	reap.cleanup_status = &cleanup_status;
	reap.saw_cleanup = &saw_cleanup;
	reap.collector_pid = &collector_pid;
	reap.watched_reaped = &watched_reaped;
	reap.saw_watched = &saw_watched;
	reap.controller_reaped = &controller_reaped;
	reap.controller_status = &controller_status;
	reap.cleanup_started = &cleanup_started;
	reap.pending_fd = &pending_fd;
	reap.ctrl = &ctrl;
	reap.owned_directory = &owned_directory;
	reap.admission_deadline = admission_deadline;
	reap.cleanup_deadline = &cleanup_deadline;
	path[0] = 0;
	cleanup_deadline = *admission_deadline;
	ceiling = *admission_deadline;
	guard_add_ms(&ceiling, cleanup_ms);
	admission_tfd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC | TFD_NONBLOCK);
	cleanup_tfd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC | TFD_NONBLOCK);
	if (admission_tfd < 0 || cleanup_tfd < 0 || arm_absolute(admission_tfd, admission_deadline) != 0 ||
	    (ctrl >= 0 && set_nonblock(ctrl) != 0)) {
		out->protocol_failed = 1;
		goto finish;
	}
	/* The controller stays parked until this timer exists. */
	if (release_fd >= 0) {
		char go = 'g';
		ssize_t wrote = write(release_fd, &go, 1);
		close(release_fd);
		release_fd = -1;
		if (wrote != 1)
			out->protocol_failed = 1;
	}
	for (;;) {
		struct pollfd pfds[8];
		int nfds = 0;
		int rc;
		int remain = 0;
		int idx_admit = -1, idx_clean = -1, idx_ctrl = -1, idx_sock = -1;
		int idx_verify = -1, idx_worker = -1, idx_collect = -1, idx_pipe = -1;
		const struct timespec *active;

		if (skip_ctrl && !controller_reaped && reap_nowait(controller, &controller_status))
			note_status(out, controller, controller, controller_status, &controller_reaped,
				    &cleanup_status, &have_cleanup_status, cleanup_pid, NULL, NULL, -1);
		if (!verify_reaped && saw_verify > 0) {
			int status = 0;
			if (reap_nowait(saw_verify, &status)) {
				if (verify_for == (int)GUARD_CUSTODY || verify_for == (int)GUARD_CLONE)
					apply_verify_exit(out, status, cleanup_started, ctrl,
							  cleanup_started ? &cleanup_deadline : admission_deadline,
							  &pending_fd, &verify_pid, &verify_pidfd, &verify_for,
							  &verify_reaped, &owned_directory);
				else {
					verify_reaped = 1;
					verify_pid = -1;
				}
				skip_verify = 0;
			}
		}
		if (skip_watched && !watched_reaped && reap_nowait(collector_pid, NULL))
			watched_reaped = 1;
		if (skip_cleanup && !have_cleanup_status && reap_nowait(cleanup_pid, &cleanup_status))
			have_cleanup_status = 1;
		/* Zombies, including children adopted from the controller, are waited
		 * by the pid waitpid returns. A specific ECHILD is not a reap.
		 */
		adopted_pending = 0;
		if (reap_ready_children(&reap) != 0 && controller_reaped)
			adopted_pending = unnamed_outstanding(&reap);
		if (cleanup_started && guard_remaining_ms(&cleanup_deadline, NULL) != 0)
			cleanup_expired = 1;
		if (cleanup_expired) {
			out->cleanup_confirmed = 0;
			break;
		}
		if (cleanup_started && controller_reaped && (saw_watched <= 0 || watched_reaped) &&
		    (saw_verify <= 0 || verify_reaped) && (!owned_directory || have_cleanup_status) &&
		    !adopted_pending)
			break;
		if (!cleanup_started && (out->timed_out || controller_reaped || out->protocol_failed)) {
			struct timespec now;
			int report[2] = {-1, -1};
			int ack[2] = {-1, -1};

			cleanup_started = 1;
			if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) {
				out->protocol_failed = 1;
				cleanup_expired = 1;
				break;
			}
			cleanup_deadline = now;
			guard_add_ms(&cleanup_deadline, cleanup_ms);
			if (timespec_after(&cleanup_deadline, &ceiling))
				cleanup_deadline = ceiling;
			if (arm_absolute(cleanup_tfd, &cleanup_deadline) != 0 ||
			    guard_remaining_ms(&cleanup_deadline, NULL) != 0) {
				out->protocol_failed = 1;
				cleanup_expired = 1;
				out->cleanup_confirmed = 0;
				break;
			}
			if (!controller_reaped)
				signal_pidfd(controller_pidfd, SIGKILL);
			if (!watched_reaped)
				signal_pidfd(collector_pidfd, SIGKILL);
			if (!verify_reaped)
				signal_pidfd(verify_pidfd, SIGKILL);
			/* An unverified descriptor is not ownership. Close it
			 * without cgroup.kill. A proposed path is not opened.
			 */
			if (!owned_directory && pending_fd >= 0) {
				close(pending_fd);
				pending_fd = -1;
			}
			if (owned_directory && out->custody_fd >= 0) {
				if (pipe2(report, O_CLOEXEC) != 0) {
					out->protocol_failed = 1;
					out->cleanup_confirmed = 0;
				} else if (pipe2(ack, O_CLOEXEC) != 0) {
					close(report[0]);
					close(report[1]);
					out->protocol_failed = 1;
					out->cleanup_confirmed = 0;
				} else {
					cleanup_pid = fork();
					if (cleanup_pid < 0) {
						out->protocol_failed = 1;
						out->cleanup_confirmed = 0;
						close(report[0]);
						close(report[1]);
						close(ack[0]);
						close(ack[1]);
					} else if (cleanup_pid == 0) {
						close(report[0]);
						close(ack[1]);
						cleanup_worker(out->custody_fd, report[1], ack[0], ops);
						_exit(2);
					} else {
						saw_cleanup = cleanup_pid;
						close(report[1]);
						close(ack[0]);
						cleanup_report = report[0];
						cleanup_ack = ack[1];
						cleanup_pidfd = open_pidfd(cleanup_pid);
						if (cleanup_pidfd < 0) {
							out->protocol_failed = 1;
							out->cleanup_confirmed = 0;
							kill(cleanup_pid, SIGKILL);
						}
					}
				}
			} else {
				have_cleanup_status = 1;
				cleanup_status = 1;
				out->cleanup_confirmed = 0;
			}
			continue;
		}
		active = cleanup_started ? &cleanup_deadline : admission_deadline;
		if (guard_remaining_ms(active, &remain) != 0) {
			if (cleanup_started)
				cleanup_expired = 1;
			else
				out->timed_out = 1;
			continue;
		}
		if (remain > 20 && (skip_ctrl || skip_verify || skip_watched || skip_cleanup || adopted_pending))
			remain = 20;
		if (!cleanup_started) {
			pfds[nfds].fd = admission_tfd;
			pfds[nfds].events = POLLIN;
			idx_admit = nfds++;
		}
		if (cleanup_started) {
			pfds[nfds].fd = cleanup_tfd;
			pfds[nfds].events = POLLIN;
			idx_clean = nfds++;
		}
		if (!controller_reaped && controller_pidfd >= 0 && !skip_ctrl) {
			pfds[nfds].fd = controller_pidfd;
			pfds[nfds].events = POLLIN;
			idx_ctrl = nfds++;
		}
		if (ctrl >= 0) {
			pfds[nfds].fd = ctrl;
			pfds[nfds].events = POLLIN;
			idx_sock = nfds++;
		}
		if (verify_pid > 0 && verify_pidfd >= 0 && !skip_verify && !verify_reaped) {
			pfds[nfds].fd = verify_pidfd;
			pfds[nfds].events = POLLIN;
			idx_verify = nfds++;
		}
		if (cleanup_pid > 0 && cleanup_pidfd >= 0 && !have_cleanup_status && !skip_cleanup) {
			pfds[nfds].fd = cleanup_pidfd;
			pfds[nfds].events = POLLIN;
			idx_worker = nfds++;
		}
		if (collector_pid > 0 && collector_pidfd >= 0 && !watched_reaped && !skip_watched) {
			pfds[nfds].fd = collector_pidfd;
			pfds[nfds].events = POLLIN;
			idx_collect = nfds++;
		}
		if (cleanup_report >= 0 && !cleanup_ready) {
			pfds[nfds].fd = cleanup_report;
			pfds[nfds].events = POLLIN;
			idx_pipe = nfds++;
		}
		if (nfds == 0) {
			out->protocol_failed = 1;
			if (!cleanup_started)
				continue;
			cleanup_expired = 1;
			break;
		}
		rc = poll(pfds, (nfds_t)nfds, remain);
		if (rc < 0) {
			if (errno == EINTR)
				continue;
			out->protocol_failed = 1;
			if (!cleanup_started)
				continue;
			cleanup_expired = 1;
			out->cleanup_confirmed = 0;
			break;
		}
		if (rc == 0)
			continue;
		if (idx_admit >= 0 && (pfds[idx_admit].revents & POLLIN) && !cleanup_started) {
			consume_timer(admission_tfd);
			out->timed_out = 1;
		}
		if (idx_clean >= 0 && (pfds[idx_clean].revents & POLLIN)) {
			consume_timer(cleanup_tfd);
			cleanup_expired = 1;
			out->cleanup_confirmed = 0;
			break;
		}
		if (idx_ctrl >= 0 && (pfds[idx_ctrl].revents & POLLIN) && !controller_reaped) {
			int status = 0;
			if (reap_nowait(controller, &status)) {
				controller_status = status;
				note_status(out, controller, controller, status, &controller_reaped, &cleanup_status,
					    &have_cleanup_status, cleanup_pid, NULL, NULL, -1);
			} else {
				skip_ctrl = 1;
			}
		}
		if (idx_pipe >= 0 && (pfds[idx_pipe].revents & POLLIN) && !cleanup_ready) {
			char byte = 0;
			if (read(cleanup_report, &byte, 1) == 1 && byte == '1') {
				cleanup_ready = 1;
				if (out->custody_fd >= 0) {
					close(out->custody_fd);
					out->custody_fd = -1;
				}
				if (cleanup_ack >= 0) {
					char go = '1';
					ssize_t wrote = write(cleanup_ack, &go, 1);
					if (wrote != 1)
						out->cleanup_confirmed = 0;
				}
			}
		}
		if (idx_worker >= 0 && (pfds[idx_worker].revents & POLLIN) && !have_cleanup_status) {
			int status = 0;
			if (reap_nowait(cleanup_pid, &status)) {
				have_cleanup_status = 1;
				cleanup_status = status;
			} else {
				skip_cleanup = 1;
			}
		}
		if (idx_verify >= 0 && (pfds[idx_verify].revents & POLLIN) && !verify_reaped) {
			int status = 0;
			if (!reap_nowait(verify_pid, &status))
				skip_verify = 1;
			else
				apply_verify_exit(out, status, cleanup_started, ctrl, active, &pending_fd, &verify_pid,
						  &verify_pidfd, &verify_for, &verify_reaped, &owned_directory);
		}
		if (idx_collect >= 0 && (pfds[idx_collect].revents & POLLIN) && !watched_reaped) {
			int status = 0;
			if (reap_nowait(collector_pid, &status))
				watched_reaped = 1;
			else
				skip_watched = 1;
		}
		if (idx_sock >= 0 && (pfds[idx_sock].revents & (POLLIN | POLLHUP))) {
			char buf[sizeof(struct guard_head) + sizeof(struct lifetime_receipt)];
			char control[CMSG_SPACE(sizeof(int))];
			struct msghdr msg;
			struct iovec iov;
			ssize_t n;
			struct guard_head head;
			struct cmsghdr *cmsg;
			int got_fd = -1;

			memset(&msg, 0, sizeof msg);
			iov.iov_base = buf;
			iov.iov_len = sizeof buf;
			msg.msg_iov = &iov;
			msg.msg_iovlen = 1;
			msg.msg_control = control;
			msg.msg_controllen = sizeof control;
			n = recvmsg(ctrl, &msg, MSG_CMSG_CLOEXEC | MSG_DONTWAIT);
			if (n < 0 && (errno == EINTR || errno == EAGAIN))
				continue;
			if (n == 0) {
				ctrl = -1;
				continue;
			}
			if (n < (ssize_t)sizeof head) {
				close_received_fds(&msg);
				out->protocol_failed = 1;
				continue;
			}
			memcpy(&head, buf, sizeof head);
			for (cmsg = CMSG_FIRSTHDR(&msg); cmsg; cmsg = CMSG_NXTHDR(&msg, cmsg)) {
				if (cmsg->cmsg_level == SOL_SOCKET && cmsg->cmsg_type == SCM_RIGHTS &&
				    cmsg->cmsg_len >= CMSG_LEN(sizeof(int))) {
					int fd;
					memcpy(&fd, CMSG_DATA(cmsg), sizeof fd);
					if (got_fd < 0)
						got_fd = fd;
					else if (fd >= 0)
						close(fd);
				}
			}
			if (head.type == GUARD_PATH) {
				int reply = GUARD_PATH_NO;
				if (!path[0] && head.nbytes > 0 && head.nbytes < PATH_MAX &&
				    (size_t)n == sizeof head + head.nbytes &&
				    buf[sizeof head + head.nbytes - 1] == 0 &&
				    path_matches_leaf(buf + sizeof head, path_prefix, leaf_name) &&
				    accepted_path && accepted_cap >= head.nbytes && !out->timed_out &&
				    !cleanup_started) {
					memcpy(path, buf + sizeof head, head.nbytes);
					memcpy(accepted_path, path, head.nbytes);
					reply = GUARD_PATH_OK;
				}
				if (reply_simple(ctrl, (uint32_t)reply, active) != 0)
					out->protocol_failed = 1;
				if (got_fd >= 0)
					close(got_fd);
			} else if (head.type == GUARD_CUSTODY) {
				if (got_fd < 0 || pending_fd >= 0 || out->custody_fd >= 0 || path[0] == 0 ||
				    verify_pid > 0 || out->timed_out || cleanup_started) {
					if (got_fd >= 0)
						close(got_fd);
					if (reply_simple(ctrl, GUARD_CUSTODY_NO, active) != 0)
						out->protocol_failed = 1;
				} else {
					pending_fd = got_fd;
					verify_pid = fork();
					if (verify_pid < 0) {
						close(pending_fd);
						pending_fd = -1;
						out->protocol_failed = 1;
						if (reply_simple(ctrl, GUARD_CUSTODY_NO, active) != 0)
							out->protocol_failed = 1;
					} else if (verify_pid == 0) {
						verify_custody(pending_fd, path);
					} else {
						saw_verify = verify_pid;
						out->owned_verify = verify_pid;
						verify_reaped = 0;
						skip_verify = 0;
						verify_pidfd = open_pidfd(verify_pid);
						verify_for = (int)GUARD_CUSTODY;
						if (verify_pidfd < 0) {
							kill(verify_pid, SIGKILL);
							if (reap_nowait(verify_pid, NULL))
								verify_reaped = 1;
							verify_pid = -1;
							verify_for = 0;
							close(pending_fd);
							pending_fd = -1;
							out->protocol_failed = 1;
							if (reply_simple(ctrl, GUARD_CUSTODY_NO, active) != 0)
								out->protocol_failed = 1;
						}
					}
				}
			} else if (head.type == GUARD_CLONE) {
				if (got_fd >= 0)
					close(got_fd);
				if (!out->custody_held || out->clone_permits != 0 || verify_pid > 0 ||
				    out->timed_out || cleanup_started || path[0] == 0 || !owned_directory) {
					if (reply_simple(ctrl, GUARD_CLONE_NO, active) != 0)
						out->protocol_failed = 1;
				} else {
					verify_pid = fork();
					if (verify_pid < 0) {
						out->protocol_failed = 1;
						if (reply_simple(ctrl, GUARD_CLONE_NO, active) != 0)
							out->protocol_failed = 1;
					} else if (verify_pid == 0) {
						verify_custody(out->custody_fd, path);
					} else {
						saw_verify = verify_pid;
						out->owned_verify = verify_pid;
						verify_reaped = 0;
						skip_verify = 0;
						verify_pidfd = open_pidfd(verify_pid);
						verify_for = (int)GUARD_CLONE;
						if (verify_pidfd < 0) {
							kill(verify_pid, SIGKILL);
							if (reap_nowait(verify_pid, NULL))
								verify_reaped = 1;
							verify_pid = -1;
							verify_for = 0;
							out->protocol_failed = 1;
							if (reply_simple(ctrl, GUARD_CLONE_NO, active) != 0)
								out->protocol_failed = 1;
						}
					}
				}
			} else if (head.type == GUARD_WATCH) {
				if (got_fd >= 0)
					close(got_fd);
				if (head.pid <= 0 || collector_pid > 0 || out->timed_out || cleanup_started) {
					if (reply_simple(ctrl, GUARD_WATCH_NO, active) != 0)
						out->protocol_failed = 1;
				} else {
					int watched_fd = open_pidfd((pid_t)head.pid);
					if (watched_fd < 0) {
						if (reply_simple(ctrl, GUARD_WATCH_NO, active) != 0)
							out->protocol_failed = 1;
					} else {
						collector_pidfd = watched_fd;
						collector_pid = (pid_t)head.pid;
						saw_watched = collector_pid;
						out->owned_watched = collector_pid;
						if (reply_simple(ctrl, GUARD_WATCH_OK, active) != 0)
							out->protocol_failed = 1;
					}
				}
			} else if (head.type == GUARD_RESULT) {
				if (got_fd >= 0)
					close(got_fd);
				if (head.nbytes != sizeof(struct lifetime_receipt) ||
				    (size_t)n != sizeof head + sizeof(struct lifetime_receipt) ||
				    out->have_result) {
					out->protocol_failed = 1;
				} else {
					memcpy(&out->receipt, buf + sizeof head, sizeof out->receipt);
					out->have_result = 1;
					if (controller_reaped && !out->timed_out && WIFEXITED(controller_status) &&
					    !WIFSIGNALED(controller_status))
						out->controller_lost = 0;
				}
			} else if (head.type == GUARD_DONE) {
				if (got_fd >= 0)
					close(got_fd);
			} else {
				if (got_fd >= 0)
					close(got_fd);
				out->protocol_failed = 1;
			}
		}
	}
finish:
	/* One nonblocking pass. A worker still inside the kernel is not success
	 * and is not waited on.
	 */
	if (!controller_reaped && controller_pidfd >= 0)
		signal_pidfd(controller_pidfd, SIGKILL);
	if (!have_cleanup_status && cleanup_pidfd >= 0)
		signal_pidfd(cleanup_pidfd, SIGKILL);
	if (!verify_reaped && verify_pidfd >= 0)
		signal_pidfd(verify_pidfd, SIGKILL);
	if (!watched_reaped && collector_pidfd >= 0)
		signal_pidfd(collector_pidfd, SIGKILL);
	if (!controller_reaped && controller > 0 && reap_nowait(controller, &controller_status))
		note_status(out, controller, controller, controller_status, &controller_reaped, &cleanup_status,
			    &have_cleanup_status, cleanup_pid, NULL, NULL, -1);
	if (!verify_reaped && saw_verify > 0 && reap_nowait(saw_verify, NULL))
		verify_reaped = 1;
	if (!watched_reaped && saw_watched > 0 && reap_nowait(saw_watched, NULL))
		watched_reaped = 1;
	if (!have_cleanup_status && saw_cleanup > 0 && reap_nowait(saw_cleanup, &cleanup_status))
		have_cleanup_status = 1;
	/* Last nonblocking pass. Emptiness is waitpid(-1) returning ECHILD after
	 * the controller has been reaped, so adopted descendants are our children.
	 */
	adopted_pending = 0;
	if (reap_ready_children(&reap) != 0) {
		if (controller_reaped)
			unnamed_outstanding(&reap);
		reap_ready_children(&reap);
		if (reap_ready_children(&reap) != 0)
			adopted_pending = 1;
	}
	out->owned_controller = controller > 0 ? controller : 0;
	out->owned_cleanup = saw_cleanup > 0 ? saw_cleanup : 0;
	out->owned_verify = saw_verify > 0 ? saw_verify : 0;
	out->owned_watched = saw_watched > 0 ? saw_watched : 0;
	out->owned_directory = owned_directory;
	out->unreaped_controller = (controller > 0 && !controller_reaped) ? controller : 0;
	out->unreaped_cleanup = (saw_cleanup > 0 && !have_cleanup_status) ? saw_cleanup : 0;
	out->unreaped_verify = (saw_verify > 0 && !verify_reaped) ? saw_verify : 0;
	out->unreaped_watched = (saw_watched > 0 && !watched_reaped) ? saw_watched : 0;
	if (out->unreaped_controller || out->unreaped_cleanup || out->unreaped_verify || out->unreaped_watched ||
	    out->unreaped_adopted_count > 0 || out->adopted_unresolved || adopted_pending)
		out->reap_unconfirmed = 1;
	if (out->reap_unconfirmed || cleanup_expired || !owned_directory || !cleanup_ready || !have_cleanup_status ||
	    !controller_reaped || (saw_watched > 0 && !watched_reaped) || (saw_verify > 0 && !verify_reaped) ||
	    out->unreaped_adopted_count > 0 || out->adopted_unresolved || adopted_pending ||
	    !(WIFEXITED(cleanup_status) && WEXITSTATUS(cleanup_status) == 0))
		out->cleanup_confirmed = 0;
	else
		out->cleanup_confirmed = 1;
	note_pid("unreaped_controller", out->unreaped_controller);
	note_pid("unreaped_cleanup", out->unreaped_cleanup);
	note_pid("unreaped_verify", out->unreaped_verify);
	note_pid("unreaped_watched", out->unreaped_watched);
	for (int adopted_i = 0; adopted_i < out->unreaped_adopted_count; adopted_i++)
		note_pid("unreaped_adopted", out->unreaped_adopted[adopted_i]);
	if (!out->cleanup_confirmed && path[0])
		dprintf(STDERR_FILENO, "admission_guard: leaf_path=%s owned_directory=%d\n", path, owned_directory);
	if (release_fd >= 0)
		close(release_fd);
	if (pending_fd >= 0)
		close(pending_fd);
	if (admission_tfd >= 0)
		close(admission_tfd);
	if (cleanup_tfd >= 0)
		close(cleanup_tfd);
	if (!verify_reaped && verify_pidfd >= 0) {
		out->held_verify_pidfd = verify_pidfd;
		verify_pidfd = -1;
	} else if (verify_pidfd >= 0) {
		close(verify_pidfd);
	}
	if (!have_cleanup_status && cleanup_pidfd >= 0) {
		out->held_cleanup_pidfd = cleanup_pidfd;
		cleanup_pidfd = -1;
	} else if (cleanup_pidfd >= 0) {
		close(cleanup_pidfd);
	}
	if (!watched_reaped && collector_pidfd >= 0) {
		out->held_watched_pidfd = collector_pidfd;
		collector_pidfd = -1;
	} else if (collector_pidfd >= 0) {
		close(collector_pidfd);
	}
	if (cleanup_report >= 0)
		close(cleanup_report);
	if (cleanup_ack >= 0)
		close(cleanup_ack);
	if (out->custody_fd >= 0) {
		close(out->custody_fd);
		out->custody_fd = -1;
	}
	return 0;
}

struct temp_own {
	int dfd;
	int fd;
	int have;
};

/* Publisher uid owns the directory, and group or other cannot write it. */
static int directory_exclusive(int dfd)
{
	struct stat st;

	if (dfd < 0 || fstat(dfd, &st) != 0 || !S_ISDIR(st.st_mode))
		return 0;
	if (st.st_uid != getuid())
		return 0;
	if ((st.st_mode & (S_IWGRP | S_IWOTH)) != 0)
		return 0;
	return 1;
}

static int report_phase(int progress_fd, char phase)
{
	if (progress_fd < 0)
		return 0;
	for (;;) {
		ssize_t n = write(progress_fd, &phase, 1);
		if (n == 1)
			return 0;
		if (n < 0 && errno == EINTR)
			continue;
		return -1;
	}
}

static int phase_gate(int stall_fd, char phase)
{
	if (stall_fd < 0)
		return 0;
	for (;;) {
		char byte = 0;
		ssize_t n = read(stall_fd, &byte, 1);

		if (n < 0 && errno == EINTR)
			continue;
		if (n != 1)
			return -1;
		if (byte == phase)
			return 0;
	}
}

static void close_temp(struct temp_own *tmp)
{
	if (!tmp)
		return;
	if (tmp->fd >= 0)
		close(tmp->fd);
	if (tmp->dfd >= 0)
		close(tmp->dfd);
	tmp->fd = -1;
	tmp->dfd = -1;
}

/* The temporary is an unnamed inode. Abandoning it closes that inode.
 * There is no pathname to unlink. A published final name is never removed.
 */
static int release_temp(struct temp_own *tmp)
{
	if (!tmp || !tmp->have)
		return 0;
	if (tmp->fd < 0)
		return -1;
	tmp->have = 0;
	return 0;
}

static int rollback_temp(struct temp_own *tmp, int stall_fd, int progress_fd)
{
	if (report_phase(progress_fd, 'U') != 0 || phase_gate(stall_fd, 'U') != 0)
		return -1;
	if (release_temp(tmp) != 0)
		return -1;
	return 0;
}

static int fail_commit(struct temp_own *tmp, int stall_fd, int progress_fd)
{
	rollback_temp(tmp, stall_fd, progress_fd);
	close_temp(tmp);
	return -1;
}

int receipt_commit_exclusive(const char *path, const void *buf, size_t len, int stall_fd, int progress_fd)
{
	char dir[PATH_MAX];
	char base_buf[NAME_MAX + 1];
	const char *slash;
	const char *base;
	struct stat before;
	struct stat after;
	struct stat created;
	struct temp_own tmp;
	char *check = NULL;
	ssize_t got = 0;
	size_t n = 0;
	size_t dlen;
	int rfd;

	memset(&tmp, 0, sizeof tmp);
	tmp.dfd = -1;
	tmp.fd = -1;

	if (!path || !buf || len == 0 || strlen(path) >= PATH_MAX)
		return -1;
	slash = strrchr(path, '/');
	if (!slash) {
		memcpy(dir, ".", 2);
		base = path;
	} else if (slash == path) {
		memcpy(dir, "/", 2);
		base = slash + 1;
	} else {
		dlen = (size_t)(slash - path);
		if (dlen >= sizeof dir)
			return -1;
		memcpy(dir, path, dlen);
		dir[dlen] = 0;
		base = slash + 1;
	}
	if (!base[0] || strcmp(base, ".") == 0 || strcmp(base, "..") == 0 || strlen(base) >= sizeof base_buf)
		return -1;
	memcpy(base_buf, base, strlen(base) + 1);
	if (lstat(path, &before) == 0) {
		/* Present, including a replaceable final name. Do not remove it. */
		(void)before.st_ino;
		return -1;
	}
	if (errno != ENOENT)
		return -1;
	tmp.dfd = open(dir, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
	if (tmp.dfd < 0 || !directory_exclusive(tmp.dfd)) {
		close_temp(&tmp);
		return -1;
	}
	/* O_EXCL with O_TMPFILE would refuse the later link. A filesystem that
	 * rejects O_TMPFILE is reported and is not given a named partial.
	 */
	tmp.fd = openat(tmp.dfd, ".", O_TMPFILE | O_WRONLY | O_CLOEXEC, 0644);
	if (tmp.fd < 0) {
		dprintf(STDERR_FILENO, "admission_guard: unnamed temporary refused errno=%d\n", errno);
		return fail_commit(&tmp, stall_fd, progress_fd);
	}
	tmp.have = 1;
	while (n < len) {
		ssize_t w = write(tmp.fd, (const char *)buf + n, len - n);

		if (w < 0) {
			if (errno == EINTR)
				continue;
			return fail_commit(&tmp, stall_fd, progress_fd);
		}
		if (w == 0)
			return fail_commit(&tmp, stall_fd, progress_fd);
		n += (size_t)w;
	}
	if (fsync(tmp.fd) != 0 || fstat(tmp.fd, &created) != 0 || !S_ISREG(created.st_mode) ||
	    (size_t)created.st_size != len)
		return fail_commit(&tmp, stall_fd, progress_fd);
	/* linkat fails if the final name exists. That name is not ours to remove.
	 * AT_EMPTY_PATH needs CAP_DAC_READ_SEARCH. The proc fd path is the
	 * unprivileged link open(2) documents for an O_TMPFILE inode.
	 */
	if (report_phase(progress_fd, 'C') != 0 || phase_gate(stall_fd, 'C') != 0)
		return fail_commit(&tmp, stall_fd, progress_fd);
	{
		char proc[64];

		if (snprintf(proc, sizeof proc, "/proc/self/fd/%d", tmp.fd) >= (int)sizeof proc)
			return fail_commit(&tmp, stall_fd, progress_fd);
		if (linkat(AT_FDCWD, proc, tmp.dfd, base_buf, AT_SYMLINK_FOLLOW) != 0) {
			dprintf(STDERR_FILENO, "admission_guard: final link refused errno=%d\n", errno);
			return fail_commit(&tmp, stall_fd, progress_fd);
		}
	}
	/* Published. A later failure leaves this final name in place. */
	if (release_temp(&tmp) != 0)
		return fail_commit(&tmp, stall_fd, progress_fd);
	if (fsync(tmp.dfd) != 0)
		return fail_commit(&tmp, stall_fd, progress_fd);
	rfd = openat(tmp.dfd, base_buf, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
	if (rfd < 0)
		return fail_commit(&tmp, stall_fd, progress_fd);
	if (fstat(rfd, &after) != 0 || (size_t)after.st_size != len || after.st_dev != created.st_dev ||
	    after.st_ino != created.st_ino) {
		close(rfd);
		return fail_commit(&tmp, stall_fd, progress_fd);
	}
	check = malloc(len);
	if (!check) {
		close(rfd);
		return fail_commit(&tmp, stall_fd, progress_fd);
	}
	n = 0;
	while (n < len) {
		got = read(rfd, check + n, len - n);
		if (got < 0) {
			if (errno == EINTR)
				continue;
			free(check);
			close(rfd);
			return fail_commit(&tmp, stall_fd, progress_fd);
		}
		if (got == 0)
			break;
		n += (size_t)got;
	}
	close(rfd);
	if (n != len || memcmp(check, buf, len) != 0) {
		free(check);
		return fail_commit(&tmp, stall_fd, progress_fd);
	}
	free(check);
	close_temp(&tmp);
	return 0;
}

static int supervise_deadline(pid_t child, const struct timespec *deadline, int *status, int *reaped)
{
	int pidfd;
	int tfd;

	*status = 1;
	*reaped = 0;
	pidfd = open_pidfd(child);
	tfd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC | TFD_NONBLOCK);
	if (pidfd < 0 || tfd < 0 || arm_absolute(tfd, deadline) != 0) {
		if (pidfd >= 0)
			signal_pidfd(pidfd, SIGKILL);
		else
			guard_signal_pinned(child, SIGKILL);
		*reaped = reap_nowait(child, status);
		if (pidfd >= 0)
			close(pidfd);
		if (tfd >= 0)
			close(tfd);
		return -1;
	}
	for (;;) {
		struct pollfd pfds[2];
		int remain = 0;
		int rc;

		if (guard_remaining_ms(deadline, &remain) != 0) {
			signal_pidfd(pidfd, SIGKILL);
			break;
		}
		pfds[0].fd = tfd;
		pfds[0].events = POLLIN;
		pfds[1].fd = pidfd;
		pfds[1].events = POLLIN;
		rc = poll(pfds, 2, remain);
		if (rc < 0 && errno == EINTR)
			continue;
		if (rc < 0) {
			signal_pidfd(pidfd, SIGKILL);
			break;
		}
		if (rc == 0 || (pfds[0].revents & POLLIN)) {
			signal_pidfd(pidfd, SIGKILL);
			break;
		}
		if ((pfds[1].revents & POLLIN) && reap_nowait(child, status)) {
			*reaped = 1;
			break;
		}
	}
	if (!*reaped)
		*reaped = reap_nowait(child, status);
	close(pidfd);
	close(tfd);
	return *reaped ? 0 : -1;
}

static void publish_worker(const char *path, const void *buf, size_t len, int stall_fd, int progress_fd)
{
	struct stat st;

	if (report_phase(progress_fd, 'I') != 0 || phase_gate(stall_fd, 'I') != 0)
		_exit(2);
	if (lstat(path, &st) == 0)
		_exit(3);
	if (errno != ENOENT)
		_exit(2);
	if (receipt_commit_exclusive(path, buf, len, stall_fd, progress_fd) != 0)
		_exit(2);
	if (report_phase(progress_fd, 'P') != 0 || phase_gate(stall_fd, 'P') != 0)
		_exit(2);
	_exit(0);
}

int receipt_confirm_absent(const char *path, const struct timespec *deadline, pid_t *unreaped_out)
{
	pid_t child;
	int status = 1;
	int reaped = 0;

	if (unreaped_out)
		*unreaped_out = 0;
	if (!path || !path[0] || !deadline)
		return -1;
	if (guard_remaining_ms(deadline, NULL) != 0)
		return -1;
	child = fork();
	if (child < 0)
		return -1;
	if (child == 0) {
		struct stat st;

		if (lstat(path, &st) == 0)
			_exit(3);
		_exit(errno == ENOENT ? 0 : 2);
	}
	if (supervise_deadline(child, deadline, &status, &reaped) != 0) {
		if (!reaped && unreaped_out)
			*unreaped_out = child;
		return -1;
	}
	if (guard_remaining_ms(deadline, NULL) != 0)
		return -1;
	if (WIFEXITED(status) && WEXITSTATUS(status) == 0)
		return 0;
	if (WIFEXITED(status) && WEXITSTATUS(status) == 3)
		return -2;
	return -1;
}

int receipt_publish_supervised(const char *path, const void *buf, size_t len,
			       const struct timespec *deadline, int stall_fd, int progress_fd,
			       pid_t *unreaped_out)
{
	pid_t child;
	int status = 1;
	int reaped = 0;

	if (unreaped_out)
		*unreaped_out = 0;
	if (!path || !buf || !deadline || len == 0)
		return -1;
	if (guard_remaining_ms(deadline, NULL) != 0)
		return -1;
	child = fork();
	if (child < 0)
		return -1;
	if (child == 0)
		publish_worker(path, buf, len, stall_fd, progress_fd);
	if (supervise_deadline(child, deadline, &status, &reaped) != 0) {
		if (!reaped && unreaped_out)
			*unreaped_out = child;
		return -1;
	}
	/* A late file is not success. The worker's exit is the publication result. */
	if (!(WIFEXITED(status) && WEXITSTATUS(status) == 0) || guard_remaining_ms(deadline, NULL) != 0)
		return -1;
	return 0;
}
