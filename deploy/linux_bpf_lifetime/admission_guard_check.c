#define _GNU_SOURCE

/* Unprivileged checks of the admission guardian's supervision, IPC and
 * result rules. This file does not create a cgroup, load BPF, or decide
 * that a kernel admitted the diagnostic.
 */

#include "admission_guard.h"
#include "admission_guard_owner.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <unistd.h>

#ifndef __NR_pidfd_open
#define __NR_pidfd_open 434
#endif
#ifndef __NR_pidfd_send_signal
#define __NR_pidfd_send_signal 424
#endif

static int failures;

static int open_pidfd(pid_t pid);

static int fail_setup(const char *what)
{
	dprintf(STDERR_FILENO, "supervision check failed: %s\n", what);
	failures++;
	return -1;
}

static void release_handles(struct admission_outcome *out)
{
	if (!out)
		return;
	if (out->held_cleanup_pidfd >= 0)
		close(out->held_cleanup_pidfd);
	if (out->held_verify_pidfd >= 0)
		close(out->held_verify_pidfd);
	if (out->held_watched_pidfd >= 0)
		close(out->held_watched_pidfd);
	out->held_cleanup_pidfd = -1;
	out->held_verify_pidfd = -1;
	out->held_watched_pidfd = -1;
}

static void close_pair(int fd[2])
{
	if (!fd)
		return;
	if (fd[0] >= 0)
		close(fd[0]);
	if (fd[1] >= 0)
		close(fd[1]);
	fd[0] = -1;
	fd[1] = -1;
}

/* Non-signalling. ECHILD and a completed reap both stop the wait.
 * This does not open a pidfd.
 */
static void reap_child_bounded(pid_t pid)
{
	struct timespec deadline;

	if (pid <= 0)
		return;
	if (clock_gettime(CLOCK_MONOTONIC, &deadline) != 0) {
		waitpid(pid, NULL, WNOHANG);
		return;
	}
	guard_add_ms(&deadline, 500);
	for (;;) {
		int remain = 0;
		pid_t got = waitpid(pid, NULL, WNOHANG);

		if (got == pid || got < 0)
			break;
		if (guard_remaining_ms(&deadline, &remain) != 0)
			break;
		if (poll(NULL, 0, remain > 20 ? 20 : remain) < 0 && errno != EINTR)
			break;
	}
}

/* 1 only while this pid is still our unreaped child. ECHILD is not that. */
static int unreaped_direct_child(pid_t pid)
{
	siginfo_t info;

	if (pid <= 0)
		return 0;
	memset(&info, 0, sizeof info);
	if (waitid(P_PID, (id_t)pid, &info, WEXITED | WNOHANG | WNOWAIT) != 0)
		return 0;
	return info.si_pid == pid || info.si_pid == 0;
}

static void stop_child(pid_t pid)
{
	int pidfd;

	if (!unreaped_direct_child(pid)) {
		reap_child_bounded(pid);
		return;
	}
	pidfd = open_pidfd(pid);
	if (pidfd >= 0) {
		syscall(__NR_pidfd_send_signal, pidfd, SIGKILL, NULL, 0);
		close(pidfd);
	}
	reap_child_bounded(pid);
}

static void remove_tree(const char *dir)
{
	DIR *handle;
	struct dirent *ent;

	handle = opendir(dir);
	if (!handle) {
		rmdir(dir);
		return;
	}
	while ((ent = readdir(handle)) != NULL) {
		char path[PATH_MAX];

		if (strcmp(ent->d_name, ".") == 0 || strcmp(ent->d_name, "..") == 0)
			continue;
		if (snprintf(path, sizeof path, "%s/%s", dir, ent->d_name) >= (int)sizeof path)
			continue;
		unlink(path);
		rmdir(path);
	}
	closedir(handle);
	rmdir(dir);
}

static void expect(int cond, const char *what)
{
	if (!cond) {
		dprintf(STDERR_FILENO, "supervision check failed: %s\n", what);
		failures++;
	}
}

static int open_pidfd(pid_t pid)
{
	return (int)syscall(__NR_pidfd_open, pid, 0);
}

static void ignore_signal(int sig)
{
	(void)sig;
}

static int kill_fail(int dirfd, void *ctx)
{
	(void)dirfd;
	(void)ctx;
	return -1;
}

static int populated_busy(int dirfd, int *out, void *ctx)
{
	(void)dirfd;
	(void)ctx;
	*out = 1;
	return 0;
}

static int remove_fail(void *ctx)
{
	(void)ctx;
	return -1;
}

static int kill_fstat(int dirfd, void *ctx)
{
	struct stat st;

	(void)ctx;
	if (fstat(dirfd, &st) != 0 || !S_ISDIR(st.st_mode))
		return -1;
	return 0;
}

struct mark_obs {
	int write_fd;
};

static int kill_mark(int dirfd, void *ctx)
{
	struct mark_obs *mark = ctx;
	char byte = 'k';

	(void)dirfd;
	if (!mark || mark->write_fd < 0 || write(mark->write_fd, &byte, 1) != 1)
		return -1;
	return 0;
}

static int kill_pause(int dirfd, void *ctx)
{
	(void)dirfd;
	(void)ctx;
	for (;;)
		pause();
	return -1;
}

static int populated_empty(int dirfd, int *out, void *ctx)
{
	(void)dirfd;
	(void)ctx;
	*out = 0;
	return 0;
}

static int remove_rmdir(void *ctx)
{
	char *path = ctx;

	return path && rmdir(path) == 0 ? 0 : -1;
}

static int supervise_child(pid_t child, int pidfd, int sock, uint32_t admit_ms, uint32_t cleanup_ms,
			   const char *leaf, const char *prefix, char *accepted, size_t accepted_cap,
			   const struct admission_guard_ops *ops, struct admission_outcome *out)
{
	struct timespec deadline;

	if (clock_gettime(CLOCK_MONOTONIC, &deadline) != 0)
		return -1;
	guard_add_ms(&deadline, admit_ms);
	return admission_supervise(child, pidfd, sock, &deadline, cleanup_ms, leaf, prefix, accepted,
				   accepted_cap, ops, -1, out);
}

static void test_stale_receipt(void)
{
	char dir[] = "/tmp/mnemion-guard-receipt-XXXXXX";
	char path[PATH_MAX];
	char again[64];
	unsigned char body[32];
	unsigned char stale[32];
	int fd;
	ssize_t n;

	if (mkdtemp(dir) == NULL) {
		fail_setup("receipt temp dir");
		return;
	}
	if (snprintf(path, sizeof path, "%s/receipt.bin", dir) >= (int)sizeof path) {
		fail_setup("receipt path");
		remove_tree(dir);
		return;
	}
	memset(body, 0x11, sizeof body);
	memset(stale, 0x22, sizeof stale);
	fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0644);
	if (fd < 0) {
		fail_setup("seed stale file");
		remove_tree(dir);
		return;
	}
	if (write(fd, stale, sizeof stale) != (ssize_t)sizeof stale) {
		fail_setup("write stale bytes");
		close(fd);
		remove_tree(dir);
		return;
	}
	close(fd);
	expect(receipt_commit_exclusive(path, body, sizeof body, -1, -1) != 0, "existing path is refused");
	fd = open(path, O_RDONLY | O_CLOEXEC);
	n = fd >= 0 ? read(fd, again, sizeof again) : -1;
	if (fd >= 0)
		close(fd);
	expect(n == (ssize_t)sizeof stale && memcmp(again, stale, sizeof stale) == 0, "stale bytes stay");
	unlink(path);
	expect(receipt_commit_exclusive(path, body, sizeof body, -1, -1) == 0, "fresh exclusive commit");
	expect(receipt_commit_exclusive(path, body, sizeof body, -1, -1) != 0, "second commit is refused");
	unlink(path);
	rmdir(dir);
}

static void test_controller_loss(void)
{
	int sv[2];
	int park[2];
	int pidfd;
	pid_t child;
	struct admission_outcome out;
	struct admission_guard_ops ops;
	char accepted[PATH_MAX];

	if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, sv) != 0) {
		fail_setup("loss socket");
		return;
	}
	if (pipe2(park, O_CLOEXEC) != 0) {
		fail_setup("loss park");
		close(sv[0]);
		close(sv[1]);
		return;
	}
	child = fork();
	if (child < 0) {
		fail_setup("loss fork");
		close(sv[0]);
		close(sv[1]);
		close(park[0]);
		close(park[1]);
		return;
	}
	if (child == 0) {
		char byte = 0;
		close(sv[0]);
		close(park[1]);
		if (read(park[0], &byte, 1) != 1)
			_exit(1);
		_exit(9);
	}
	close(sv[1]);
	close(park[0]);
	pidfd = open_pidfd(child);
	if (pidfd < 0 || write(park[1], "g", 1) != 1) {
		fail_setup("loss pidfd");
		close(park[1]);
		stop_child(child);
		if (pidfd >= 0)
			close(pidfd);
		close(sv[0]);
		return;
	}
	close(park[1]);
	memset(&ops, 0, sizeof ops);
	ops.kill_write = kill_fail;
	ops.read_populated = populated_busy;
	ops.remove_leaf = remove_fail;
	memset(&out, 0, sizeof out);
	expect(supervise_child(child, pidfd, sv[0], 1000, 200, "leaf", "/tmp", accepted, sizeof accepted, &ops,
			       &out) == 0,
	       "loss supervise");
	expect(out.controller_lost == 1, "controller loss is not success");
	expect(out.have_result == 0, "lost controller has no result");
	expect(out.clone_permits == 0, "lost controller was not permitted to clone");
	release_handles(&out);
	close(pidfd);
	close(sv[0]);
}

static void test_blocked_and_eintr(void)
{
	int sv[2] = {-1, -1};
	int park[2] = {-1, -1};
	int hold[2] = {-1, -1};
	int life[2] = {-1, -1};
	int pidfd = -1;
	int noise_fd = -1;
	int parent_fd = -1;
	pid_t child = -1;
	pid_t noisemaker = -1;
	struct admission_outcome out;
	struct admission_guard_ops ops;
	struct timespec start;
	struct timespec end;
	struct itimerval tick;
	char accepted[PATH_MAX];
	int64_t elapsed_ms;

	if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, sv) != 0) {
		fail_setup("block socket");
		return;
	}
	if (pipe2(park, O_CLOEXEC) != 0) {
		fail_setup("block pipes");
		close_pair(sv);
		return;
	}
	if (pipe2(hold, O_CLOEXEC) != 0) {
		fail_setup("block pipes");
		close_pair(sv);
		close_pair(park);
		return;
	}
	if (pipe2(life, O_CLOEXEC) != 0) {
		fail_setup("block pipes");
		close_pair(sv);
		close_pair(park);
		close_pair(hold);
		return;
	}
	child = fork();
	if (child < 0) {
		fail_setup("block fork");
		close(sv[0]);
		close(sv[1]);
		close(park[0]);
		close(park[1]);
		close(hold[0]);
		close(hold[1]);
		close(life[0]);
		close(life[1]);
		return;
	}
	if (child == 0) {
		char byte = 0;
		close(sv[0]);
		close(park[1]);
		close(hold[1]);
		close(life[0]);
		close(life[1]);
		if (read(park[0], &byte, 1) != 1)
			_exit(1);
		if (read(hold[0], &byte, 1) < 0)
			_exit(1);
		_exit(0);
	}
	close(sv[1]);
	close(park[0]);
	close(hold[0]);
	pidfd = open_pidfd(child);
	if (pidfd < 0 || write(park[1], "g", 1) != 1) {
		fail_setup("block pidfd");
		close(park[1]);
		close(life[0]);
		close(life[1]);
		stop_child(child);
		if (pidfd >= 0)
			close(pidfd);
		close(sv[0]);
		close(hold[1]);
		return;
	}
	close(park[1]);
	signal(SIGALRM, ignore_signal);
	parent_fd = open_pidfd(getpid());
	if (parent_fd < 0) {
		fail_setup("block parent pidfd");
		close(life[0]);
		close(life[1]);
		stop_child(child);
		close(pidfd);
		close(sv[0]);
		close(hold[1]);
		return;
	}
	noisemaker = fork();
	if (noisemaker < 0) {
		fail_setup("block noisemaker");
		close(parent_fd);
		close(life[0]);
		close(life[1]);
		stop_child(child);
		close(pidfd);
		close(sv[0]);
		close(hold[1]);
		return;
	}
	if (noisemaker == 0) {
		struct pollfd pfds[2];

		close(life[1]);
		for (;;) {
			int rc;

			pfds[0].fd = life[0];
			pfds[0].events = POLLIN;
			pfds[1].fd = parent_fd;
			pfds[1].events = POLLIN;
			rc = poll(pfds, 2, 30);
			if (rc < 0 && errno == EINTR)
				continue;
			if (rc < 0)
				_exit(0);
			if (pfds[1].revents & (POLLIN | POLLERR | POLLHUP))
				_exit(0);
			if (pfds[0].revents & (POLLIN | POLLHUP | POLLERR)) {
				char byte = 0;
				if (read(life[0], &byte, 1) <= 0)
					_exit(0);
			}
			if (syscall(__NR_pidfd_send_signal, parent_fd, SIGALRM, NULL, 0) != 0)
				_exit(0);
		}
	}
	close(parent_fd);
	close(life[0]);
	noise_fd = open_pidfd(noisemaker);
	if (noise_fd < 0) {
		fail_setup("block noise pidfd");
		close(life[1]);
		stop_child(noisemaker);
		stop_child(child);
		close(pidfd);
		close(sv[0]);
		close(hold[1]);
		return;
	}
	memset(&tick, 0, sizeof tick);
	tick.it_interval.tv_usec = 30000;
	tick.it_value.tv_usec = 30000;
	setitimer(ITIMER_REAL, &tick, NULL);
	clock_gettime(CLOCK_MONOTONIC, &start);
	memset(&ops, 0, sizeof ops);
	ops.kill_write = kill_fail;
	ops.read_populated = populated_busy;
	ops.remove_leaf = remove_fail;
	expect(supervise_child(child, pidfd, sv[0], 200, 200, "leaf", "/tmp", accepted, sizeof accepted, &ops,
			       &out) == 0,
	       "blocked supervise");
	clock_gettime(CLOCK_MONOTONIC, &end);
	memset(&tick, 0, sizeof tick);
	setitimer(ITIMER_REAL, &tick, NULL);
	close(life[1]);
	if (noise_fd >= 0)
		syscall(__NR_pidfd_send_signal, noise_fd, SIGKILL, NULL, 0);
	reap_child_bounded(noisemaker);
	if (noise_fd >= 0)
		close(noise_fd);
	elapsed_ms = (int64_t)(end.tv_sec - start.tv_sec) * 1000 +
		     (int64_t)(end.tv_nsec - start.tv_nsec) / 1000000;
	expect(out.timed_out == 1, "blocked worker hits the admission deadline");
	expect(out.controller_signaled == 1 || out.controller_lost == 1, "blocked controller is stopped");
	expect(elapsed_ms < 1000, "EINTR does not extend the admission deadline");
	{
		pid_t got = waitpid(child, NULL, WNOHANG);
		expect(got < 0 && errno == ECHILD, "blocked controller is dead");
	}
	release_handles(&out);
	close(hold[1]);
	close(pidfd);
	close(sv[0]);
}

static void test_clone_without_custody(void)
{
	int sv[2] = {-1, -1};
	int park[2] = {-1, -1};
	int pidfd;
	pid_t child;
	struct admission_outcome out;
	struct admission_guard_ops ops;
	char accepted[PATH_MAX];
	struct timespec deadline;

	if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, sv) != 0) {
		fail_setup("clone setup");
		return;
	}
	if (pipe2(park, O_CLOEXEC) != 0) {
		fail_setup("clone setup");
		close_pair(sv);
		return;
	}
	child = fork();
	if (child < 0) {
		fail_setup("clone fork");
		close(sv[0]);
		close(sv[1]);
		close(park[0]);
		close(park[1]);
		return;
	}
	if (child == 0) {
		char byte = 0;
		uint32_t reply = 0;
		close(sv[0]);
		close(park[1]);
		if (read(park[0], &byte, 1) != 1)
			_exit(1);
		if (guard_send_simple(sv[1], GUARD_CLONE, 0) != 0)
			_exit(2);
		clock_gettime(CLOCK_MONOTONIC, &deadline);
		guard_add_ms(&deadline, 1000);
		if (guard_recv_reply(sv[1], &deadline, &reply) != 0 || reply != GUARD_CLONE_NO)
			_exit(3);
		_exit(0);
	}
	close(sv[1]);
	close(park[0]);
	pidfd = open_pidfd(child);
	if (pidfd < 0 || write(park[1], "g", 1) != 1) {
		fail_setup("clone pidfd");
		close(park[1]);
		stop_child(child);
		if (pidfd >= 0)
			close(pidfd);
		close(sv[0]);
		return;
	}
	close(park[1]);
	memset(&ops, 0, sizeof ops);
	ops.kill_write = kill_fail;
	ops.read_populated = populated_busy;
	ops.remove_leaf = remove_fail;
	expect(supervise_child(child, pidfd, sv[0], 1000, 200, "leaf", "/tmp", accepted, sizeof accepted, &ops,
			       &out) == 0,
	       "clone supervise");
	expect(out.clone_permits == 0, "clone without custody is not permitted");
	expect(out.controller_exited == 1 && out.controller_exit_code == 0, "deny was delivered");
	release_handles(&out);
	close(pidfd);
	close(sv[0]);
}

static void test_failed_cleanup_and_fd_survives(void)
{
	char dir[] = "/tmp/mnemion-guard-leaf-XXXXXX";
	char path[PATH_MAX];
	int sv[2] = {-1, -1};
	int park[2] = {-1, -1};
	int pidfd = -1;
	int dirfd;
	pid_t child = -1;
	struct admission_outcome out;
	struct admission_guard_ops ops;
	char accepted[PATH_MAX];
	int kill_hits = 0;
	struct timespec deadline;

	if (mkdtemp(dir) == NULL) {
		fail_setup("leaf temp dir");
		return;
	}
	if (snprintf(path, sizeof path, "%s/leaf", dir) >= (int)sizeof path) {
		fail_setup("leaf path");
		remove_tree(dir);
		return;
	}
	if (mkdir(path, 0700) != 0) {
		fail_setup("leaf mkdir");
		remove_tree(dir);
		return;
	}
	if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, sv) != 0) {
		fail_setup("fd socket");
		remove_tree(dir);
		return;
	}
	if (pipe2(park, O_CLOEXEC) != 0) {
		fail_setup("fd park");
		close_pair(sv);
		remove_tree(dir);
		return;
	}
	child = fork();
	if (child < 0) {
		fail_setup("fd fork");
		close_pair(sv);
		close_pair(park);
		remove_tree(dir);
		return;
	}
	if (child == 0) {
		char byte = 0;
		uint32_t reply = 0;
		int fd;
		close(sv[0]);
		close(park[1]);
		if (read(park[0], &byte, 1) != 1)
			_exit(1);
		if (guard_send_path(sv[1], path) != 0)
			_exit(2);
		clock_gettime(CLOCK_MONOTONIC, &deadline);
		guard_add_ms(&deadline, 1000);
		if (guard_recv_reply(sv[1], &deadline, &reply) != 0 || reply != GUARD_PATH_OK)
			_exit(3);
		fd = open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
		if (fd < 0 || guard_send_fd(sv[1], fd) != 0)
			_exit(4);
		close(fd);
		clock_gettime(CLOCK_MONOTONIC, &deadline);
		guard_add_ms(&deadline, 1000);
		if (guard_recv_reply(sv[1], &deadline, &reply) != 0 || reply != GUARD_CUSTODY_OK)
			_exit(5);
		raise(SIGKILL);
		_exit(6);
	}
	close(sv[1]);
	sv[1] = -1;
	close(park[0]);
	park[0] = -1;
	pidfd = open_pidfd(child);
	if (pidfd < 0 || write(park[1], "g", 1) != 1) {
		fail_setup("fd pidfd");
		close(park[1]);
		stop_child(child);
		if (pidfd >= 0)
			close(pidfd);
		close(sv[0]);
		remove_tree(dir);
		return;
	}
	close(park[1]);
	memset(&ops, 0, sizeof ops);
	ops.kill_write = kill_fail;
	ops.read_populated = populated_busy;
	ops.remove_leaf = remove_fail;
	ops.ctx = &kill_hits;
	expect(supervise_child(child, pidfd, sv[0], 1000, 300, "leaf", dir, accepted, sizeof accepted, &ops,
			       &out) == 0,
	       "failed cleanup supervise");
	expect(out.controller_lost == 1, "SIGKILL is controller loss");
	expect(out.custody_held == 1, "custody was acknowledged");
	expect(out.cleanup_confirmed == 0, "failed kill is not confirmed cleanup");
	dirfd = open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
	expect(dirfd >= 0, "failed cleanup leaves the directory");
	if (dirfd >= 0)
		close(dirfd);
	release_handles(&out);
	close(pidfd);
	close(sv[0]);
	sv[0] = sv[1] = -1;
	park[0] = park[1] = -1;
	pidfd = -1;
	child = -1;

	if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, sv) != 0) {
		fail_setup("survive socket");
		remove_tree(dir);
		return;
	}
	if (pipe2(park, O_CLOEXEC) != 0) {
		fail_setup("survive park");
		close_pair(sv);
		remove_tree(dir);
		return;
	}
	child = fork();
	if (child < 0) {
		fail_setup("survive fork");
		close_pair(sv);
		close_pair(park);
		remove_tree(dir);
		return;
	}
	if (child == 0) {
		char byte = 0;
		uint32_t reply = 0;
		int fd;
		close(sv[0]);
		close(park[1]);
		if (read(park[0], &byte, 1) != 1)
			_exit(1);
		if (guard_send_path(sv[1], path) != 0)
			_exit(2);
		clock_gettime(CLOCK_MONOTONIC, &deadline);
		guard_add_ms(&deadline, 1000);
		if (guard_recv_reply(sv[1], &deadline, &reply) != 0 || reply != GUARD_PATH_OK)
			_exit(3);
		fd = open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
		if (fd < 0 || guard_send_fd(sv[1], fd) != 0)
			_exit(4);
		close(fd);
		clock_gettime(CLOCK_MONOTONIC, &deadline);
		guard_add_ms(&deadline, 1000);
		if (guard_recv_reply(sv[1], &deadline, &reply) != 0 || reply != GUARD_CUSTODY_OK)
			_exit(5);
		raise(SIGKILL);
		_exit(6);
	}
	close(sv[1]);
	sv[1] = -1;
	close(park[0]);
	park[0] = -1;
	pidfd = open_pidfd(child);
	if (pidfd < 0 || write(park[1], "g", 1) != 1) {
		fail_setup("survive pidfd");
		close(park[1]);
		stop_child(child);
		if (pidfd >= 0)
			close(pidfd);
		close(sv[0]);
		remove_tree(dir);
		return;
	}
	close(park[1]);
	memset(&ops, 0, sizeof ops);
	kill_hits = 0;
	ops.kill_write = kill_fstat;
	ops.read_populated = populated_empty;
	ops.remove_leaf = remove_rmdir;
	ops.ctx = path;
	expect(supervise_child(child, pidfd, sv[0], 1000, 500, "leaf", dir, accepted, sizeof accepted, &ops,
			       &out) == 0,
	       "survive supervise");
	/* kill_fstat's ctx is the path, so it must not write an int through it.
	 * The directory fd is fstat'd inside that callback after the controller
	 * is dead. Removal of this temp directory is not cgroup.kill evidence.
	 */
	expect(out.custody_held == 1, "directory fd was accepted");
	expect(out.controller_lost == 1, "dead controller stays a failure");
	expect(out.cleanup_confirmed == 1, "temp directory removal was confirmed");
	expect(access(path, F_OK) != 0, "temp leaf was removed");
	release_handles(&out);
	close(pidfd);
	close(sv[0]);
	rmdir(dir);
}

static void test_unowned_path_is_not_killed(void)
{
	char dir[] = "/tmp/mnemion-guard-unowned-XXXXXX";
	char path[PATH_MAX];
	int sv[2] = {-1, -1};
	int park[2] = {-1, -1};
	int pidfd = -1;
	int mark_pipe[2] = {-1, -1};
	struct mark_obs mark;
	pid_t child = -1;
	struct admission_outcome out;
	struct admission_guard_ops ops;
	char accepted[PATH_MAX];
	struct timespec deadline;

	if (mkdtemp(dir) == NULL) {
		fail_setup("unowned temp");
		return;
	}
	if (snprintf(path, sizeof path, "%s/leaf", dir) >= (int)sizeof path || mkdir(path, 0700) != 0) {
		fail_setup("unowned path");
		remove_tree(dir);
		return;
	}
	if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, sv) != 0) {
		fail_setup("unowned socket");
		remove_tree(dir);
		return;
	}
	if (pipe2(park, O_CLOEXEC) != 0) {
		fail_setup("unowned park");
		close_pair(sv);
		remove_tree(dir);
		return;
	}
	child = fork();
	if (child < 0) {
		fail_setup("unowned fork");
		close_pair(sv);
		close_pair(park);
		remove_tree(dir);
		return;
	}
	if (child == 0) {
		char byte = 0;
		uint32_t reply = 0;
		close(sv[0]);
		close(park[1]);
		if (read(park[0], &byte, 1) != 1)
			_exit(1);
		if (guard_send_path(sv[1], path) != 0)
			_exit(2);
		clock_gettime(CLOCK_MONOTONIC, &deadline);
		guard_add_ms(&deadline, 1000);
		if (guard_recv_reply(sv[1], &deadline, &reply) != 0 || reply != GUARD_PATH_OK)
			_exit(3);
		_exit(0);
	}
	close(sv[1]);
	close(park[0]);
	pidfd = open_pidfd(child);
	if (pidfd < 0 || write(park[1], "g", 1) != 1) {
		fail_setup("unowned pidfd");
		close(park[1]);
		stop_child(child);
		if (pidfd >= 0)
			close(pidfd);
		close(sv[0]);
		remove_tree(dir);
		return;
	}
	close(park[1]);
	memset(&ops, 0, sizeof ops);
	memset(&out, 0, sizeof out);
	if (pipe2(mark_pipe, O_CLOEXEC) != 0) {
		fail_setup("unowned mark pipe");
		stop_child(child);
		close(pidfd);
		close(sv[0]);
		remove_tree(dir);
		return;
	}
	if (fcntl(mark_pipe[0], F_SETFL, O_NONBLOCK) != 0) {
		fail_setup("unowned mark nonblock");
		close(mark_pipe[0]);
		close(mark_pipe[1]);
		stop_child(child);
		close(pidfd);
		close(sv[0]);
		remove_tree(dir);
		return;
	}
	mark.write_fd = mark_pipe[1];
	ops.kill_write = kill_mark;
	ops.read_populated = populated_empty;
	ops.remove_leaf = remove_fail;
	ops.ctx = &mark;
	expect(supervise_child(child, pidfd, sv[0], 1000, 300, "leaf", dir, accepted, sizeof accepted, &ops,
			       &out) == 0,
	       "unowned supervise");
	{
		char byte = 0;
		ssize_t saw = read(mark_pipe[0], &byte, 1);
		expect(saw < 0 && errno == EAGAIN, "proposed path is not killed");
	}
	close(mark_pipe[0]);
	close(mark_pipe[1]);
	expect(out.owned_directory == 0, "proposed path is not owned");
	expect(out.cleanup_confirmed == 0, "unowned path is not confirmed cleanup");
	expect(access(path, F_OK) == 0, "pre-existing directory remains");
	release_handles(&out);
	close(pidfd);
	close(sv[0]);
	rmdir(path);
	rmdir(dir);
}

static void test_cleanup_expiry_returns(void)
{
	char dir[] = "/tmp/mnemion-guard-expire-XXXXXX";
	char path[PATH_MAX];
	int sv[2] = {-1, -1};
	int park[2] = {-1, -1};
	int pidfd = -1;
	pid_t child = -1;
	struct admission_outcome out;
	struct admission_guard_ops ops;
	char accepted[PATH_MAX];
	struct timespec deadline;
	struct timespec start;
	struct timespec end;
	int64_t elapsed_ms;

	if (mkdtemp(dir) == NULL) {
		fail_setup("expire temp");
		return;
	}
	if (snprintf(path, sizeof path, "%s/leaf", dir) >= (int)sizeof path || mkdir(path, 0700) != 0) {
		fail_setup("expire path");
		remove_tree(dir);
		return;
	}
	if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, sv) != 0) {
		fail_setup("expire socket");
		remove_tree(dir);
		return;
	}
	if (pipe2(park, O_CLOEXEC) != 0) {
		fail_setup("expire park");
		close_pair(sv);
		remove_tree(dir);
		return;
	}
	child = fork();
	if (child < 0) {
		fail_setup("expire fork");
		close_pair(sv);
		close_pair(park);
		remove_tree(dir);
		return;
	}
	if (child == 0) {
		char byte = 0;
		uint32_t reply = 0;
		int fd;
		close(sv[0]);
		close(park[1]);
		if (read(park[0], &byte, 1) != 1)
			_exit(1);
		if (guard_send_path(sv[1], path) != 0)
			_exit(2);
		clock_gettime(CLOCK_MONOTONIC, &deadline);
		guard_add_ms(&deadline, 1000);
		if (guard_recv_reply(sv[1], &deadline, &reply) != 0 || reply != GUARD_PATH_OK)
			_exit(3);
		fd = open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
		if (fd < 0 || guard_send_fd(sv[1], fd) != 0)
			_exit(4);
		close(fd);
		clock_gettime(CLOCK_MONOTONIC, &deadline);
		guard_add_ms(&deadline, 1000);
		if (guard_recv_reply(sv[1], &deadline, &reply) != 0 || reply != GUARD_CUSTODY_OK)
			_exit(5);
		for (;;)
			pause();
	}
	close(sv[1]);
	close(park[0]);
	pidfd = open_pidfd(child);
	if (pidfd < 0 || write(park[1], "g", 1) != 1) {
		fail_setup("expire pidfd");
		close(park[1]);
		stop_child(child);
		if (pidfd >= 0)
			close(pidfd);
		close(sv[0]);
		remove_tree(dir);
		return;
	}
	close(park[1]);
	memset(&ops, 0, sizeof ops);
	memset(&out, 0, sizeof out);
	ops.kill_write = kill_pause;
	ops.read_populated = populated_empty;
	ops.remove_leaf = remove_fail;
	clock_gettime(CLOCK_MONOTONIC, &start);
	expect(supervise_child(child, pidfd, sv[0], 300, 250, "leaf", dir, accepted, sizeof accepted, &ops,
			       &out) == 0,
	       "expire supervise");
	clock_gettime(CLOCK_MONOTONIC, &end);
	elapsed_ms = (int64_t)(end.tv_sec - start.tv_sec) * 1000 +
		     (int64_t)(end.tv_nsec - start.tv_nsec) / 1000000;
	/* pause() can be killed. This does not show that D-state work finishes. */
	expect(elapsed_ms < 2000, "cleanup deadline returns");
	expect(out.timed_out == 1, "admission deadline is recorded");
	expect(out.cleanup_confirmed == 0, "expired cleanup is not confirmed");
	expect(access(path, F_OK) == 0, "blocked cleanup leaves the directory");
	/* The guardian already signaled through the pidfd it still holds.
	 * Do not signal the historical pid after that descriptor is closed.
	 */
	release_handles(&out);
	close(pidfd);
	close(sv[0]);
	rmdir(path);
	rmdir(dir);
}

static void test_watched_worker(int adopt, int expect_confirm)
{
	char dir[] = "/tmp/mnemion-guard-watch-XXXXXX";
	char path[PATH_MAX];
	int sv[2] = {-1, -1};
	int park[2] = {-1, -1};
	int pidfd = -1;
	pid_t child = -1;
	struct admission_outcome out;
	struct admission_guard_ops ops;
	char accepted[PATH_MAX];
	struct timespec deadline;
	int armed = 0;

	if (adopt) {
		if (prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0) {
			fail_setup("subreaper");
			return;
		}
		armed = 1;
	} else if (prctl(PR_SET_CHILD_SUBREAPER, 0, 0, 0, 0) != 0) {
		fail_setup("subreaper");
		return;
	}
	if (mkdtemp(dir) == NULL) {
		fail_setup("watch temp");
		if (armed && prctl(PR_SET_CHILD_SUBREAPER, 0, 0, 0, 0) != 0)
			fail_setup("subreaper clear");
		return;
	}
	if (snprintf(path, sizeof path, "%s/leaf", dir) >= (int)sizeof path || mkdir(path, 0700) != 0) {
		fail_setup("watch path");
		remove_tree(dir);
		if (armed && prctl(PR_SET_CHILD_SUBREAPER, 0, 0, 0, 0) != 0)
			fail_setup("subreaper clear");
		return;
	}
	if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, sv) != 0) {
		fail_setup("watch socket");
		remove_tree(dir);
		if (armed && prctl(PR_SET_CHILD_SUBREAPER, 0, 0, 0, 0) != 0)
			fail_setup("subreaper clear");
		return;
	}
	if (pipe2(park, O_CLOEXEC) != 0) {
		fail_setup("watch park");
		close_pair(sv);
		remove_tree(dir);
		if (armed && prctl(PR_SET_CHILD_SUBREAPER, 0, 0, 0, 0) != 0)
			fail_setup("subreaper clear");
		return;
	}
	child = fork();
	if (child < 0) {
		fail_setup("watch fork");
		close_pair(sv);
		close_pair(park);
		remove_tree(dir);
		if (armed && prctl(PR_SET_CHILD_SUBREAPER, 0, 0, 0, 0) != 0)
			fail_setup("subreaper clear");
		return;
	}
	if (child == 0) {
		char byte = 0;
		uint32_t reply = 0;
		int fd;
		pid_t grand;
		close(sv[0]);
		close(park[1]);
		if (read(park[0], &byte, 1) != 1)
			_exit(1);
		grand = fork();
		if (grand < 0)
			_exit(2);
		if (grand == 0) {
			for (;;)
				pause();
		}
		if (guard_send_simple(sv[1], GUARD_WATCH, grand) != 0)
			_exit(3);
		clock_gettime(CLOCK_MONOTONIC, &deadline);
		guard_add_ms(&deadline, 1000);
		if (guard_recv_reply(sv[1], &deadline, &reply) != 0 || reply != GUARD_WATCH_OK)
			_exit(4);
		if (guard_send_path(sv[1], path) != 0)
			_exit(5);
		clock_gettime(CLOCK_MONOTONIC, &deadline);
		guard_add_ms(&deadline, 1000);
		if (guard_recv_reply(sv[1], &deadline, &reply) != 0 || reply != GUARD_PATH_OK)
			_exit(6);
		fd = open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
		if (fd < 0 || guard_send_fd(sv[1], fd) != 0)
			_exit(7);
		close(fd);
		clock_gettime(CLOCK_MONOTONIC, &deadline);
		guard_add_ms(&deadline, 1000);
		if (guard_recv_reply(sv[1], &deadline, &reply) != 0 || reply != GUARD_CUSTODY_OK)
			_exit(8);
		_exit(0);
	}
	close(sv[1]);
	close(park[0]);
	pidfd = open_pidfd(child);
	if (pidfd < 0 || write(park[1], "g", 1) != 1) {
		fail_setup("watch pidfd");
		close(park[1]);
		stop_child(child);
		if (pidfd >= 0)
			close(pidfd);
		close(sv[0]);
		remove_tree(dir);
		if (armed && prctl(PR_SET_CHILD_SUBREAPER, 0, 0, 0, 0) != 0)
			fail_setup("subreaper clear");
		return;
	}
	close(park[1]);
	memset(&ops, 0, sizeof ops);
	memset(&out, 0, sizeof out);
	ops.kill_write = kill_fstat;
	ops.read_populated = populated_empty;
	ops.remove_leaf = remove_rmdir;
	ops.ctx = path;
	expect(supervise_child(child, pidfd, sv[0], 1000, adopt ? 1000 : 300, "leaf", dir, accepted,
			       sizeof accepted, &ops, &out) == 0,
	       "watch supervise");
	expect(out.owned_watched > 0, "watched worker identity is kept");
	if (expect_confirm) {
		expect(out.unreaped_watched == 0, "adopted watcher is reaped");
		expect(out.cleanup_confirmed == 1, "cleanup waits for the watcher");
		expect(access(path, F_OK) != 0, "owned temp leaf removed");
	} else {
		expect(out.unreaped_watched > 0, "unadopted watcher stays unreaped");
		expect(out.cleanup_confirmed == 0, "unreaped watcher is not confirmed cleanup");
		expect(out.reap_unconfirmed == 1, "deadline records unconfirmed reap");
	}
	release_handles(&out);
	close(pidfd);
	close(sv[0]);
	rmdir(path);
	rmdir(dir);
	if (armed && prctl(PR_SET_CHILD_SUBREAPER, 0, 0, 0, 0) != 0)
		fail_setup("subreaper clear");
}

static void test_publication_deadline(void)
{
	char dir[] = "/tmp/mnemion-guard-publish-XXXXXX";
	char path[PATH_MAX];
	char stale_path[PATH_MAX];
	unsigned char body[32];
	unsigned char stale[32];
	unsigned char again[64];
	struct timespec deadline;
	struct timespec start;
	struct timespec end;
	pid_t unreaped = 0;
	int stall[2] = {-1, -1};
	int fd = -1;
	ssize_t n;
	int64_t elapsed_ms;

	if (mkdtemp(dir) == NULL) {
		fail_setup("publish temp");
		return;
	}
	if (snprintf(path, sizeof path, "%s/receipt.bin", dir) >= (int)sizeof path) {
		fail_setup("publish path");
		remove_tree(dir);
		return;
	}
	memset(body, 0x41, sizeof body);
	if (clock_gettime(CLOCK_MONOTONIC, &deadline) != 0) {
		fail_setup("publish clock");
		remove_tree(dir);
		return;
	}
	deadline.tv_sec -= 5;
	expect(receipt_publish_supervised(path, body, sizeof body, &deadline, -1, -1, &unreaped) != 0,
	       "expired publish fails");
	expect(access(path, F_OK) != 0, "expired publish creates nothing");
	if (snprintf(stale_path, sizeof stale_path, "%s/stale.bin", dir) >= (int)sizeof stale_path) {
		fail_setup("publish stale path");
		remove_tree(dir);
		return;
	}
	memset(stale, 0x42, sizeof stale);
	fd = open(stale_path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0644);
	if (fd < 0) {
		fail_setup("seed publish stale");
		remove_tree(dir);
		return;
	}
	if (write(fd, stale, sizeof stale) != (ssize_t)sizeof stale) {
		fail_setup("write publish stale");
		close(fd);
		unlink(stale_path);
		remove_tree(dir);
		return;
	}
	close(fd);
	fd = -1;
	if (clock_gettime(CLOCK_MONOTONIC, &deadline) != 0) {
		fail_setup("publish clock");
		unlink(stale_path);
		remove_tree(dir);
		return;
	}
	guard_add_ms(&deadline, 1000);
	expect(receipt_publish_supervised(stale_path, body, sizeof body, &deadline, -1, -1, &unreaped) != 0,
	       "existing publish fails");
	fd = open(stale_path, O_RDONLY | O_CLOEXEC);
	n = fd >= 0 ? read(fd, again, sizeof again) : -1;
	if (fd >= 0)
		close(fd);
	expect(n == (ssize_t)sizeof stale && memcmp(again, stale, sizeof stale) == 0, "publish stale bytes stay");
	if (pipe2(stall, O_CLOEXEC) != 0) {
		fail_setup("publish stall");
		unlink(path);
		unlink(stale_path);
		remove_tree(dir);
		return;
	}
	if (clock_gettime(CLOCK_MONOTONIC, &start) != 0 || clock_gettime(CLOCK_MONOTONIC, &deadline) != 0) {
		fail_setup("publish clock");
		close_pair(stall);
		unlink(stale_path);
		remove_tree(dir);
		return;
	}
	guard_add_ms(&deadline, 200);
	expect(receipt_publish_supervised(path, body, sizeof body, &deadline, stall[0], -1, &unreaped) != 0,
	       "stalled pre-publication inspection fails");
	if (clock_gettime(CLOCK_MONOTONIC, &end) != 0) {
		fail_setup("publish clock");
	} else {
		elapsed_ms = (int64_t)(end.tv_sec - start.tv_sec) * 1000 +
			     (int64_t)(end.tv_nsec - start.tv_nsec) / 1000000;
		expect(elapsed_ms < 1500, "stalled publish returns at the deadline");
	}
	expect(access(path, F_OK) != 0, "stalled publish leaves no receipt");
	close(stall[0]);
	close(stall[1]);
	stall[0] = stall[1] = -1;
	if (unreaped > 0) {
		/* Our child, if it is already a zombie. Do not signal a pid whose pidfd is closed. */
		reap_child_bounded(unreaped);
	}
	if (clock_gettime(CLOCK_MONOTONIC, &deadline) != 0) {
		fail_setup("publish clock");
		unlink(stale_path);
		remove_tree(dir);
		return;
	}
	guard_add_ms(&deadline, 2000);
	unreaped = 0;
	expect(receipt_publish_supervised(path, body, sizeof body, &deadline, -1, -1, &unreaped) == 0,
	       "publish inside the deadline");
	expect(unreaped == 0, "publisher reaped");
	unlink(path);
	unlink(stale_path);
	rmdir(dir);
}

static void disarm_subreaper(void)
{
	if (prctl(PR_SET_CHILD_SUBREAPER, 0, 0, 0, 0) != 0)
		fail_setup("subreaper clear");
}

static void test_normal_observe_reap(void)
{
	char dir[] = "/tmp/mnemion-guard-reap-XXXXXX";
	char path[PATH_MAX];
	int sv[2] = {-1, -1};
	int park[2] = {-1, -1};
	int pidfd = -1;
	pid_t child = -1;
	struct admission_outcome out;
	struct admission_guard_ops ops;
	char accepted[PATH_MAX];

	if (prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0) {
		fail_setup("reap subreaper");
		return;
	}
	if (mkdtemp(dir) == NULL) {
		fail_setup("reap temp");
		disarm_subreaper();
		return;
	}
	if (snprintf(path, sizeof path, "%s/leaf", dir) >= (int)sizeof path || mkdir(path, 0700) != 0) {
		fail_setup("reap path");
		remove_tree(dir);
		disarm_subreaper();
		return;
	}
	if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, sv) != 0) {
		fail_setup("reap socket");
		remove_tree(dir);
		disarm_subreaper();
		return;
	}
	if (pipe2(park, O_CLOEXEC) != 0) {
		fail_setup("reap park");
		close_pair(sv);
		remove_tree(dir);
		disarm_subreaper();
		return;
	}
	child = fork();
	if (child < 0) {
		fail_setup("reap fork");
		close_pair(sv);
		close_pair(park);
		remove_tree(dir);
		disarm_subreaper();
		return;
	}
	if (child == 0) {
		char byte = 0;
		uint32_t reply = 0;
		int fd;
		int gate[2] = {-1, -1};
		pid_t grand;
		int status = -1;
		struct timespec dl;

		close(sv[0]);
		close(park[1]);
		if (read(park[0], &byte, 1) != 1)
			_exit(1);
		if (pipe2(gate, O_CLOEXEC) != 0)
			_exit(2);
		grand = fork();
		if (grand < 0)
			_exit(2);
		if (grand == 0) {
			char go = 0;

			close(gate[1]);
			if (read(gate[0], &go, 1) != 1)
				_exit(1);
			_exit(0);
		}
		close(gate[0]);
		if (guard_send_simple(sv[1], GUARD_WATCH, grand) != 0)
			_exit(3);
		if (clock_gettime(CLOCK_MONOTONIC, &dl) != 0)
			_exit(3);
		guard_add_ms(&dl, 1000);
		if (guard_recv_reply(sv[1], &dl, &reply) != 0 || reply != GUARD_WATCH_OK)
			_exit(4);
		if (write(gate[1], "g", 1) != 1)
			_exit(5);
		close(gate[1]);
		if (clock_gettime(CLOCK_MONOTONIC, &dl) != 0)
			_exit(6);
		guard_add_ms(&dl, 1000);
		if (guard_observe_exit(grand, &status, &dl) != 0 || !WIFEXITED(status) || WEXITSTATUS(status) != 0)
			_exit(6);
		if (guard_observe_exit(grand, &status, &dl) != 0 || !WIFEXITED(status) || WEXITSTATUS(status) != 0)
			_exit(7);
		if (guard_send_path(sv[1], path) != 0)
			_exit(8);
		if (clock_gettime(CLOCK_MONOTONIC, &dl) != 0)
			_exit(8);
		guard_add_ms(&dl, 1000);
		if (guard_recv_reply(sv[1], &dl, &reply) != 0 || reply != GUARD_PATH_OK)
			_exit(9);
		fd = open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
		if (fd < 0 || guard_send_fd(sv[1], fd) != 0)
			_exit(10);
		close(fd);
		if (clock_gettime(CLOCK_MONOTONIC, &dl) != 0)
			_exit(10);
		guard_add_ms(&dl, 1000);
		if (guard_recv_reply(sv[1], &dl, &reply) != 0 || reply != GUARD_CUSTODY_OK)
			_exit(11);
		_exit(0);
	}
	close(sv[1]);
	close(park[0]);
	pidfd = open_pidfd(child);
	if (pidfd < 0 || write(park[1], "g", 1) != 1) {
		fail_setup("reap pidfd");
		close(park[1]);
		stop_child(child);
		if (pidfd >= 0)
			close(pidfd);
		close(sv[0]);
		remove_tree(dir);
		disarm_subreaper();
		return;
	}
	close(park[1]);
	memset(&ops, 0, sizeof ops);
	memset(&out, 0, sizeof out);
	ops.kill_write = kill_fstat;
	ops.read_populated = populated_empty;
	ops.remove_leaf = remove_rmdir;
	ops.ctx = path;
	expect(supervise_child(child, pidfd, sv[0], 1500, 1000, "leaf", dir, accepted, sizeof accepted, &ops,
			       &out) == 0,
	       "normal observe supervise");
	expect(out.controller_exited == 1 && out.controller_exit_code == 0, "parent observed without reaping");
	expect(out.owned_watched > 0, "observed child was watched");
	expect(out.unreaped_watched == 0, "guardian reaped the observed child");
	expect(out.cleanup_confirmed == 1, "normal teardown completed");
	expect(out.adopted_unresolved == 0, "normal reap left no unresolved child");
	expect(out.reap_unconfirmed == 0, "normal reap was confirmed");
	expect(access(path, F_OK) != 0, "normal teardown removed the leaf");
	release_handles(&out);
	close(pidfd);
	close(sv[0]);
	remove_tree(dir);
	disarm_subreaper();
}

static void test_unreported_preflight(void)
{
	int sv[2] = {-1, -1};
	int park[2] = {-1, -1};
	int idp[2] = {-1, -1};
	int pidfd = -1;
	pid_t child = -1;
	pid_t pre = -1;
	struct admission_outcome out;
	struct admission_guard_ops ops;
	char accepted[PATH_MAX];
	ssize_t n;

	if (prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0) {
		fail_setup("preflight subreaper");
		return;
	}
	if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, sv) != 0) {
		fail_setup("preflight socket");
		disarm_subreaper();
		return;
	}
	if (pipe2(park, O_CLOEXEC) != 0) {
		fail_setup("preflight park");
		close_pair(sv);
		disarm_subreaper();
		return;
	}
	if (pipe2(idp, O_CLOEXEC) != 0) {
		fail_setup("preflight id");
		close_pair(sv);
		close_pair(park);
		disarm_subreaper();
		return;
	}
	child = fork();
	if (child < 0) {
		fail_setup("preflight fork");
		close_pair(sv);
		close_pair(park);
		close_pair(idp);
		disarm_subreaper();
		return;
	}
	if (child == 0) {
		char byte = 0;
		int ready[2] = {-1, -1};
		pid_t grand;
		pid_t parent;

		close(sv[0]);
		close(park[1]);
		close(idp[0]);
		if (read(park[0], &byte, 1) != 1)
			_exit(1);
		if (pipe2(ready, O_CLOEXEC) != 0)
			_exit(2);
		grand = fork();
		if (grand < 0)
			_exit(2);
		if (grand == 0) {
			close(ready[0]);
			parent = getppid();
			if (prctl(PR_SET_PDEATHSIG, SIGKILL) != 0 || getppid() != parent)
				_exit(127);
			if (write(ready[1], "r", 1) != 1)
				_exit(127);
			close(ready[1]);
			for (;;)
				pause();
		}
		close(ready[1]);
		if (read(ready[0], &byte, 1) != 1)
			_exit(2);
		close(ready[0]);
		if (write(idp[1], &grand, sizeof grand) != (ssize_t)sizeof grand)
			_exit(3);
		close(idp[1]);
		raise(SIGKILL);
		_exit(4);
	}
	close(sv[1]);
	close(park[0]);
	close(idp[1]);
	pidfd = open_pidfd(child);
	if (pidfd < 0 || write(park[1], "g", 1) != 1) {
		fail_setup("preflight pidfd");
		close(park[1]);
		close(idp[0]);
		stop_child(child);
		if (pidfd >= 0)
			close(pidfd);
		close(sv[0]);
		disarm_subreaper();
		return;
	}
	close(park[1]);
	memset(&ops, 0, sizeof ops);
	memset(&out, 0, sizeof out);
	ops.kill_write = kill_fail;
	ops.read_populated = populated_busy;
	ops.remove_leaf = remove_fail;
	expect(supervise_child(child, pidfd, sv[0], 1000, 800, "leaf", "/tmp", accepted, sizeof accepted, &ops,
			       &out) == 0,
	       "preflight supervise");
	n = read(idp[0], &pre, sizeof pre);
	expect(n == (ssize_t)sizeof pre && pre > 0, "preflight identity was recorded");
	expect(out.controller_lost == 1, "lost controller is a failed teardown");
	expect(out.have_result == 0, "unreported preflight has no result");
	expect(out.owned_watched == 0, "preflight was not watched");
	expect(out.cleanup_confirmed == 0, "unreported preflight is not confirmed cleanup");
	expect(out.adopted_unresolved == 0, "adopted preflight was resolved");
	expect(out.unreaped_adopted_count == 0, "adopted preflight was not left listed");
	expect(out.reap_unconfirmed == 0, "adopted preflight was reaped");
	if (pre > 0) {
		pid_t got = waitpid(pre, NULL, WNOHANG);

		expect(got < 0 && errno == ECHILD, "preflight is not still our child");
		if (got >= 0)
			stop_child(pre);
	}
	{
		pid_t extra = waitpid(-1, NULL, WNOHANG);

		expect(extra < 0 && errno == ECHILD, "no child remains after preflight");
		if (extra > 0)
			stop_child(extra);
	}
	release_handles(&out);
	close(pidfd);
	close(sv[0]);
	close(idp[0]);
	disarm_subreaper();
}

static void test_absence_inspection(void)
{
	char dir[] = "/tmp/mnemion-guard-absent-XXXXXX";
	char path[PATH_MAX];
	char blocked[PATH_MAX];
	struct timespec deadline;
	pid_t unreaped = 0;
	int fd = -1;
	unsigned char byte = 0x5a;

	if (mkdtemp(dir) == NULL) {
		fail_setup("absent temp");
		return;
	}
	if (snprintf(path, sizeof path, "%s/receipt.bin", dir) >= (int)sizeof path) {
		fail_setup("absent path");
		remove_tree(dir);
		return;
	}
	if (clock_gettime(CLOCK_MONOTONIC, &deadline) != 0) {
		fail_setup("absent clock");
		remove_tree(dir);
		return;
	}
	guard_add_ms(&deadline, 1000);
	expect(receipt_confirm_absent(path, &deadline, &unreaped) == 0, "missing path is absence");
	expect(unreaped == 0, "absence inspector reaped");
	fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0644);
	if (fd < 0 || write(fd, &byte, 1) != 1) {
		fail_setup("absent seed");
		if (fd >= 0)
			close(fd);
		remove_tree(dir);
		return;
	}
	close(fd);
	if (clock_gettime(CLOCK_MONOTONIC, &deadline) != 0) {
		fail_setup("absent clock");
		remove_tree(dir);
		return;
	}
	guard_add_ms(&deadline, 1000);
	unreaped = 0;
	expect(receipt_confirm_absent(path, &deadline, &unreaped) == -2, "present path is not absence");
	expect(unreaped == 0, "present inspector reaped");
	expect(access(path, F_OK) == 0, "present file stays");
	if (snprintf(blocked, sizeof blocked, "%s/receipt.bin/extra", dir) >= (int)sizeof blocked) {
		fail_setup("absent notdir");
		remove_tree(dir);
		return;
	}
	if (clock_gettime(CLOCK_MONOTONIC, &deadline) != 0) {
		fail_setup("absent clock");
		remove_tree(dir);
		return;
	}
	guard_add_ms(&deadline, 1000);
	unreaped = 0;
	expect(receipt_confirm_absent(blocked, &deadline, &unreaped) == -1, "lookup failure is not absence");
	deadline.tv_sec -= 5;
	unreaped = 0;
	expect(receipt_confirm_absent(path, &deadline, &unreaped) == -1, "expired absence is unconfirmed");
	unlink(path);
	remove_tree(dir);
}

struct phase_plan {
	const char *path;
	const unsigned char *body;
	size_t body_len;
	int create_at_c;
	unsigned char competitor_byte;
	int replace_at_u;
	unsigned char replacement_byte;
	int release_u;
	int release_p;
	char stall_phase;
	uint32_t deadline_ms;
	const char *what;
	const unsigned char *remain;
};

static int write_byte(int fd, char byte)
{
	for (;;) {
		ssize_t n = write(fd, &byte, 1);

		if (n == 1)
			return 0;
		if (n < 0 && errno == EINTR)
			continue;
		return -1;
	}
}

static int read_phase(int fd, const struct timespec *deadline, char *out)
{
	for (;;) {
		struct pollfd pfd;
		int remain = 0;
		char byte = 0;
		ssize_t n;
		int rc;

		if (guard_remaining_ms(deadline, &remain) != 0)
			return -1;
		pfd.fd = fd;
		pfd.events = POLLIN;
		rc = poll(&pfd, 1, remain > 50 ? 50 : remain);
		if (rc < 0 && errno == EINTR)
			continue;
		if (rc < 0)
			return -1;
		if (rc == 0)
			continue;
		n = read(fd, &byte, 1);
		if (n < 0 && errno == EINTR)
			continue;
		if (n != 1)
			return -1;
		*out = byte;
		return 0;
	}
}

static void phase_driver(int progress_rd, int stall_wr, int ack_wr, const struct phase_plan *plan)
{
	struct timespec deadline;
	unsigned char buf[64];

	if (!plan || plan->body_len == 0 || plan->body_len > sizeof buf)
		_exit(2);
	if (clock_gettime(CLOCK_MONOTONIC, &deadline) != 0)
		_exit(2);
	guard_add_ms(&deadline, 3000);
	for (;;) {
		char phase = 0;

		if (read_phase(progress_rd, &deadline, &phase) != 0)
			_exit(2);
		if (phase == 'I') {
			if (write_byte(stall_wr, 'I') != 0)
				_exit(2);
		} else if (phase == 'C') {
			if (plan->create_at_c) {
				int fd = open(plan->path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0644);

				if (fd < 0)
					_exit(2);
				memset(buf, plan->competitor_byte, plan->body_len);
				if (write(fd, buf, plan->body_len) != (ssize_t)plan->body_len) {
					close(fd);
					_exit(2);
				}
				close(fd);
			}
			if (write_byte(stall_wr, 'C') != 0)
				_exit(2);
		} else if (phase == 'U') {
			if (plan->replace_at_u) {
				int fd;

				if (unlink(plan->path) != 0 && errno != ENOENT)
					_exit(2);
				fd = open(plan->path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0644);
				if (fd < 0)
					_exit(2);
				memset(buf, plan->replacement_byte, plan->body_len);
				if (write(fd, buf, plan->body_len) != (ssize_t)plan->body_len) {
					close(fd);
					_exit(2);
				}
				close(fd);
			}
			if (!plan->release_u) {
				/* Tell the checker which phase is held, then keep the stall write end open. */
				if (plan->stall_phase != 'U' || write_byte(ack_wr, 'U') != 0)
					_exit(2);
				for (;;)
					pause();
			}
			if (write_byte(stall_wr, 'U') != 0)
				_exit(2);
			_exit(0);
		} else if (phase == 'P') {
			if (!plan->release_p) {
				if (plan->stall_phase != 'P' || write_byte(ack_wr, 'P') != 0)
					_exit(2);
				for (;;)
					pause();
			}
			if (write_byte(stall_wr, 'P') != 0)
				_exit(2);
			_exit(0);
		} else {
			_exit(2);
		}
	}
}

static int file_is(const char *path, const unsigned char *buf, size_t len)
{
	unsigned char got[64];
	int fd;
	ssize_t n;

	if (!path || !buf || len == 0 || len > sizeof got)
		return 0;
	fd = open(path, O_RDONLY | O_CLOEXEC);
	if (fd < 0)
		return 0;
	n = read(fd, got, sizeof got);
	close(fd);
	return n == (ssize_t)len && memcmp(got, buf, len) == 0;
}

static int read_phase_ack(int fd, char *out)
{
	struct pollfd pfd;
	char byte = 0;
	ssize_t n;
	int rc;

	pfd.fd = fd;
	pfd.events = POLLIN;
	rc = poll(&pfd, 1, 0);
	if (rc <= 0)
		return -1;
	n = read(fd, &byte, 1);
	if (n != 1)
		return -1;
	*out = byte;
	return 0;
}

static int driver_finished(pid_t driver, int *code)
{
	struct timespec deadline;

	if (clock_gettime(CLOCK_MONOTONIC, &deadline) != 0)
		return -1;
	guard_add_ms(&deadline, 500);
	for (;;) {
		int status = 0;
		int remain = 0;
		pid_t got = waitpid(driver, &status, WNOHANG);

		if (got == driver) {
			if (!WIFEXITED(status))
				return -1;
			*code = WEXITSTATUS(status);
			return 0;
		}
		if (got < 0)
			return -1;
		if (guard_remaining_ms(&deadline, &remain) != 0)
			return -1;
		if (poll(NULL, 0, remain > 20 ? 20 : remain) < 0 && errno != EINTR)
			return -1;
	}
}

static void run_phased_publish(const struct phase_plan *plan)
{
	int progress[2] = {-1, -1};
	int stall[2] = {-1, -1};
	int ack[2] = {-1, -1};
	struct timespec start;
	struct timespec end;
	struct timespec deadline;
	pid_t driver = -1;
	pid_t unreaped = 0;
	int64_t elapsed_ms = -1;
	char acked = 0;
	int saw_ack = 0;

	if (pipe2(progress, O_CLOEXEC) != 0) {
		fail_setup(plan->what);
		return;
	}
	if (pipe2(stall, O_CLOEXEC) != 0) {
		fail_setup(plan->what);
		close_pair(progress);
		return;
	}
	if (pipe2(ack, O_CLOEXEC) != 0) {
		fail_setup(plan->what);
		close_pair(progress);
		close_pair(stall);
		return;
	}
	driver = fork();
	if (driver < 0) {
		fail_setup(plan->what);
		close_pair(progress);
		close_pair(stall);
		close_pair(ack);
		return;
	}
	if (driver == 0) {
		close(progress[1]);
		close(stall[0]);
		close(ack[0]);
		phase_driver(progress[0], stall[1], ack[1], plan);
		_exit(2);
	}
	close(progress[0]);
	close(stall[1]);
	close(ack[1]);
	ack[1] = -1;
	if (clock_gettime(CLOCK_MONOTONIC, &start) != 0 || clock_gettime(CLOCK_MONOTONIC, &deadline) != 0) {
		fail_setup(plan->what);
		close(stall[0]);
		close(progress[1]);
		close(ack[0]);
		stop_child(driver);
		return;
	}
	guard_add_ms(&deadline, plan->deadline_ms);
	expect(receipt_publish_supervised(plan->path, plan->body, plan->body_len, &deadline, stall[0], progress[1],
					  &unreaped) != 0,
	       plan->what);
	if (clock_gettime(CLOCK_MONOTONIC, &end) == 0) {
		elapsed_ms = (int64_t)(end.tv_sec - start.tv_sec) * 1000 +
			     (int64_t)(end.tv_nsec - start.tv_nsec) / 1000000;
		expect(elapsed_ms < 2000, "phased publish returns at the deadline");
	} else {
		fail_setup(plan->what);
	}
	if (plan->stall_phase) {
		saw_ack = read_phase_ack(ack[0], &acked) == 0;
		expect(saw_ack && acked == plan->stall_phase, "requested phase was entered before the stall");
		expect(elapsed_ms + 25 >= (int64_t)plan->deadline_ms, "stall reaches the deadline");
		expect(waitpid(driver, NULL, WNOHANG) == 0, "driver stays in the requested stall");
	}
	expect(file_is(plan->path, plan->remain, plan->body_len), plan->what);
	close(stall[0]);
	close(progress[1]);
	close(ack[0]);
	if (unreaped > 0)
		reap_child_bounded(unreaped);
	if (plan->stall_phase) {
		stop_child(driver);
	} else {
		int code = -1;

		if (driver_finished(driver, &code) != 0 || code != 0) {
			fail_setup(plan->what);
			stop_child(driver);
		}
	}
}

static void test_publish_phases(void)
{
	char dir[] = "/tmp/mnemion-guard-phase-XXXXXX";
	char u_path[PATH_MAX];
	char c_path[PATH_MAX];
	char r_path[PATH_MAX];
	char p_path[PATH_MAX];
	unsigned char body[32];
	unsigned char competitor[32];
	unsigned char replacement[32];
	struct phase_plan plan;

	if (mkdtemp(dir) == NULL) {
		fail_setup("phase temp");
		return;
	}
	if (snprintf(u_path, sizeof u_path, "%s/u.bin", dir) >= (int)sizeof u_path ||
	    snprintf(c_path, sizeof c_path, "%s/c.bin", dir) >= (int)sizeof c_path ||
	    snprintf(r_path, sizeof r_path, "%s/r.bin", dir) >= (int)sizeof r_path ||
	    snprintf(p_path, sizeof p_path, "%s/p.bin", dir) >= (int)sizeof p_path) {
		fail_setup("phase path");
		remove_tree(dir);
		return;
	}
	memset(body, 0x41, sizeof body);
	memset(competitor, 0x71, sizeof competitor);
	memset(replacement, 0x72, sizeof replacement);

	memset(&plan, 0, sizeof plan);
	plan.path = u_path;
	plan.body = body;
	plan.body_len = sizeof body;
	plan.create_at_c = 1;
	plan.competitor_byte = 0x71;
	plan.release_u = 0;
	plan.stall_phase = 'U';
	plan.deadline_ms = 1000;
	plan.what = "stalled rollback leaves the final name";
	plan.remain = competitor;
	run_phased_publish(&plan);

	memset(&plan, 0, sizeof plan);
	plan.path = c_path;
	plan.body = body;
	plan.body_len = sizeof body;
	plan.create_at_c = 1;
	plan.competitor_byte = 0x71;
	plan.release_u = 1;
	plan.deadline_ms = 1000;
	plan.what = "competing final at creation is preserved";
	plan.remain = competitor;
	run_phased_publish(&plan);

	memset(&plan, 0, sizeof plan);
	plan.path = r_path;
	plan.body = body;
	plan.body_len = sizeof body;
	plan.create_at_c = 1;
	plan.competitor_byte = 0x71;
	plan.replace_at_u = 1;
	plan.replacement_byte = 0x72;
	plan.release_u = 1;
	plan.deadline_ms = 1000;
	plan.what = "replacement during rollback stays";
	plan.remain = replacement;
	run_phased_publish(&plan);

	memset(&plan, 0, sizeof plan);
	plan.path = p_path;
	plan.body = body;
	plan.body_len = sizeof body;
	plan.release_p = 0;
	plan.stall_phase = 'P';
	plan.deadline_ms = 1200;
	plan.what = "post-commit stall leaves the published receipt";
	plan.remain = body;
	run_phased_publish(&plan);

	remove_tree(dir);
}

static int owner_fixture(const char *which, const char *extra)
{
	if (strcmp(which, "hang") == 0) {
		for (;;)
			pause();
	}
	if (strcmp(which, "leave-child") == 0) {
		int ready[2];
		int wfd;
		char *end = NULL;
		long value;
		pid_t grand;
		char byte = 0;

		if (!extra)
			return 2;
		errno = 0;
		value = strtol(extra, &end, 10);
		if (end == extra || *end || errno || value < 0 || value > 0x7fffffffL)
			return 2;
		wfd = (int)value;
		if (pipe2(ready, O_CLOEXEC) != 0)
			return 2;
		grand = fork();
		if (grand < 0)
			return 2;
		if (grand == 0) {
			char mark = 'g';

			close(ready[0]);
			if (write(wfd, &mark, 1) != 1)
				_exit(2);
			if (write(ready[1], &mark, 1) != 1)
				_exit(2);
			close(ready[1]);
			for (;;)
				pause();
		}
		close(ready[1]);
		if (read(ready[0], &byte, 1) != 1)
			return 2;
		close(ready[0]);
		return 0;
	}
	return 2;
}

static int exe_path(char *buf, size_t cap)
{
	ssize_t n = readlink("/proc/self/exe", buf, cap - 1);

	if (n <= 0 || (size_t)n >= cap)
		return -1;
	buf[n] = 0;
	return 0;
}

/* Backstop for a failed owner case. Signals only a pidfd for a process that is
 * still our child. Does not signal a process-group id. The absolute deadline
 * is checked before every WNOHANG wait, including a reaped child and EINTR.
 * A batch is at most the adopted-child hint cap, then live children are
 * signalled. Expiry returns. There is no blocking wait.
 */
static void release_remaining_children(void)
{
	struct timespec deadline;

	if (clock_gettime(CLOCK_MONOTONIC, &deadline) != 0)
		return;
	guard_add_ms(&deadline, 200);
	for (;;) {
		int status = 0;
		pid_t got = 0;
		char path[80];
		char buf[256];
		char *cursor;
		int fd;
		int n;
		int remain = 0;
		int batch_reaped = 0;

		if (guard_remaining_ms(&deadline, &remain) != 0)
			return;
		while (batch_reaped < 16) {
			if (guard_remaining_ms(&deadline, &remain) != 0)
				return;
			got = waitpid(-1, &status, WNOHANG);
			if (got < 0 && errno == EINTR)
				continue;
			if (got < 0)
				return;
			if (got == 0)
				break;
			batch_reaped++;
			status = 0;
		}
		if (guard_remaining_ms(&deadline, &remain) != 0)
			return;
		if (snprintf(path, sizeof path, "/proc/%d/task/%d/children", (int)getpid(), (int)getpid()) >=
		    (int)sizeof path)
			return;
		fd = open(path, O_RDONLY | O_CLOEXEC);
		if (fd < 0)
			return;
		n = (int)read(fd, buf, sizeof buf - 1);
		close(fd);
		if (n <= 0) {
			if (guard_remaining_ms(&deadline, &remain) != 0)
				return;
			if (poll(NULL, 0, remain > 20 ? 20 : remain) < 0 && errno != EINTR)
				return;
			continue;
		}
		buf[n] = 0;
		cursor = buf;
		while (*cursor) {
			char *end = NULL;
			long value = strtol(cursor, &end, 10);
			int pinned;

			if (end == cursor)
				break;
			cursor = end;
			if (value <= 0)
				continue;
			pinned = open_pidfd((pid_t)value);
			if (pinned < 0)
				continue;
			/* The pidfd pins the task. Skip it when it is no longer our child. */
			{
				char status_path[64];
				char status_buf[256];
				int status_fd;
				int status_n;
				int ours = 0;

				if (snprintf(status_path, sizeof status_path, "/proc/%ld/status", value) <
				    (int)sizeof status_path) {
					status_fd = open(status_path, O_RDONLY | O_CLOEXEC);
					if (status_fd >= 0) {
						status_n = (int)read(status_fd, status_buf, sizeof status_buf - 1);
						close(status_fd);
						if (status_n > 0) {
							status_buf[status_n] = 0;
							if (strstr(status_buf, "PPid:\t") != NULL) {
								char needle[32];

								snprintf(needle, sizeof needle, "PPid:\t%d\n", (int)getpid());
								ours = strstr(status_buf, needle) != NULL;
							}
						}
					}
				}
				if (!ours) {
					close(pinned);
					continue;
				}
			}
			if (syscall(__NR_pidfd_send_signal, pinned, SIGKILL, NULL, 0) != 0) {
				close(pinned);
				continue;
			}
			close(pinned);
		}
		if (guard_remaining_ms(&deadline, &remain) != 0)
			return;
		if (poll(NULL, 0, remain > 20 ? 20 : remain) < 0 && errno != EINTR)
			return;
	}
}

/* Calls external_owner_run in this process. It does not exec
 * admission_guard_owner, does not pass --status, and does not prove
 * exclusive create, write, or close. Publication failure is a CLI result
 * and stays distinct from these child, timeout, and cleanup flags.
 * --status-fixture is that CLI entry. This check does not run it.
 */
static void test_external_owner_boundaries(void)
{
	char exe[PATH_MAX];
	struct external_owner_spec spec;
	struct external_owner_result result;
	struct timespec start;
	struct timespec end;
	int life[2] = {-1, -1};
	char fd_text[32];
	char *hang_argv[4];
	char *leave_argv[5];
	int64_t elapsed_ms;
	struct pollfd pfd;

	if (exe_path(exe, sizeof exe) != 0) {
		fail_setup("owner exe");
		return;
	}
	hang_argv[0] = exe;
	hang_argv[1] = "--owner-fixture";
	hang_argv[2] = "hang";
	hang_argv[3] = NULL;
	memset(&spec, 0, sizeof spec);
	spec.argv = hang_argv;
	spec.run_ms = 300;
	spec.cleanup_ms = 300;
	if (clock_gettime(CLOCK_MONOTONIC, &start) != 0) {
		fail_setup("owner clock");
		return;
	}
	expect(external_owner_run(&spec, &result) == 0, "hanging checker owner returned");
	if (clock_gettime(CLOCK_MONOTONIC, &end) != 0) {
		fail_setup("owner clock");
	} else {
		elapsed_ms = (int64_t)(end.tv_sec - start.tv_sec) * 1000 +
			     (int64_t)(end.tv_nsec - start.tv_nsec) / 1000000;
		expect(elapsed_ms + 25 >= 300, "hanging checker reaches the run deadline");
		expect(elapsed_ms < 1600, "hanging checker does not wait past cleanup");
	}
	expect(result.started == 1, "hanging checker was started");
	expect(result.timed_out == 1, "hanging checker records the run deadline");
	expect(result.interrupted == 0, "hanging checker was not an interruption");
	expect(result.child_signaled == 1, "hanging checker was signalled through its pidfd");
	expect(result.cleanup_confirmed == 1, "hanging checker cleanup is confirmed");
	expect(result.ownership_unresolved == 0, "hanging checker ownership stayed resolved");
	release_remaining_children();

	if (pipe2(life, O_CLOEXEC) != 0) {
		fail_setup("early child pipe");
		return;
	}
	if (fcntl(life[1], F_SETFD, 0) != 0) {
		fail_setup("early child fd");
		close_pair(life);
		return;
	}
	if (snprintf(fd_text, sizeof fd_text, "%d", life[1]) >= (int)sizeof fd_text) {
		fail_setup("early child fd text");
		close_pair(life);
		return;
	}
	leave_argv[0] = exe;
	leave_argv[1] = "--owner-fixture";
	leave_argv[2] = "leave-child";
	leave_argv[3] = fd_text;
	leave_argv[4] = NULL;
	memset(&spec, 0, sizeof spec);
	memset(&result, 0, sizeof result);
	spec.argv = leave_argv;
	spec.run_ms = 2000;
	spec.cleanup_ms = 500;
	if (clock_gettime(CLOCK_MONOTONIC, &start) != 0) {
		fail_setup("owner clock");
		close_pair(life);
		return;
	}
	expect(external_owner_run(&spec, &result) == 0, "early checker owner returned");
	if (clock_gettime(CLOCK_MONOTONIC, &end) != 0) {
		fail_setup("owner clock");
		elapsed_ms = -1;
	} else {
		elapsed_ms = (int64_t)(end.tv_sec - start.tv_sec) * 1000 +
			     (int64_t)(end.tv_nsec - start.tv_nsec) / 1000000;
		expect(elapsed_ms < 1500, "early checker returns before its run deadline");
	}
	expect(result.started == 1, "early checker was started");
	expect(result.timed_out == 0, "early checker is not a run timeout");
	expect(result.child_exited == 1 && result.child_exit_code == 0, "early checker status stays separate");
	expect(result.cleanup_confirmed == 1, "early checker descendant cleanup is confirmed");
	expect(result.ownership_unresolved == 0, "early checker ownership stayed resolved");
	close(life[1]);
	life[1] = -1;
	memset(&pfd, 0, sizeof pfd);
	pfd.fd = life[0];
	pfd.events = POLLIN;
	expect(poll(&pfd, 1, 0) > 0 && (pfd.revents & POLLHUP), "early checker left no live child");
	close(life[0]);
	release_remaining_children();
}

int main(int argc, char **argv)
{
	if (argc >= 3 && strcmp(argv[1], "--owner-fixture") == 0)
		return owner_fixture(argv[2], argc > 3 ? argv[3] : NULL);
	test_stale_receipt();
	test_controller_loss();
	test_blocked_and_eintr();
	test_clone_without_custody();
	test_failed_cleanup_and_fd_survives();
	test_unowned_path_is_not_killed();
	test_cleanup_expiry_returns();
	test_watched_worker(0, 0);
	test_watched_worker(1, 1);
	test_normal_observe_reap();
	test_unreported_preflight();
	test_absence_inspection();
	test_publication_deadline();
	test_publish_phases();
	test_external_owner_boundaries();
	dprintf(STDOUT_FILENO, "supervision_ipc=1\n");
	dprintf(STDOUT_FILENO, "cgroup_evidence=0\n");
	dprintf(STDOUT_FILENO, "bpf_evidence=0\n");
	if (failures) {
		dprintf(STDOUT_FILENO, "supervision_check=fail\n");
		return 1;
	}
	dprintf(STDOUT_FILENO, "supervision_check=pass\n");
	return 0;
}
