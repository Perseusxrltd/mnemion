#define _GNU_SOURCE

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <limits.h>
#include <sched.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include <linux/bpf.h>
#include <linux/btf.h>
#include <linux/capability.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/random.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/utsname.h>
#include <sys/wait.h>

#include <bpf/bpf.h>
#include <bpf/btf.h>
#include <bpf/libbpf.h>

#include <linux/types.h>
#define LIFETIME_HAVE_U_TYPES
#include "lifetime_receipt.h"
#include "lifetime_sha256.h"

/* Cleanup owner stays outside the owned cgroup and is the only process
 * that writes cgroup.kill. Descendants are not stopped by historical
 * numeric process ids. Scope is no external migration: a process a
 * privileged outsider moves out is outside this claim.
 * Birth launch is clone3 with CLONE_INTO_CGROUP. A write of a process id
 * before exec is not this path.
 */

#ifndef CLONE_INTO_CGROUP
#define CLONE_INTO_CGROUP 0x0000020000000000ULL
#endif

#ifndef __NR_clone3
#if defined(__x86_64__) || defined(__aarch64__)
#define __NR_clone3 435
#else
#error __NR_clone3 is required
#endif
#endif

#ifndef __NR_pidfd_open
#if defined(__x86_64__) || defined(__aarch64__)
#define __NR_pidfd_open 434
#else
#error __NR_pidfd_open is required
#endif
#endif

#ifndef __NR_pidfd_send_signal
#if defined(__x86_64__) || defined(__aarch64__)
#define __NR_pidfd_send_signal 424
#else
#error __NR_pidfd_send_signal is required
#endif
#endif

#ifndef __NR_close_range
#if defined(__x86_64__) || defined(__aarch64__)
#define __NR_close_range 436
#else
#error __NR_close_range is required
#endif
#endif

#ifndef __NR_io_uring_setup
#if defined(__x86_64__) || defined(__aarch64__)
#define __NR_io_uring_setup 425
#else
#error __NR_io_uring_setup is required
#endif
#endif

#ifndef __NR_capget
#if defined(__x86_64__)
#define __NR_capget 125
#elif defined(__aarch64__)
#define __NR_capget 90
#else
#error __NR_capget is required
#endif
#endif

#ifndef __NR_capset
#if defined(__x86_64__)
#define __NR_capset 126
#elif defined(__aarch64__)
#define __NR_capset 91
#else
#error __NR_capset is required
#endif
#endif

#ifndef CAP_BPF
#define CAP_BPF 39
#endif
#ifndef CAP_PERFMON
#define CAP_PERFMON 38
#endif
#ifndef CAP_SYS_ADMIN
#define CAP_SYS_ADMIN 21
#endif

#define LIFE_MSG_ATTACHED 1u
#define LIFE_MSG_REFUSED 2u
#define LIFE_MSG_GO 3u
#define LIFE_MSG_VALIDATE 4u
#define LIFE_MSG_STOP 5u

#define LIFE_BTF_CAP (64u * 1024u * 1024u)
#define LIFE_CAPACITY_CHILDREN 300
#define LIFE_OWNER_GRACE_MS 2000u

struct lifetime_clone_args {
	uint64_t flags;
	uint64_t pidfd;
	uint64_t child_tid;
	uint64_t parent_tid;
	uint64_t exit_signal;
	uint64_t stack;
	uint64_t stack_size;
	uint64_t tls;
	uint64_t set_tid;
	uint64_t set_tid_size;
	uint64_t cgroup;
};

_Static_assert(sizeof(struct lifetime_clone_args) == 88, "clone3 version-2 size");

struct life_msg {
	uint32_t code;
	uint32_t reason;
	uint32_t mode;
	uint32_t page_size;
	uint64_t cgroup_id;
	uint8_t clear_refs_state;
	uint8_t io_encoding;
	uint8_t links_verified;
	uint8_t prototype_ok;
	uint8_t recursion_field_ok;
	uint8_t config_taskstats;
	uint8_t config_cgroups;
	uint8_t btf_ok;
	uint8_t enabled_after_validation;
	uint8_t pad[7];
};

struct cpu_view {
	uint64_t usage;
	uint64_t user;
	uint64_t system;
	int ok;
};

static struct lifetime_receipt g_receipt;
static uint32_t g_preset_reason;
static char g_receipt_path[PATH_MAX];
static char g_leaf_path[PATH_MAX];
static char g_leaf_name[64];
static char g_cgroup_rel[PATH_MAX];
static int g_dirfd = -1;
static uint64_t g_cgroup_id;
static uint32_t g_mode;
static int g_keep_fd = -1;
static int g_thread_tid = 1;

static void note(const char *msg)
{
	if (msg)
		dprintf(STDERR_FILENO, "lifetime_diag: %s\n", msg);
}

static uint64_t mono_ms(void)
{
	struct timespec ts;

	if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0)
		return 0;
	return (uint64_t)ts.tv_sec * 1000ull + (uint64_t)ts.tv_nsec / 1000000ull;
}

static void sleep_ms(uint32_t ms)
{
	struct timespec ts;

	ts.tv_sec = ms / 1000u;
	ts.tv_nsec = (long)(ms % 1000u) * 1000000L;
	while (nanosleep(&ts, &ts) != 0) {
		if (errno != EINTR)
			break;
	}
}

static int write_full(int fd, const void *buf, size_t len)
{
	const unsigned char *p = buf;

	while (len) {
		ssize_t n = write(fd, p, len);
		if (n < 0) {
			if (errno == EINTR)
				continue;
			return -1;
		}
		if (n == 0)
			return -1;
		p += n;
		len -= (size_t)n;
	}
	return 0;
}

static int read_full_fd(int fd, char *buf, size_t cap, size_t *out)
{
	size_t n = 0;

	if (cap == 0)
		return -1;
	while (n + 1 < cap) {
		ssize_t got = read(fd, buf + n, cap - 1 - n);
		if (got < 0) {
			if (errno == EINTR)
				continue;
			return -1;
		}
		if (got == 0)
			break;
		n += (size_t)got;
	}
	if (n + 1 >= cap)
		return -1;
	buf[n] = 0;
	if (out)
		*out = n;
	return 0;
}

static int read_path(const char *path, char *buf, size_t cap)
{
	int fd = open(path, O_RDONLY | O_CLOEXEC);
	int rc;

	if (fd < 0)
		return -1;
	rc = read_full_fd(fd, buf, cap, NULL);
	close(fd);
	return rc;
}

static int send_msg(int fd, const struct life_msg *msg)
{
	ssize_t n = send(fd, msg, sizeof(*msg), MSG_NOSIGNAL);

	return n == (ssize_t)sizeof(*msg) ? 0 : -1;
}

static int recv_msg(int fd, struct life_msg *msg)
{
	ssize_t n = recv(fd, msg, sizeof(*msg), 0);

	if (n < 0 && errno == EINTR)
		n = recv(fd, msg, sizeof(*msg), 0);
	return n == (ssize_t)sizeof(*msg) ? 0 : -1;
}

static int write_receipt(const char *path, const struct lifetime_receipt *receipt)
{
	char tmp[PATH_MAX];
	int fd;
	int rc;

	if (snprintf(tmp, sizeof tmp, "%s.tmp", path) >= (int)sizeof tmp)
		return -1;
	fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
	if (fd < 0)
		return -1;
	rc = write_full(fd, receipt, sizeof(*receipt));
	if (rc == 0 && fsync(fd) != 0)
		rc = -1;
	if (close(fd) != 0)
		rc = -1;
	if (rc != 0) {
		unlink(tmp);
		return -1;
	}
	if (rename(tmp, path) != 0) {
		unlink(tmp);
		return -1;
	}
	return 0;
}

static int read_receipt(const char *path, struct lifetime_receipt *receipt)
{
	int fd = open(path, O_RDONLY | O_CLOEXEC);
	size_t n = 0;
	char *p;

	if (fd < 0)
		return -1;
	p = (char *)receipt;
	while (n < sizeof(*receipt)) {
		ssize_t got = read(fd, p + n, sizeof(*receipt) - n);
		if (got < 0) {
			if (errno == EINTR)
				continue;
			close(fd);
			return -1;
		}
		if (got == 0)
			break;
		n += (size_t)got;
	}
	close(fd);
	return n == sizeof(*receipt) ? 0 : -1;
}

static void seal_and_write(void)
{
	g_receipt.known_fixture_births = 0;
	if (g_receipt.reason == LIFETIME_REASON_NONE && g_preset_reason != LIFETIME_REASON_NONE)
		g_receipt.reason = g_preset_reason;
	lifetime_apply(&g_receipt);
	if (write_receipt(g_receipt_path, &g_receipt) != 0)
		note("receipt write failed");
}

static int cap_bit(uint64_t caps, int cap)
{
	if (cap < 0 || cap > 63)
		return 0;
	return (int)((caps >> cap) & 1ull);
}

static int read_capeff(uint64_t *out)
{
	char buf[16384];
	char hex[160];
	char *line;
	size_t n = 0;
	const char *start;

	if (read_path("/proc/self/status", buf, sizeof buf) != 0)
		return -1;
	line = strstr(buf, "CapEff:");
	if (!line)
		return -1;
	line += 7;
	while (*line == ' ' || *line == '\t')
		line++;
	while (isxdigit((unsigned char)*line) && n + 1 < sizeof hex)
		hex[n++] = *line++;
	if (n == 0)
		return -1;
	hex[n] = 0;
	start = n > 16 ? hex + (n - 16) : hex;
	*out = strtoull(start, NULL, 16);
	return 0;
}

static void read_lockdown(void)
{
	char buf[256];

	g_receipt.lockdown_blocks = 0;
	if (read_path("/sys/kernel/security/lockdown", buf, sizeof buf) != 0)
		return;
	if (strstr(buf, "[integrity]") || strstr(buf, "[confidentiality]"))
		g_receipt.lockdown_blocks = 1;
}

static int hash_btf(uint8_t out[32])
{
	int fd;
	uint8_t *mem;
	size_t cap = 1u << 20;
	size_t n = 0;
	ssize_t got;

	fd = open("/sys/kernel/btf/vmlinux", O_RDONLY | O_CLOEXEC);
	if (fd < 0)
		return -1;
	mem = malloc(cap);
	if (!mem) {
		close(fd);
		return -1;
	}
	for (;;) {
		if (n == cap) {
			size_t next;
			uint8_t *grown;
			if (cap >= LIFE_BTF_CAP) {
				free(mem);
				close(fd);
				return -1;
			}
			next = cap * 2u;
			if (next > LIFE_BTF_CAP)
				next = LIFE_BTF_CAP;
			grown = realloc(mem, next);
			if (!grown) {
				free(mem);
				close(fd);
				return -1;
			}
			mem = grown;
			cap = next;
		}
		got = read(fd, mem + n, cap - n);
		if (got < 0) {
			if (errno == EINTR)
				continue;
			free(mem);
			close(fd);
			return -1;
		}
		if (got == 0)
			break;
		n += (size_t)got;
	}
	close(fd);
	if (n == 0 || n >= LIFE_BTF_CAP) {
		free(mem);
		return -1;
	}
	lifetime_sha256(mem, n, out);
	free(mem);
	return 0;
}

static int path_is_normalized(const char *path)
{
	size_t n = strlen(path);
	size_t i;

	if (n == 0 || path[0] != '/')
		return 0;
	if (n > 1 && path[n - 1] == '/')
		return 0;
	for (i = 0; i < n; i++) {
		unsigned char ch = (unsigned char)path[i];
		if (ch <= ' ' || ch == '\\' || ch >= 0x7f)
			return 0;
		if (ch == '/' && i + 1 < n && path[i + 1] == '/')
			return 0;
	}
	if (strstr(path, "..") || strstr(path, "(deleted)"))
		return 0;
	return 1;
}

static int line_is_other_cgroup(const char *line, size_t len)
{
	size_t i = 0;

	if (len == 0 || line[0] < '0' || line[0] > '9')
		return 0;
	while (i < len && line[i] >= '0' && line[i] <= '9')
		i++;
	if (i == 0 || i >= len || line[i] != ':')
		return 0;
	i++;
	while (i < len && line[i] != ':')
		i++;
	if (i >= len || line[i] != ':')
		return 0;
	if (i + 1 >= len)
		return 0;
	return 1;
}

/* One exact "0::" line. Other controller lines may be present.
 * A second 0:: line, a blank line, or a non-normalized path is rejected.
 */
static int parse_exact_cgroup2_path(const char *text, char *out, size_t cap)
{
	const char *cursor;
	int found = 0;

	if (!text || !out || cap < 2)
		return -1;
	out[0] = 0;
	cursor = text;
	if (*cursor == '\0')
		return -1;
	while (*cursor) {
		const char *nl = strchr(cursor, '\n');
		size_t len = nl ? (size_t)(nl - cursor) : strlen(cursor);

		if (len == 0)
			return -1;
		if (cursor[len - 1] == '\r')
			return -1;
		if (len >= 3 && cursor[0] == '0' && cursor[1] == ':' && cursor[2] == ':') {
			size_t plen = len - 3;
			if (found)
				return -1;
			if (plen + 1 > cap)
				return -1;
			memcpy(out, cursor + 3, plen);
			out[plen] = 0;
			if (!path_is_normalized(out))
				return -1;
			found = 1;
		} else if (!line_is_other_cgroup(cursor, len)) {
			return -1;
		}
		if (!nl)
			break;
		cursor = nl + 1;
		if (*cursor == '\0')
			break;
	}
	return found ? 0 : -1;
}

static int cgroup_relative(char *out, size_t cap)
{
	char buf[8192];

	if (read_path("/proc/self/cgroup", buf, sizeof buf) != 0)
		return -1;
	if (parse_exact_cgroup2_path(buf, out, cap) != 0)
		return -1;
	if (strcmp(out, "/") == 0)
		return -1;
	return 0;
}

static int path_is_under(const char *path, const char *root)
{
	size_t n = strlen(root);

	if (strcmp(path, root) == 0)
		return 0;
	if (strncmp(path, root, n) != 0)
		return 0;
	return path[n] == '/';
}

static int cgroup_id_of(int fd, uint64_t *out)
{
	unsigned char storage[sizeof(struct file_handle) + 8];
	struct file_handle *fh = (struct file_handle *)storage;
	int mount_id = 0;
	uint64_t id = 0;

	memset(storage, 0, sizeof storage);
	fh->handle_bytes = 8;
	if (name_to_handle_at(fd, "", fh, &mount_id, AT_EMPTY_PATH) != 0)
		return -1;
	if (fh->handle_bytes != 8)
		return -1;
	memcpy(&id, fh->f_handle, sizeof id);
	if (id == 0)
		return -1;
	*out = id;
	return 0;
}

static int read_populated(int dirfd, int *out)
{
	char buf[512];
	char *mark;
	int fd = openat(dirfd, "cgroup.events", O_RDONLY | O_CLOEXEC);

	if (fd < 0)
		return -1;
	if (read_full_fd(fd, buf, sizeof buf, NULL) != 0) {
		close(fd);
		return -1;
	}
	close(fd);
	mark = strstr(buf, "populated ");
	if (!mark)
		return -1;
	mark += 10;
	if (*mark != '0' && *mark != '1')
		return -1;
	*out = *mark - '0';
	return 0;
}

static int parse_cpu_line(const char *line, const char *key, uint64_t *out)
{
	size_t n = strlen(key);
	char *end = NULL;
	unsigned long long val;

	if (strncmp(line, key, n) != 0 || line[n] != ' ')
		return 0;
	errno = 0;
	val = strtoull(line + n + 1, &end, 10);
	if (errno || end == line + n + 1)
		return -1;
	*out = (uint64_t)val;
	return 1;
}

static int read_cpu(int dirfd, struct cpu_view *out)
{
	char buf[8192];
	char *cursor;
	int fd;
	int saw_usage = 0;
	int saw_user = 0;
	int saw_system = 0;

	memset(out, 0, sizeof(*out));
	fd = openat(dirfd, "cpu.stat", O_RDONLY | O_CLOEXEC);
	if (fd < 0)
		return -1;
	if (read_full_fd(fd, buf, sizeof buf, NULL) != 0) {
		close(fd);
		return -1;
	}
	close(fd);
	cursor = buf;
	while (*cursor) {
		char *nl = strchr(cursor, '\n');
		int rc;
		if (nl)
			*nl = 0;
		rc = parse_cpu_line(cursor, "usage_usec", &out->usage);
		if (rc < 0)
			return -1;
		if (rc == 1)
			saw_usage = 1;
		rc = parse_cpu_line(cursor, "user_usec", &out->user);
		if (rc < 0)
			return -1;
		if (rc == 1)
			saw_user = 1;
		rc = parse_cpu_line(cursor, "system_usec", &out->system);
		if (rc < 0)
			return -1;
		if (rc == 1)
			saw_system = 1;
		if (!nl)
			break;
		cursor = nl + 1;
	}
	out->ok = saw_usage && saw_user && saw_system;
	return out->ok ? 0 : -1;
}

static int cgroup_kill_write(int dirfd)
{
	int fd = openat(dirfd, "cgroup.kill", O_WRONLY | O_CLOEXEC);
	char one = '1';
	int rc;

	if (fd < 0)
		return -1;
	rc = write_full(fd, &one, 1);
	close(fd);
	return rc;
}

static int cleanup_tree(void)
{
	uint64_t deadline;
	int kill_rc;

	if (g_leaf_path[0] == '\0')
		return 1;
	if (g_dirfd < 0)
		return rmdir(g_leaf_path) == 0 ? 1 : 0;
	kill_rc = cgroup_kill_write(g_dirfd);
	deadline = mono_ms() + LIFETIME_CLEANUP_MS;
	for (;;) {
		int status = 0;
		int populated = -1;
		while (waitpid(-1, &status, WNOHANG) > 0)
			continue;
		if (read_populated(g_dirfd, &populated) == 0 && populated == 0 && rmdir(g_leaf_path) == 0) {
			close(g_dirfd);
			g_dirfd = -1;
			return 1;
		}
		if (mono_ms() >= deadline)
			break;
		sleep_ms(20);
	}
	(void)kill_rc;
	return 0;
}

static pid_t clone3_into(int dirfd)
{
	struct lifetime_clone_args args;

	memset(&args, 0, sizeof args);
	args.flags = CLONE_INTO_CGROUP;
	args.exit_signal = SIGCHLD;
	args.cgroup = (uint64_t)dirfd;
	return (pid_t)syscall(__NR_clone3, &args, sizeof args);
}

static int wait_pid_bounded(pid_t pid, int *status, uint32_t bound_ms)
{
	uint64_t deadline = mono_ms() + bound_ms;

	for (;;) {
		pid_t got = waitpid(pid, status, WNOHANG);
		if (got == pid)
			return 0;
		if (got < 0 && errno != EINTR)
			return -1;
		if (mono_ms() >= deadline)
			return -1;
		sleep_ms(20);
	}
}

static void close_from_3(void)
{
	if (syscall(__NR_close_range, 3u, ~0u, 0u) == 0)
		return;
	for (int fd = 3; fd < 1024; fd++)
		close(fd);
}

static void close_from_3_except(int keep)
{
	if (keep >= 3) {
		for (int fd = 3; fd < 1024; fd++) {
			if (fd != keep)
				close(fd);
		}
		return;
	}
	close_from_3();
}

static int caps_are_clear(void)
{
	struct __user_cap_header_struct hdr;
	struct __user_cap_data_struct data[2];

	memset(&hdr, 0, sizeof hdr);
	memset(data, 0, sizeof data);
	hdr.version = _LINUX_CAPABILITY_VERSION_3;
	hdr.pid = 0;
	if (syscall(__NR_capget, &hdr, data) != 0)
		return -1;
	if (data[0].effective | data[0].permitted | data[0].inheritable | data[1].effective |
	    data[1].permitted | data[1].inheritable)
		return -1;
	return 0;
}

static int drop_privs(void)
{
	struct __user_cap_header_struct hdr;
	struct __user_cap_data_struct data[2];
	const uid_t user = 65534;
	const gid_t group = 65534;
	uid_t ruid = 1;
	uid_t euid = 1;
	uid_t suid = 1;
	gid_t rgid = 1;
	gid_t egid = 1;
	gid_t sgid = 1;
	gid_t extra = group;

	/* setgroups and the id changes need CAP_SETGID and CAP_SETUID.
	 * Clear capabilities only after real, effective, and saved ids are nobody.
	 * This does not open or chmod the owned cgroup; the cleanup owner keeps it.
	 */
	if (setgroups(0, &extra) != 0)
		return -1;
	if (setresgid(group, group, group) != 0)
		return -1;
	if (setresuid(user, user, user) != 0)
		return -1;
	if (getresuid(&ruid, &euid, &suid) != 0 || ruid != user || euid != user || suid != user)
		return -1;
	if (getresgid(&rgid, &egid, &sgid) != 0 || rgid != group || egid != group || sgid != group)
		return -1;
	memset(&hdr, 0, sizeof hdr);
	memset(data, 0, sizeof data);
	hdr.version = _LINUX_CAPABILITY_VERSION_3;
	hdr.pid = 0;
	if (syscall(__NR_capset, &hdr, data) != 0)
		return -1;
	if (caps_are_clear() != 0)
		return -1;
	if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0)
		return -1;
	if (seteuid(0) == 0 || geteuid() != user)
		return -1;
	return 0;
}

static int fixture_direct(void)
{
	volatile unsigned char word = 1;

	return word == 1 ? 0 : 127;
}

static int fixture_nested(void)
{
	pid_t child = fork();
	int status = 0;

	if (child < 0)
		return 127;
	if (child == 0) {
		pid_t grand = fork();
		if (grand < 0)
			_exit(127);
		if (grand == 0)
			_exit(0);
		if (waitpid(grand, &status, 0) < 0)
			_exit(127);
		_exit(WIFEXITED(status) && WEXITSTATUS(status) == 0 ? 0 : 127);
	}
	if (waitpid(child, &status, 0) < 0)
		return 127;
	return WIFEXITED(status) && WEXITSTATUS(status) == 0 ? 0 : 127;
}

static int fixture_orphan(void)
{
	int fds[2];
	pid_t child;

	if (pipe(fds) != 0)
		return 127;
	child = fork();
	if (child < 0)
		return 127;
	if (child == 0) {
		char byte = 0;
		close(fds[1]);
		if (read(fds[0], &byte, 1) < 0)
			_exit(127);
		_exit(0);
	}
	close(fds[1]);
	close(fds[0]);
	_exit(0);
}

static int thread_exit_fn(void *arg)
{
	(void)arg;
	syscall(SYS_exit, 0);
	return 0;
}

static int fixture_thread(void)
{
	void *stack;
	int flags;
	int rc;
	uint64_t deadline;

	stack = mmap(NULL, 65536, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_STACK, -1, 0);
	if (stack == MAP_FAILED)
		return 127;
	g_thread_tid = 1;
	flags = CLONE_THREAD | CLONE_SIGHAND | CLONE_VM | CLONE_FS | CLONE_FILES | CLONE_CHILD_CLEARTID;
	rc = clone(thread_exit_fn, (char *)stack + 65536, flags, NULL, NULL, NULL, &g_thread_tid);
	if (rc < 0)
		return 127;
	deadline = mono_ms() + 2000u;
	while (*(volatile int *)&g_thread_tid != 0) {
		if (mono_ms() >= deadline)
			return 127;
		sleep_ms(1);
	}
	return 0;
}

static int touch_pages(size_t bytes)
{
	long page = sysconf(_SC_PAGESIZE);
	unsigned char *mem;
	size_t off;

	if (page <= 0)
		return -1;
	mem = mmap(NULL, bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	if (mem == MAP_FAILED)
		return -1;
	for (off = 0; off < bytes; off += (size_t)page)
		mem[off] = 1;
	if (munmap(mem, bytes) != 0)
		return -1;
	return 0;
}

static int fixture_alloc(void)
{
	return touch_pages(2u * 1024u * 1024u) == 0 ? 0 : 127;
}

extern char **environ;

static int exec_payload(void)
{
	char *argv[] = {"/proc/self/exe", "--payload", NULL};

	execve("/proc/self/exe", argv, environ);
	return 127;
}

static int fixture_pre_exec(void)
{
	if (touch_pages(1024u * 1024u) != 0)
		return 127;
	return exec_payload();
}

static int thread_exec_fn(void *arg)
{
	(void)arg;
	_exit(exec_payload());
}

static int fixture_nonleader(void)
{
	void *stack;
	int flags;
	int rc;
	struct timespec ts;

	stack = mmap(NULL, 65536, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_STACK, -1, 0);
	if (stack == MAP_FAILED)
		return 127;
	flags = CLONE_THREAD | CLONE_SIGHAND | CLONE_VM | CLONE_FS | CLONE_FILES;
	rc = clone(thread_exec_fn, (char *)stack + 65536, flags, NULL, NULL, NULL, NULL);
	if (rc < 0)
		return 127;
	ts.tv_sec = 2;
	ts.tv_nsec = 0;
	nanosleep(&ts, NULL);
	return 127;
}

static int fixture_io_uring(void)
{
	unsigned char params[128];
	uint32_t flags = 2; /* IORING_SETUP_SQPOLL */
	long fd;

	memset(params, 0, sizeof params);
	memcpy(params + 8, &flags, sizeof flags);
	fd = syscall(__NR_io_uring_setup, 1, params);
	if (fd < 0)
		_exit(86);
	close((int)fd);
	return 0;
}

static int fixture_capacity(void)
{
	int fds[2];
	int started = 0;
	int i;

	if (pipe(fds) != 0)
		return 127;
	for (i = 0; i < LIFE_CAPACITY_CHILDREN; i++) {
		pid_t child = fork();
		if (child < 0)
			break;
		if (child == 0) {
			char byte = 0;
			close(fds[1]);
			if (read(fds[0], &byte, 1) < 0)
				_exit(127);
			_exit(0);
		}
		started++;
	}
	close(fds[1]);
	close(fds[0]);
	return started > LIFETIME_GROUP_SLOTS ? 0 : 127;
}

static int fixture_reset(void)
{
	int fd = open("/proc/self/clear_refs", O_WRONLY | O_CLOEXEC);
	int rc;

	if (fd < 0)
		return 127;
	rc = write_full(fd, "5", 1);
	close(fd);
	return rc == 0 ? 0 : 127;
}

static int run_fixture(uint32_t mode)
{
	struct rlimit limit;

	close_from_3();
	if (mode == LIFETIME_MODE_CAPACITY) {
		limit.rlim_cur = 8192;
		limit.rlim_max = 8192;
		if (setrlimit(RLIMIT_NPROC, &limit) != 0)
			return 127;
	}
	if (drop_privs() != 0)
		return 127;
	switch (mode) {
	case LIFETIME_MODE_DIRECT:
		return fixture_direct();
	case LIFETIME_MODE_NESTED:
		return fixture_nested();
	case LIFETIME_MODE_ORPHAN:
		return fixture_orphan();
	case LIFETIME_MODE_THREAD:
		return fixture_thread();
	case LIFETIME_MODE_ALLOC:
		return fixture_alloc();
	case LIFETIME_MODE_PRE_EXEC:
		return fixture_pre_exec();
	case LIFETIME_MODE_NONLEADER_EXEC:
		return fixture_nonleader();
	case LIFETIME_MODE_IO_URING:
		return fixture_io_uring();
	case LIFETIME_MODE_CAPACITY:
		return fixture_capacity();
	case LIFETIME_MODE_RESET:
		return fixture_reset();
	default:
		return 127;
	}
}

static int owner_is_outside(void)
{
	char buf[8192];
	char path[PATH_MAX];
	size_t n;

	if (g_cgroup_rel[0] != '/')
		return 0;
	if (read_path("/proc/self/cgroup", buf, sizeof buf) != 0)
		return 0;
	if (parse_exact_cgroup2_path(buf, path, sizeof path) != 0)
		return 0;
	if (strcmp(path, g_cgroup_rel) == 0)
		return 0;
	n = strlen(g_cgroup_rel);
	if (strncmp(path, g_cgroup_rel, n) == 0 && path[n] == '/')
		return 0;
	return 1;
}

static int probe_direct_launch(void)
{
	int fds[2];
	pid_t pid;
	int status = 0;
	char text[4096];
	int populated = -1;

	if (pipe(fds) != 0)
		return -1;
	g_keep_fd = fds[1];
	pid = clone3_into(g_dirfd);
	if (pid < 0) {
		close(fds[0]);
		close(fds[1]);
		return -1;
	}
	if (pid == 0) {
		char buf[4096];
		int fd;
		ssize_t n;
		close(fds[0]);
		fd = open("/proc/self/cgroup", O_RDONLY | O_CLOEXEC);
		if (fd < 0)
			_exit(127);
		n = read(fd, buf, sizeof buf);
		if (n < 0)
			_exit(127);
		if (write(fds[1], buf, (size_t)n) != n)
			_exit(127);
		_exit(0);
	}
	close(fds[1]);
	if (wait_pid_bounded(pid, &status, 2000u) != 0) {
		cgroup_kill_write(g_dirfd);
		wait_pid_bounded(pid, &status, LIFETIME_CLEANUP_MS);
		close(fds[0]);
		return -1;
	}
	if (read_full_fd(fds[0], text, sizeof text, NULL) != 0) {
		close(fds[0]);
		return -1;
	}
	close(fds[0]);
	if (!WIFEXITED(status) || WEXITSTATUS(status) != 0)
		return -1;
	{
		char path[PATH_MAX];
		if (parse_exact_cgroup2_path(text, path, sizeof path) != 0 || strcmp(path, g_cgroup_rel) != 0)
			return -1;
	}
	if (read_populated(g_dirfd, &populated) != 0 || populated != 0)
		return -1;
	return 0;
}

static const struct btf_type *skip_mods(const struct btf *btf, __u32 id)
{
	int depth = 0;

	while (id && depth++ < 16) {
		const struct btf_type *type = btf__type_by_id(btf, id);
		if (!type)
			return NULL;
		switch (btf_kind(type)) {
		case BTF_KIND_TYPEDEF:
		case BTF_KIND_VOLATILE:
		case BTF_KIND_CONST:
		case BTF_KIND_RESTRICT:
			id = type->type;
			break;
		default:
			return type;
		}
	}
	return NULL;
}

static int is_ptr_to_struct(const struct btf *btf, __u32 id, const char *name)
{
	const struct btf_type *type = skip_mods(btf, id);
	const char *got;

	if (!type || btf_kind(type) != BTF_KIND_PTR)
		return 0;
	type = skip_mods(btf, type->type);
	if (!type || btf_kind(type) != BTF_KIND_STRUCT)
		return 0;
	got = btf__name_by_offset(btf, type->name_off);
	return got && strcmp(got, name) == 0;
}

static int is_int_size(const struct btf *btf, __u32 id, __u32 size)
{
	const struct btf_type *type = skip_mods(btf, id);

	if (!type || btf_kind(type) != BTF_KIND_INT)
		return 0;
	return type->size == size;
}

static int func_proto(const struct btf *btf, const char *name, const struct btf_type **proto_out)
{
	int id = btf__find_by_name_kind(btf, name, BTF_KIND_FUNC);
	const struct btf_type *func;
	const struct btf_type *proto;

	if (id < 0)
		return -1;
	func = btf__type_by_id(btf, id);
	if (!func || btf_kind(func) != BTF_KIND_FUNC)
		return -1;
	proto = btf__type_by_id(btf, func->type);
	if (!proto || btf_kind(proto) != BTF_KIND_FUNC_PROTO)
		return -1;
	*proto_out = proto;
	return 0;
}

/* libbpf btf_member_bitfield_size reads this same kflag encoding. */
static __u32 member_bitfield_size(const struct btf_type *type, __u32 index)
{
	const struct btf_member *member = btf_members(type) + index;

	if (!BTF_INFO_KFLAG(type->info))
		return 0;
	return BTF_MEMBER_BITFIELD_SIZE(member->offset);
}

static int find_member(const struct btf *btf, const char *type_name, const char *member_name, __u32 *bitfield)
{
	int id = btf__find_by_name_kind(btf, type_name, BTF_KIND_STRUCT);
	const struct btf_type *type;
	const struct btf_member *members;
	__u16 count;
	__u16 i;

	if (id < 0)
		return -1;
	type = btf__type_by_id(btf, id);
	if (!type)
		return -1;
	members = btf_members(type);
	count = btf_vlen(type);
	for (i = 0; i < count; i++) {
		const char *name = btf__name_by_offset(btf, members[i].name_off);
		if (name && strcmp(name, member_name) == 0) {
			if (bitfield)
				*bitfield = member_bitfield_size(type, i);
			return 0;
		}
	}
	return -1;
}

static int prototypes_ok(const struct btf *btf, int *io_bitfield)
{
	const struct btf_type *proto = NULL;
	const struct btf_param *params;
	const char *task_fields[] = {
		"pid", "tgid", "cgroups", "signal", "real_parent", "start_time", "start_boottime", NULL
	};
	int i;
	__u32 io_bits = 0;

	g_receipt.config_taskstats = 0;
	g_receipt.config_cgroups = 0;
	*io_bitfield = -1;
	if (func_proto(btf, "taskstats_exit", &proto) == 0 && btf_vlen(proto) == 2) {
		params = btf_params(proto);
		if (is_ptr_to_struct(btf, params[0].type, "task_struct") && is_int_size(btf, params[1].type, 4))
			g_receipt.config_taskstats = 1;
	}
	if (find_member(btf, "css_set", "dfl_cgrp", NULL) == 0 &&
	    find_member(btf, "cgroup", "kn", NULL) == 0 &&
	    find_member(btf, "kernfs_node", "id", NULL) == 0 &&
	    find_member(btf, "signal_struct", "maxrss", NULL) == 0)
		g_receipt.config_cgroups = 1;
	for (i = 0; task_fields[i]; i++) {
		if (find_member(btf, "task_struct", task_fields[i], NULL) != 0)
			return -1;
	}
	if (find_member(btf, "kernel_clone_args", "flags", NULL) != 0)
		return -1;
	if (find_member(btf, "kernel_clone_args", "io_thread", &io_bits) != 0)
		return -1;
	*io_bitfield = io_bits > 0 ? 1 : 0;
	if (func_proto(btf, "copy_process", &proto) != 0 || btf_vlen(proto) != 4)
		return -1;
	if (!is_ptr_to_struct(btf, proto->type, "task_struct"))
		return -1;
	params = btf_params(proto);
	if (!is_ptr_to_struct(btf, params[0].type, "pid"))
		return -1;
	if (!is_int_size(btf, params[1].type, 4) || !is_int_size(btf, params[2].type, 4))
		return -1;
	if (!is_ptr_to_struct(btf, params[3].type, "kernel_clone_args"))
		return -1;
	return 0;
}

static int recursion_supported(int prog_fd, __u64 *misses)
{
	struct bpf_prog_info info;
	__u32 len = sizeof info;
	size_t need = offsetof(struct bpf_prog_info, recursion_misses) + sizeof(info.recursion_misses);

	memset(&info, 0, sizeof info);
	if (bpf_obj_get_info_by_fd(prog_fd, &info, &len) != 0)
		return -1;
	if ((size_t)len < need)
		return -1;
	if (misses)
		*misses = info.recursion_misses;
	return 0;
}

static int quiet_libbpf(enum libbpf_print_level level, const char *fmt, va_list args)
{
	(void)level;
	(void)fmt;
	(void)args;
	return 0;
}

static int exe_object(char *out, size_t cap, const char *name)
{
	char path[PATH_MAX];
	ssize_t n = readlink("/proc/self/exe", path, sizeof path - 1);
	char *slash;

	if (n <= 0)
		return -1;
	path[n] = 0;
	slash = strrchr(path, '/');
	if (!slash)
		return -1;
	*slash = 0;
	if (snprintf(out, cap, "%s/%s", path, name) >= (int)cap)
		return -1;
	return 0;
}

static int map_fd_by_name(struct bpf_object *obj, const char *name)
{
	struct bpf_map *map = bpf_object__find_map_by_name(obj, name);

	if (!map)
		return -1;
	return bpf_map__fd(map);
}

static int count_map_keys(int fd, size_t key_size)
{
	unsigned char key[32];
	unsigned char next[32];
	int count = 0;
	int rc;

	if (key_size > sizeof key)
		return -1;
	rc = bpf_map_get_next_key(fd, NULL, next);
	while (rc == 0) {
		count++;
		memcpy(key, next, key_size);
		rc = bpf_map_get_next_key(fd, key, next);
		if (count > 1000000)
			return -1;
	}
	if (rc != 0 && errno != ENOENT)
		return -1;
	return count;
}

static void fill_summaries(int completed_fd)
{
	struct lifetime_done_key key;
	struct lifetime_done_key next;
	int rc;
	uint32_t count = 0;

	memset(&key, 0, sizeof key);
	rc = bpf_map_get_next_key(completed_fd, NULL, &next);
	while (rc == 0) {
		struct lifetime_summary_rec rec;
		struct lifetime_summary summary;
		uint64_t bytes = 0;

		memset(&rec, 0, sizeof rec);
		memset(&summary, 0, sizeof summary);
		if (bpf_map_lookup_elem(completed_fd, &next, &rec) != 0) {
			g_receipt.observation_failed = 1;
			return;
		}
		if (count >= LIFETIME_SUMMARY_SLOTS) {
			g_receipt.observation_failed = 1;
			g_receipt.counters[LIFETIME_CTR_COMPLETED_OVERFLOW] += 1;
			return;
		}
		summary.kind = rec.kind;
		summary.category = rec.category;
		summary.exec_seen = rec.exec_seen;
		summary.cookie = rec.cookie;
		summary.group_cookie = rec.group_cookie;
		summary.creator_cookie = rec.creator_cookie;
		summary.maxrss_pages = rec.maxrss_pages;
		if (lifetime_pages_to_bytes(rec.maxrss_pages, g_receipt.page_size, &bytes) != 0) {
			summary.overflow = 1;
			summary.maxrss_bytes = 0;
			g_receipt.byte_overflow = 1;
			g_receipt.counters[LIFETIME_CTR_BYTE_OVERFLOW] += 1;
		} else {
			summary.maxrss_bytes = bytes;
		}
		memcpy((unsigned char *)&g_receipt + offsetof(struct lifetime_receipt, summaries) +
			       count * sizeof(summary),
		       &summary, sizeof summary);
		count++;
		key = next;
		rc = bpf_map_get_next_key(completed_fd, &key, &next);
	}
	if (rc != 0 && errno != ENOENT)
		g_receipt.observation_failed = 1;
	g_receipt.summary_count = count;
}

static void read_counters(int fd)
{
	__u32 index;

	for (index = 0; index < LIFETIME_CTR_COUNT; index++) {
		__u64 value = 0;
		if (bpf_map_lookup_elem(fd, &index, &value) != 0) {
			g_receipt.observation_failed = 1;
			return;
		}
		g_receipt.counters[index] = value;
	}
}

static int set_cfg(int fd, uint64_t cgroup_id, uint32_t enabled, struct lifetime_cfg *out)
{
	struct lifetime_cfg cfg;
	__u32 key = 0;

	memset(&cfg, 0, sizeof cfg);
	if (bpf_map_lookup_elem(fd, &key, &cfg) != 0)
		return -1;
	/* Seed once while disabled. A later disable must not rewind a live allocator. */
	if (!enabled) {
		if (cfg.next_task_cookie == 0)
			cfg.next_task_cookie = 1;
		if (cfg.next_group_cookie == 0)
			cfg.next_group_cookie = 1;
	}
	cfg.target_cgroup_id = cgroup_id;
	cfg.enabled = enabled;
	if (bpf_map_update_elem(fd, &key, &cfg, BPF_ANY) != 0)
		return -1;
	if (out)
		*out = cfg;
	return 0;
}

static void apply_cpu_delta(const struct cpu_view *start, int dirfd)
{
	struct cpu_view end;

	if (read_cpu(dirfd, &end) != 0 || !start->ok) {
		g_receipt.cpu_aggregate_ok = 0;
		return;
	}
	if (end.usage < start->usage || end.user < start->user || end.system < start->system) {
		g_receipt.cpu_aggregate_ok = 0;
		return;
	}
	g_receipt.cpu_usage_usec = end.usage - start->usage;
	g_receipt.cpu_user_usec = end.user - start->user;
	g_receipt.cpu_system_usec = end.system - start->system;
	g_receipt.cpu_aggregate_ok = 1;
}

static int census_is_quiet(int tasks_fd, int groups_fd, int counters_fd)
{
	int tasks = count_map_keys(tasks_fd, sizeof(__u64));
	int groups = count_map_keys(groups_fd, sizeof(__u64));
	__u64 births = 0;
	__u64 exits = 0;
	__u64 group_births = 0;
	__u64 group_finals = 0;
	__u32 key;

	if (tasks < 0 || groups < 0)
		return 0;
	key = LIFETIME_CTR_BIRTHS;
	if (bpf_map_lookup_elem(counters_fd, &key, &births) != 0)
		return 0;
	key = LIFETIME_CTR_TASK_EXITS;
	if (bpf_map_lookup_elem(counters_fd, &key, &exits) != 0)
		return 0;
	key = LIFETIME_CTR_GROUP_BIRTHS;
	if (bpf_map_lookup_elem(counters_fd, &key, &group_births) != 0)
		return 0;
	key = LIFETIME_CTR_GROUP_FINALS;
	if (bpf_map_lookup_elem(counters_fd, &key, &group_finals) != 0)
		return 0;
	return tasks == 0 && groups == 0 && births >= 1 && births == exits && group_births >= 1 &&
	       group_births == group_finals;
}

static void launch_blocker(void)
{
	int fds[2];
	pid_t pid;

	if (pipe(fds) != 0)
		_exit(127);
	g_keep_fd = fds[0];
	pid = clone3_into(g_dirfd);
	if (pid < 0)
		_exit(127);
	if (pid == 0) {
		char byte = 0;
		close(fds[1]);
		close_from_3_except(fds[0]);
		if (drop_privs() != 0)
			_exit(127);
		if (read(fds[0], &byte, 1) < 0)
			_exit(127);
		_exit(0);
	}
	close(fds[0]);
	g_receipt.fixture_launched = 1;
}

static void collector(int sock)
{
	struct btf *btf = NULL;
	struct bpf_object *obj = NULL;
	struct bpf_link *links[4] = {0};
	int prog_fds[4] = {-1, -1, -1, -1};
	int link_count = 0;
	int io_bitfield = -1;
	int clear_func = 0;
	int clear_proc = 0;
	char object_path[PATH_MAX];
	const char *object_name;
	struct life_msg msg;
	struct bpf_program *programs[4];
	const char *names[4] = {
		"lifetime_copy_process",
		"lifetime_taskstats_exit",
		"lifetime_sched_process_exec",
		"lifetime_clear_refs_write",
	};
	int cfg_fd = -1;
	int counters_fd = -1;
	int tasks_fd = -1;
	int groups_fd = -1;
	int completed_fd = -1;
	int i;
	__u64 baseline[4] = {0};
	struct cpu_view cpu_start;
	uint64_t work_deadline;
	const char *clear_name = "clear_refs_write";

	libbpf_set_print(quiet_libbpf);
	memset(&msg, 0, sizeof msg);
	msg.mode = g_mode;
	msg.page_size = g_receipt.page_size;
	msg.cgroup_id = g_cgroup_id;
	btf = btf__parse("/sys/kernel/btf/vmlinux", NULL);
	if (!btf || libbpf_get_error(btf)) {
		g_receipt.btf_ok = 0;
		g_receipt.prototype_ok = 0;
		seal_and_write();
		msg.code = LIFE_MSG_REFUSED;
		msg.reason = LIFETIME_REASON_BTF;
		send_msg(sock, &msg);
		_exit(1);
	}
	g_receipt.btf_ok = 1;
	clear_func = btf__find_by_name_kind(btf, clear_name, BTF_KIND_FUNC) >= 0;
	clear_proc = access("/proc/self/clear_refs", F_OK) == 0;
	if (prototypes_ok(btf, &io_bitfield) != 0 || io_bitfield < 0) {
		g_receipt.prototype_ok = 0;
		btf__free(btf);
		seal_and_write();
		msg.code = LIFE_MSG_REFUSED;
		msg.reason = LIFETIME_REASON_PROTOTYPE;
		msg.prototype_ok = 0;
		msg.config_taskstats = g_receipt.config_taskstats;
		msg.config_cgroups = g_receipt.config_cgroups;
		send_msg(sock, &msg);
		_exit(1);
	}
	g_receipt.prototype_ok = 1;
	if (!clear_func && !clear_proc) {
		g_receipt.clear_refs_state = LIFETIME_CLEAR_ABSENT;
	} else if (!clear_func && clear_proc) {
		g_receipt.clear_refs_state = LIFETIME_CLEAR_UNOBSERVABLE;
	}
	object_name = io_bitfield ? "lifetime_bitfield.bpf.o" : "lifetime_plain.bpf.o";
	g_receipt.io_thread_encoding = io_bitfield ? LIFETIME_IO_ENCODING_BITFIELD : LIFETIME_IO_ENCODING_PLAIN;
	if (exe_object(object_path, sizeof object_path, object_name) != 0) {
		g_receipt.btf_ok = 0;
		btf__free(btf);
		seal_and_write();
		msg.code = LIFE_MSG_REFUSED;
		send_msg(sock, &msg);
		_exit(1);
	}
	obj = bpf_object__open_file(object_path, NULL);
	if (!obj || libbpf_get_error(obj)) {
		btf__free(btf);
		seal_and_write();
		msg.code = LIFE_MSG_REFUSED;
		msg.reason = LIFETIME_REASON_LINK;
		send_msg(sock, &msg);
		_exit(1);
	}
	for (i = 0; i < 4; i++) {
		programs[i] = bpf_object__find_program_by_name(obj, names[i]);
		if (!programs[i]) {
			bpf_object__close(obj);
			btf__free(btf);
			seal_and_write();
			msg.code = LIFE_MSG_REFUSED;
			msg.reason = LIFETIME_REASON_LINK;
			send_msg(sock, &msg);
			_exit(1);
		}
	}
	if (g_receipt.clear_refs_state == LIFETIME_CLEAR_ABSENT ||
	    g_receipt.clear_refs_state == LIFETIME_CLEAR_UNOBSERVABLE)
		bpf_program__set_autoload(programs[3], false);
	if (bpf_object__load(obj) != 0) {
		bpf_object__close(obj);
		btf__free(btf);
		g_receipt.links_verified = 0;
		seal_and_write();
		msg.code = LIFE_MSG_REFUSED;
		msg.reason = LIFETIME_REASON_LINK;
		send_msg(sock, &msg);
		_exit(1);
	}
	cfg_fd = map_fd_by_name(obj, "lifetime_cfg");
	counters_fd = map_fd_by_name(obj, "lifetime_counters");
	tasks_fd = map_fd_by_name(obj, "lifetime_tasks");
	groups_fd = map_fd_by_name(obj, "lifetime_groups");
	completed_fd = map_fd_by_name(obj, "lifetime_completed");
	if (cfg_fd < 0 || counters_fd < 0 || tasks_fd < 0 || groups_fd < 0 || completed_fd < 0 ||
	    set_cfg(cfg_fd, g_cgroup_id, 0, NULL) != 0) {
		bpf_object__close(obj);
		btf__free(btf);
		seal_and_write();
		msg.code = LIFE_MSG_REFUSED;
		msg.reason = LIFETIME_REASON_LINK;
		send_msg(sock, &msg);
		_exit(1);
	}
	for (i = 0; i < 4; i++) {
		int fd;
		if (i == 3 && (g_receipt.clear_refs_state == LIFETIME_CLEAR_ABSENT ||
			       g_receipt.clear_refs_state == LIFETIME_CLEAR_UNOBSERVABLE))
			continue;
		links[link_count] = bpf_program__attach(programs[i]);
		if (!links[link_count] || libbpf_get_error(links[link_count])) {
			if (i == 3) {
				g_receipt.clear_refs_state = LIFETIME_CLEAR_ATTACH_FAILED;
				break;
			}
			bpf_object__close(obj);
			btf__free(btf);
			g_receipt.links_verified = 0;
			seal_and_write();
			msg.code = LIFE_MSG_REFUSED;
			msg.reason = LIFETIME_REASON_LINK;
			send_msg(sock, &msg);
			_exit(1);
		}
		fd = bpf_program__fd(programs[i]);
		prog_fds[link_count] = fd;
		if (recursion_supported(fd, &baseline[link_count]) != 0)
			g_receipt.recursion_field_ok = 0;
		link_count++;
		if (i == 3)
			g_receipt.clear_refs_state = LIFETIME_CLEAR_ATTACHED;
	}
	if (g_receipt.clear_refs_state == LIFETIME_CLEAR_ATTACHED ||
	    g_receipt.clear_refs_state == LIFETIME_CLEAR_ABSENT)
		g_receipt.links_verified = g_receipt.recursion_field_ok ? 1 : 0;
	else
		g_receipt.links_verified = 0;
	if (g_receipt.links_verified)
		g_receipt.enabled_after_validation = 1;
	msg.clear_refs_state = g_receipt.clear_refs_state;
	msg.io_encoding = g_receipt.io_thread_encoding;
	msg.links_verified = g_receipt.links_verified;
	msg.prototype_ok = g_receipt.prototype_ok;
	msg.recursion_field_ok = g_receipt.recursion_field_ok;
	msg.config_taskstats = g_receipt.config_taskstats;
	msg.config_cgroups = g_receipt.config_cgroups;
	msg.btf_ok = g_receipt.btf_ok;
	msg.enabled_after_validation = g_receipt.enabled_after_validation;
	if (!g_receipt.links_verified || !g_receipt.prototype_ok || !g_receipt.recursion_field_ok ||
	    !g_receipt.config_taskstats || !g_receipt.config_cgroups) {
		seal_and_write();
		msg.code = LIFE_MSG_REFUSED;
		send_msg(sock, &msg);
		bpf_object__close(obj);
		btf__free(btf);
		_exit(1);
	}
	msg.code = LIFE_MSG_ATTACHED;
	if (send_msg(sock, &msg) != 0) {
		bpf_object__close(obj);
		btf__free(btf);
		_exit(1);
	}
	if (recv_msg(sock, &msg) != 0 || (msg.code != LIFE_MSG_GO && msg.code != LIFE_MSG_VALIDATE)) {
		seal_and_write();
		bpf_object__close(obj);
		btf__free(btf);
		_exit(1);
	}
	if (msg.code == LIFE_MSG_VALIDATE) {
		g_receipt.collection_enabled = 0;
		g_receipt.fixture_launched = 0;
		seal_and_write();
		bpf_object__close(obj);
		btf__free(btf);
		_exit(0);
	}
	for (i = 0; i < link_count; i++) {
		if (recursion_supported(prog_fds[i], &baseline[i]) != 0) {
			g_receipt.observation_failed = 1;
			g_receipt.recursion_final_ok = 0;
		}
	}
	if (set_cfg(cfg_fd, g_cgroup_id, 1, NULL) != 0) {
		g_receipt.observation_failed = 1;
		seal_and_write();
		bpf_object__close(obj);
		btf__free(btf);
		_exit(1);
	}
	__sync_synchronize();
	g_receipt.collection_enabled = 1;
	memset(&cpu_start, 0, sizeof cpu_start);
	if (read_cpu(g_dirfd, &cpu_start) != 0)
		g_receipt.cpu_aggregate_ok = 0;
	if (g_mode == LIFETIME_MODE_COLLECTOR_DEATH) {
		launch_blocker();
		kill(getpid(), SIGKILL);
		_exit(127);
	}
	{
		pid_t child = clone3_into(g_dirfd);
		int status = 0;
		if (child < 0) {
			g_receipt.observation_failed = 1;
		} else if (child == 0) {
			_exit(run_fixture(g_mode));
		} else {
			g_receipt.fixture_launched = 1;
			if (waitpid(child, &status, 0) < 0)
				g_receipt.observation_failed = 1;
			else if (WIFEXITED(status) && WEXITSTATUS(status) == 86 && g_mode == LIFETIME_MODE_IO_URING)
				g_receipt.path_unsupported = 1;
			else if (!WIFEXITED(status) || WEXITSTATUS(status) != 0)
				g_receipt.observation_failed = 1;
		}
	}
	work_deadline = mono_ms() + LIFETIME_WORK_MS;
	while (mono_ms() < work_deadline) {
		if (census_is_quiet(tasks_fd, groups_fd, counters_fd))
			break;
		sleep_ms(50);
	}
	{
		int tasks = count_map_keys(tasks_fd, sizeof(__u64));
		int groups = count_map_keys(groups_fd, sizeof(__u64));
		struct lifetime_cfg cfg;
		__u32 key = 0;
		__u64 delta = 0;
		int miss_bad = 0;
		if (tasks < 0 || groups < 0)
			g_receipt.observation_failed = 1;
		g_receipt.active_tasks = tasks < 0 ? 0 : (uint32_t)tasks;
		g_receipt.active_groups = groups < 0 ? 0 : (uint32_t)groups;
		read_counters(counters_fd);
		fill_summaries(completed_fd);
		if (bpf_map_lookup_elem(cfg_fd, &key, &cfg) != 0)
			g_receipt.observation_failed = 1;
		else
			g_receipt.possible_peak_reset = cfg.possible_peak_reset ? 1 : 0;
		for (i = 0; i < link_count; i++) {
			__u64 now = 0;
			int lfd = links[i] ? bpf_link__fd(links[i]) : -1;
			if (lfd < 0) {
				g_receipt.detach_or_loss = 1;
				g_receipt.counters[LIFETIME_CTR_DETACH_EVENTS] += 1;
			}
			if (recursion_supported(prog_fds[i], &now) != 0 || now < baseline[i]) {
				miss_bad = 1;
				delta = 1;
			} else if (!miss_bad) {
				delta += now - baseline[i];
			}
		}
		g_receipt.counters[LIFETIME_CTR_RECURSION_MISS_DELTA] = delta;
		g_receipt.recursion_final_ok = !miss_bad && delta == 0 && g_receipt.recursion_field_ok;
		apply_cpu_delta(&cpu_start, g_dirfd);
		set_cfg(cfg_fd, g_cgroup_id, 0, NULL);
	}
	seal_and_write();
	bpf_object__close(obj);
	btf__free(btf);
	_exit(0);
}

static int static_checks_ok(void)
{
	if (g_receipt.arch != LIFETIME_ARCH_X86_64 && g_receipt.arch != LIFETIME_ARCH_AARCH64)
		return 0;
	if (!g_receipt.page_size_ok)
		return 0;
	if (!(g_receipt.cap_bpf && g_receipt.cap_perfmon) && !g_receipt.cap_sys_admin)
		return 0;
	if (g_receipt.lockdown_blocks || !g_receipt.btf_ok)
		return 0;
	if (!g_receipt.cgroup_ok || !g_receipt.cgroup_kill_ok || !g_receipt.populated_ok)
		return 0;
	if (!g_receipt.clone3_ok || !g_receipt.direct_launch_ok || !g_receipt.cpu_stat_ok)
		return 0;
	if (!g_receipt.containment_ok || g_receipt.launch_path != LIFETIME_LAUNCH_CLONE3)
		return 0;
	return 1;
}

static void owner_finish(pid_t child, int child_fd, int pidfd, int go_sent)
{
	int status = 0;
	int signaled = 0;
	uint64_t deadline = mono_ms() + LIFETIME_WORK_MS + LIFETIME_CLEANUP_MS + LIFE_OWNER_GRACE_MS;
	int exited = 0;

	for (;;) {
		pid_t got = waitpid(child, &status, WNOHANG);
		if (got == child) {
			exited = 1;
			break;
		}
		if (mono_ms() >= deadline)
			break;
		sleep_ms(20);
	}
	if (!exited && pidfd >= 0) {
		syscall(__NR_pidfd_send_signal, pidfd, SIGKILL, NULL, 0);
		wait_pid_bounded(child, &status, LIFETIME_CLEANUP_MS);
		signaled = 1;
	} else if (WIFSIGNALED(status)) {
		signaled = 1;
	}
	if (signaled) {
		struct lifetime_receipt saved = g_receipt;
		memset(&g_receipt, 0, sizeof g_receipt);
		g_receipt = saved;
		g_receipt.collector_death = 1;
		g_receipt.observation_failed = 1;
		g_receipt.coverage_pass = 0;
		g_receipt.fixture_launched = go_sent ? 1 : 0;
		g_receipt.collection_enabled = go_sent ? 1 : 0;
		memset(g_receipt.counters, 0, sizeof g_receipt.counters);
		g_receipt.summary_count = 0;
		g_receipt.active_tasks = 0;
		g_receipt.active_groups = 0;
		g_receipt.reason = LIFETIME_REASON_NONE;
		if (cleanup_tree()) {
			g_receipt.cleanup_attempted = 1;
			g_receipt.cleanup_pass = 1;
		} else {
			g_receipt.cleanup_attempted = 1;
			g_receipt.cleanup_pass = 0;
		}
		seal_and_write();
		if (pidfd >= 0)
			close(pidfd);
		close(child_fd);
		if (!go_sent)
			_exit(1);
		_exit(lifetime_mode_exit_ok(&g_receipt) ? 0 : 1);
	}
	if (pidfd >= 0)
		close(pidfd);
	close(child_fd);
	if (read_receipt(g_receipt_path, &g_receipt) != 0) {
		g_receipt.observation_failed = 1;
		g_receipt.cleanup_attempted = 1;
		g_receipt.cleanup_pass = cleanup_tree() ? 1 : 0;
		seal_and_write();
		_exit(1);
	}
	g_receipt.cleanup_attempted = 1;
	g_receipt.cleanup_pass = cleanup_tree() ? 1 : 0;
	g_receipt.known_fixture_births = 0;
	if (write_receipt(g_receipt_path, &g_receipt) != 0)
		note("receipt write failed");
	_exit(lifetime_mode_exit_ok(&g_receipt) ? 0 : 1);
}

static int setup_cgroup(void)
{
	char relative[PATH_MAX];
	char joined[PATH_MAX];
	char parent_real[PATH_MAX];
	char root_real[PATH_MAX];
	char leaf_real[PATH_MAX];
	int kill_fd;
	int populated = -1;
	struct cpu_view cpu;
	unsigned char rnd[8];

	if (access("/sys/fs/cgroup/cgroup.controllers", F_OK) != 0)
		return -1;
	if (cgroup_relative(relative, sizeof relative) != 0)
		return -1;
	if (snprintf(joined, sizeof joined, "/sys/fs/cgroup%s", relative) >= (int)sizeof joined)
		return -1;
	if (!realpath(joined, parent_real) || !realpath("/sys/fs/cgroup", root_real))
		return -1;
	if (!path_is_under(parent_real, root_real))
		return -1;
	if (getrandom(rnd, sizeof rnd, 0) != (ssize_t)sizeof rnd)
		return -1;
	if (snprintf(g_leaf_name, sizeof g_leaf_name, "mnemion-bpf-life-%02x%02x%02x%02x%02x%02x%02x%02x",
		     rnd[0], rnd[1], rnd[2], rnd[3], rnd[4], rnd[5], rnd[6], rnd[7]) >= (int)sizeof g_leaf_name)
		return -1;
	if (snprintf(g_cgroup_rel, sizeof g_cgroup_rel, "%s/%s", relative, g_leaf_name) >= (int)sizeof g_cgroup_rel)
		return -1;
	if (snprintf(g_leaf_path, sizeof g_leaf_path, "%s/%s", parent_real, g_leaf_name) >= (int)sizeof g_leaf_path)
		return -1;
	if (mkdir(g_leaf_path, 0755) != 0)
		return -1;
	if (!realpath(g_leaf_path, leaf_real) || !path_is_under(leaf_real, parent_real))
		return -1;
	memcpy(g_leaf_path, leaf_real, strlen(leaf_real) + 1);
	g_dirfd = open(g_leaf_path, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
	if (g_dirfd < 0)
		return -1;
	if (cgroup_id_of(g_dirfd, &g_cgroup_id) != 0)
		return -1;
	kill_fd = openat(g_dirfd, "cgroup.kill", O_WRONLY | O_CLOEXEC);
	if (kill_fd < 0)
		return -1;
	close(kill_fd);
	g_receipt.cgroup_kill_ok = 1;
	if (read_populated(g_dirfd, &populated) != 0 || populated != 0)
		return -1;
	g_receipt.populated_ok = 1;
	if (read_cpu(g_dirfd, &cpu) != 0)
		return -1;
	g_receipt.cpu_stat_ok = 1;
	g_receipt.cgroup_ok = 1;
	if (!owner_is_outside())
		return -1;
	g_receipt.containment = LIFETIME_CONTAIN_CGROUP_KILL;
	g_receipt.containment_ok = 1;
	return 0;
}

static void fill_identity(void)
{
	uint64_t caps = 0;
	long page;
	struct utsname uts;

	memset(&g_receipt, 0, sizeof g_receipt);
#if defined(__x86_64__)
	g_receipt.arch = LIFETIME_ARCH_X86_64;
#elif defined(__aarch64__)
	g_receipt.arch = LIFETIME_ARCH_AARCH64;
#else
	g_receipt.arch = 0;
#endif
	page = sysconf(_SC_PAGESIZE);
	if (page > 0) {
		g_receipt.page_size = (uint32_t)page;
		g_receipt.page_size_ok = lifetime_page_size_ok(g_receipt.page_size) ? 1 : 0;
	}
	if (read_capeff(&caps) == 0) {
		g_receipt.cap_bpf = cap_bit(caps, CAP_BPF) ? 1 : 0;
		g_receipt.cap_perfmon = cap_bit(caps, CAP_PERFMON) ? 1 : 0;
		g_receipt.cap_sys_admin = cap_bit(caps, CAP_SYS_ADMIN) ? 1 : 0;
	}
	g_receipt.privileges_ok = ((g_receipt.cap_bpf && g_receipt.cap_perfmon) || g_receipt.cap_sys_admin) ? 1 : 0;
	read_lockdown();
	if (uname(&uts) == 0) {
		snprintf((char *)g_receipt.kernel_release, sizeof g_receipt.kernel_release, "%s", uts.release);
	}
	g_receipt.mode = g_mode;
	g_receipt.launch_path = LIFETIME_LAUNCH_NONE;
	g_receipt.containment = LIFETIME_CONTAIN_NONE;
	g_receipt.known_fixture_births = 0;
	g_receipt.recursion_field_ok = 1;
	if (hash_btf(g_receipt.btf_digest) == 0)
		g_receipt.btf_ok = 1;
}

static int parse_mode(const char *text)
{
	if (strcmp(text, "admit") == 0)
		return LIFETIME_MODE_ADMIT;
	if (strcmp(text, "direct") == 0)
		return LIFETIME_MODE_DIRECT;
	if (strcmp(text, "nested") == 0)
		return LIFETIME_MODE_NESTED;
	if (strcmp(text, "orphan") == 0)
		return LIFETIME_MODE_ORPHAN;
	if (strcmp(text, "thread") == 0)
		return LIFETIME_MODE_THREAD;
	if (strcmp(text, "alloc") == 0)
		return LIFETIME_MODE_ALLOC;
	if (strcmp(text, "pre-exec") == 0)
		return LIFETIME_MODE_PRE_EXEC;
	if (strcmp(text, "nonleader-exec") == 0)
		return LIFETIME_MODE_NONLEADER_EXEC;
	if (strcmp(text, "io-uring") == 0)
		return LIFETIME_MODE_IO_URING;
	if (strcmp(text, "capacity") == 0)
		return LIFETIME_MODE_CAPACITY;
	if (strcmp(text, "reset") == 0)
		return LIFETIME_MODE_RESET;
	if (strcmp(text, "collector-death") == 0)
		return LIFETIME_MODE_COLLECTOR_DEATH;
	return -1;
}

int main(int argc, char **argv)
{
	const char *mode_text = NULL;
	const char *path = NULL;
	int i;
	int sv[2] = {-1, -1};
	pid_t child;
	int pidfd;
	struct life_msg msg;
	struct timeval tv;

	if (argc >= 2 && strcmp(argv[1], "--payload") == 0)
		_exit(0);
	for (i = 1; i < argc; i++) {
		if (strcmp(argv[i], "--mode") == 0 && i + 1 < argc)
			mode_text = argv[++i];
		else if (strcmp(argv[i], "--receipt") == 0 && i + 1 < argc)
			path = argv[++i];
		else {
			dprintf(STDERR_FILENO, "usage: lifetime_diag --mode <mode> --receipt <path>\n");
			return 2;
		}
	}
	if (!mode_text || !path || parse_mode(mode_text) < 0) {
		dprintf(STDERR_FILENO, "usage: lifetime_diag --mode <mode> --receipt <path>\n");
		return 2;
	}
	if (strlen(path) + 1 > sizeof g_receipt_path) {
		note("receipt path is too long");
		return 2;
	}
	memcpy(g_receipt_path, path, strlen(path) + 1);
	g_mode = (uint32_t)parse_mode(mode_text);
	prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0);
	signal(SIGPIPE, SIG_IGN);
	if (lifetime_sha256_selftest() != 0) {
		fill_identity();
		g_receipt.btf_ok = 0;
		g_receipt.reason = LIFETIME_REASON_DIGEST;
		seal_and_write();
		return 1;
	}
	fill_identity();
	if (setup_cgroup() != 0) {
		note("cgroup setup refused");
		g_receipt.cgroup_ok = g_dirfd >= 0 ? g_receipt.cgroup_ok : 0;
		g_receipt.cleanup_attempted = 1;
		g_receipt.cleanup_pass = cleanup_tree() ? 1 : 0;
		seal_and_write();
		return 1;
	}
	if (probe_direct_launch() == 0) {
		g_receipt.clone3_ok = 1;
		g_receipt.direct_launch_ok = 1;
		g_receipt.launch_path = LIFETIME_LAUNCH_CLONE3;
	} else {
		note("direct launch refused");
		g_receipt.cleanup_attempted = 1;
		g_receipt.cleanup_pass = cleanup_tree() ? 1 : 0;
		seal_and_write();
		return 1;
	}
	if (!static_checks_ok()) {
		note("admission refused before launch");
		g_receipt.cleanup_attempted = 1;
		g_receipt.cleanup_pass = cleanup_tree() ? 1 : 0;
		seal_and_write();
		return 1;
	}
	if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, sv) != 0) {
		g_receipt.cleanup_attempted = 1;
		g_receipt.cleanup_pass = cleanup_tree() ? 1 : 0;
		seal_and_write();
		return 1;
	}
	child = fork();
	if (child < 0) {
		close(sv[0]);
		close(sv[1]);
		g_receipt.cleanup_attempted = 1;
		g_receipt.cleanup_pass = cleanup_tree() ? 1 : 0;
		seal_and_write();
		return 1;
	}
	if (child == 0) {
		close(sv[0]);
		collector(sv[1]);
		_exit(1);
	}
	close(sv[1]);
	pidfd = (int)syscall(__NR_pidfd_open, child, 0);
	if (pidfd < 0) {
		close(sv[0]);
		wait_pid_bounded(child, NULL, 2000u);
		g_receipt.containment_ok = 0;
		g_receipt.observation_failed = 1;
		g_receipt.cleanup_attempted = 1;
		g_receipt.cleanup_pass = cleanup_tree() ? 1 : 0;
		seal_and_write();
		return 1;
	}
	tv.tv_sec = 20;
	tv.tv_usec = 0;
	setsockopt(sv[0], SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
	memset(&msg, 0, sizeof msg);
	if (recv_msg(sv[0], &msg) != 0 || msg.code == LIFE_MSG_REFUSED) {
		int status = 0;
		waitpid(child, &status, 0);
		close(pidfd);
		close(sv[0]);
		if (read_receipt(g_receipt_path, &g_receipt) != 0)
			g_receipt.observation_failed = 1;
		g_receipt.cleanup_attempted = 1;
		g_receipt.cleanup_pass = cleanup_tree() ? 1 : 0;
		g_receipt.known_fixture_births = 0;
		write_receipt(g_receipt_path, &g_receipt);
		return lifetime_mode_exit_ok(&g_receipt) ? 0 : 1;
	}
	if (msg.code != LIFE_MSG_ATTACHED || !msg.links_verified || !msg.prototype_ok || !msg.recursion_field_ok ||
	    (msg.clear_refs_state != LIFETIME_CLEAR_ABSENT && msg.clear_refs_state != LIFETIME_CLEAR_ATTACHED) ||
	    !msg.enabled_after_validation) {
		struct life_msg stop;
		memset(&stop, 0, sizeof stop);
		stop.code = LIFE_MSG_STOP;
		send_msg(sv[0], &stop);
		owner_finish(child, sv[0], pidfd, 0);
	}
	g_receipt.clear_refs_state = msg.clear_refs_state;
	g_receipt.io_thread_encoding = msg.io_encoding;
	g_receipt.links_verified = msg.links_verified;
	g_receipt.prototype_ok = msg.prototype_ok;
	g_receipt.recursion_field_ok = msg.recursion_field_ok;
	g_receipt.config_taskstats = msg.config_taskstats;
	g_receipt.config_cgroups = msg.config_cgroups;
	g_receipt.btf_ok = msg.btf_ok;
	g_receipt.enabled_after_validation = msg.enabled_after_validation;
	memset(&msg, 0, sizeof msg);
	msg.code = g_mode == LIFETIME_MODE_ADMIT ? LIFE_MSG_VALIDATE : LIFE_MSG_GO;
	msg.mode = g_mode;
	if (send_msg(sv[0], &msg) != 0)
		owner_finish(child, sv[0], pidfd, 0);
	owner_finish(child, sv[0], pidfd, msg.code == LIFE_MSG_GO);
	return 1;
}
