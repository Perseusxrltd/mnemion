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
#include <poll.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/random.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/utsname.h>
#include <sys/wait.h>

#include "admission_guard.h"

#include <bpf/bpf.h>
#include <bpf/btf.h>
#include <bpf/libbpf.h>

/* libbpf.map puts libbpf_major_version and libbpf_minor_version in
 * LIBBPF_0.6.0, which inherits LIBBPF_0.5.0. The 0.5 baseline does not
 * export them. A weak reference still links. Header macros are the build
 * header. A resolved symbol is the loaded library. Neither is the apt package.
 */
#ifndef LIBBPF_MAJOR_VERSION
extern unsigned int libbpf_major_version(void) __attribute__((weak));
extern unsigned int libbpf_minor_version(void) __attribute__((weak));
#endif

#include <linux/types.h>
#define LIFETIME_HAVE_U_TYPES
#include "lifetime_receipt.h"
#include "lifetime_sha256.h"

/* The guardian process stays outside the owned cgroup. It alone writes
 * cgroup.kill, and it holds the directory fd across controller death.
 * Descendants are not stopped by historical numeric process ids.
 * Scope is no external migration: a process a privileged outsider moves
 * out is outside this claim. Birth launch is clone3 with
 * CLONE_INTO_CGROUP. A write of a process id before exec is not this path.
 * Collection modes are not entered from this slice.
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
static int g_is_guardian;
static int g_clone_permitted;
static struct timespec g_admission_deadline;

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
	for (;;) {
		ssize_t n = recv(fd, msg, sizeof(*msg), 0);

		if (n < 0 && errno == EINTR)
			continue;
		return n == (ssize_t)sizeof(*msg) ? 0 : -1;
	}
}

static int recv_msg_until(int fd, struct life_msg *msg, const struct timespec *deadline)
{
	for (;;) {
		struct pollfd pfd;
		int remain = 0;
		int rc;

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
		if (recv_msg(fd, msg) == 0)
			return 0;
		return -1;
	}
}

static int recv_exact_until(int fd, void *buf, size_t len, const struct timespec *deadline)
{
	for (;;) {
		struct pollfd pfd;
		int remain = 0;
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
		n = recv(fd, buf, len, 0);
		if (n < 0 && errno == EINTR)
			continue;
		return n == (ssize_t)len ? 0 : -1;
	}
}

/* Memory only. The guardian is the one writer and it publishes after cleanup. */
static void seal_and_write(void)
{
	g_receipt.known_fixture_births = 0;
	if (g_receipt.reason == LIFETIME_REASON_NONE && g_preset_reason != LIFETIME_REASON_NONE)
		g_receipt.reason = g_preset_reason;
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
	int fd;

	if (!g_is_guardian || dirfd < 0)
		return -1;
	fd = openat(dirfd, "cgroup.kill", O_WRONLY | O_CLOEXEC);
	char one = '1';
	int rc;

	if (fd < 0)
		return -1;
	rc = write_full(fd, &one, 1);
	close(fd);
	return rc;
}

static int cleanup_kill(int dirfd, void *ctx)
{
	(void)ctx;
	return cgroup_kill_write(dirfd);
}

static int cleanup_populated(int dirfd, int *out, void *ctx)
{
	(void)ctx;
	return read_populated(dirfd, out);
}

static int cleanup_remove(void *ctx)
{
	char *path = ctx;

	if (!path || !path[0])
		return -1;
	return rmdir(path) == 0 ? 0 : -1;
}

static pid_t clone3_into(int dirfd)
{
	struct lifetime_clone_args args;

	if (!g_clone_permitted || dirfd < 0)
		return -1;
	memset(&args, 0, sizeof args);
	args.flags = CLONE_INTO_CGROUP;
	args.exit_signal = SIGCHLD;
	args.cgroup = (uint64_t)dirfd;
	return (pid_t)syscall(__NR_clone3, &args, sizeof args);
}

static int wait_pid_until(pid_t pid, int *status, const struct timespec *deadline)
{
	for (;;) {
		int remain = 0;
		pid_t got = waitpid(pid, status, WNOHANG);

		if (got == pid)
			return 0;
		if (got < 0 && errno != EINTR)
			return -1;
		if (guard_remaining_ms(deadline, &remain) != 0)
			return -1;
		if (poll(NULL, 0, remain > 20 ? 20 : remain) < 0 && errno != EINTR)
			return -1;
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
		int keep = fds[1];
		pid_t parent = getppid();

		/* Controller death delivers SIGKILL. The guardian still has to reap the zombie. */
		if (prctl(PR_SET_PDEATHSIG, SIGKILL) != 0 || getppid() != parent)
			_exit(127);
		if (g_dirfd >= 0 && g_dirfd != keep)
			close(g_dirfd);
		g_dirfd = -1;
		close(fds[0]);
		close_from_3_except(keep);
		fd = open("/proc/self/cgroup", O_RDONLY | O_CLOEXEC);
		if (fd < 0)
			_exit(127);
		n = read(fd, buf, sizeof buf);
		if (n < 0)
			_exit(127);
		if (write(keep, buf, (size_t)n) != n)
			_exit(127);
		_exit(0);
	}
	g_receipt.clone3_ok = 1;
	close(fds[1]);
	{
		struct timespec preflight_deadline = g_admission_deadline;
		struct timespec short_deadline;

		if (clock_gettime(CLOCK_MONOTONIC, &short_deadline) != 0) {
			close(fds[0]);
			return -1;
		}
		guard_add_ms(&short_deadline, 2000u);
		if (short_deadline.tv_sec < preflight_deadline.tv_sec ||
		    (short_deadline.tv_sec == preflight_deadline.tv_sec &&
		     short_deadline.tv_nsec < preflight_deadline.tv_nsec))
			preflight_deadline = short_deadline;
		if (wait_pid_until(pid, &status, &preflight_deadline) != 0) {
			close(fds[0]);
			/* Pin before signaling. ECHILD from the following wait is not success. */
			guard_signal_pinned(pid, SIGKILL);
			if (wait_pid_until(pid, &status, &preflight_deadline) != 0)
				dprintf(STDERR_FILENO, "lifetime_diag: unreaped_preflight=%d\n", (int)pid);
			return -1;
		}
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
	g_receipt.direct_launch_ok = 1;
	g_receipt.launch_path = LIFETIME_LAUNCH_CLONE3;
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

static int g_worker_park = -1;

static int release_links(struct bpf_link **links, int n, struct bpf_object **obj, struct btf **btf)
{
	int rc = 0;
	int i;

	for (i = 0; i < n; i++) {
		if (!links[i] || libbpf_get_error(links[i])) {
			links[i] = NULL;
			continue;
		}
		if (bpf_link__destroy(links[i]) != 0)
			rc = -1;
		links[i] = NULL;
	}
	if (obj && *obj) {
		bpf_object__close(*obj);
		*obj = NULL;
	}
	if (btf && *btf) {
		btf__free(*btf);
		*btf = NULL;
	}
	return rc;
}

struct lifetime_btf_class {
	int code;
	const char *name;
};

/* Numbers only. A code that is not listed stays unknown, including 4002
 * (LIBBPF_ERRNO__KVERSION). The name classifies the captured number.
 */
static const struct lifetime_btf_class lifetime_btf_classes[] = {
	{1, "access"},
	{2, "absent"},
	{7, "size"},
	{12, "memory"},
	{13, "access"},
	{22, "invalid"},
	{27, "size"},
	{38, "unsupported"},
	{61, "format"},
	{71, "format"},
	{75, "size"},
	{95, "unsupported"},
	{4000, "elf"},
	{4001, "format"},
	{4003, "endian"},
	{4004, "internal"},
};

_Static_assert(EPERM == 1, "eperm");
_Static_assert(ENOENT == 2, "enoent");
_Static_assert(E2BIG == 7, "e2big");
_Static_assert(ENOMEM == 12, "enomem");
_Static_assert(EACCES == 13, "eacces");
_Static_assert(EINVAL == 22, "einval");
_Static_assert(EFBIG == 27, "efbig");
_Static_assert(ENOSYS == 38, "enosys");
_Static_assert(ENODATA == 61, "enodata");
_Static_assert(EPROTO == 71, "eproto");
_Static_assert(EOVERFLOW == 75, "eoverflow");
_Static_assert(EOPNOTSUPP == 95, "eopnotsupp");
_Static_assert(LIBBPF_ERRNO__LIBELF == 4000, "libbpf elf");
_Static_assert(LIBBPF_ERRNO__FORMAT == 4001, "libbpf format");
_Static_assert(LIBBPF_ERRNO__ENDIAN == 4003, "libbpf endian");
_Static_assert(LIBBPF_ERRNO__INTERNAL == 4004, "libbpf internal");

struct lifetime_libbpf_version {
	int known;
	unsigned major;
	unsigned minor;
};

static const char *lifetime_btf_class_name(int code)
{
	size_t i;

	if (code == 0)
		return "null";
	for (i = 0; i < sizeof lifetime_btf_classes / sizeof lifetime_btf_classes[0]; i++) {
		if (lifetime_btf_classes[i].code == code)
			return lifetime_btf_classes[i].name;
	}
	return "unknown";
}

static int lifetime_btf_text_ok(const char *value)
{
	size_t n = 0;

	if (!value || !value[0])
		return 0;
	for (; value[n]; n++) {
		unsigned char c = (unsigned char)value[n];

		if (n >= 31)
			return 0;
		if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_' || c == '.' || c == '-'))
			return 0;
	}
	return 1;
}

static int lifetime_btf_category_ok(const char *value)
{
	size_t i;

	if (strcmp(value, "null") == 0 || strcmp(value, "unknown") == 0)
		return 1;
	for (i = 0; i < sizeof lifetime_btf_classes / sizeof lifetime_btf_classes[0]; i++) {
		if (strcmp(value, lifetime_btf_classes[i].name) == 0)
			return 1;
	}
	return 0;
}

static int lifetime_btf_version_text(char *out, size_t cap, int known, unsigned major, unsigned minor)
{
	int n;

	if (!known || major > 999u || minor > 999u)
		n = snprintf(out, cap, "unavailable");
	else
		n = snprintf(out, cap, "%u.%u", major, minor);
	if (n < 0 || (size_t)n >= cap || !lifetime_btf_text_ok(out))
		return -1;
	return 0;
}

static int lifetime_btf_line_ok(const char *line)
{
	char pointer[32];
	char category[32];
	char build[32];
	char runtime[32];
	char again[256];
	int saved_errno = 0;
	long libbpf_error = 0;
	unsigned worker_reason = 0;
	int consumed = -1;
	int n;
	size_t i;
	size_t len;

	if (!line)
		return 0;
	len = strlen(line);
	if (len < 2 || len > 240 || line[len - 1] != '\n')
		return 0;
	for (i = 0; i + 1 < len; i++) {
		unsigned char c = (unsigned char)line[i];

		if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '=' || c == '_' || c == '.' ||
		      c == '-' || c == ' '))
			return 0;
	}
	n = sscanf(line,
		   "stage=btf_parse pointer=%31s errno=%d libbpf_error=%ld category=%31s worker_reason=%u build_header=%31s runtime_linkage=%31s%n",
		   pointer, &saved_errno, &libbpf_error, category, &worker_reason, build, runtime, &consumed);
	if (n != 7 || consumed < 0 || (size_t)consumed + 1 != len || line[consumed] != '\n')
		return 0;
	if (!lifetime_btf_text_ok(pointer) || !lifetime_btf_text_ok(category) || !lifetime_btf_text_ok(build) ||
	    !lifetime_btf_text_ok(runtime))
		return 0;
	if (strcmp(pointer, "null") != 0 && strcmp(pointer, "error_pointer") != 0 &&
	    strcmp(pointer, "unknown") != 0)
		return 0;
	if (!lifetime_btf_category_ok(category))
		return 0;
	if (saved_errno < 0 || saved_errno > 999999 || libbpf_error < -999999L || libbpf_error > 999999L ||
	    worker_reason > 999u)
		return 0;
	if ((strcmp(build, "unavailable") != 0 && strchr(build, '.') == NULL) ||
	    (strcmp(runtime, "unavailable") != 0 && strchr(runtime, '.') == NULL))
		return 0;
	n = snprintf(again, sizeof again,
		     "stage=btf_parse pointer=%s errno=%d libbpf_error=%ld category=%s worker_reason=%u build_header=%s runtime_linkage=%s\n",
		     pointer, saved_errno, libbpf_error, category, worker_reason, build, runtime);
	if (n < 0 || (size_t)n >= sizeof again || strcmp(again, line) != 0)
		return 0;
	return 1;
}

static void lifetime_libbpf_versions(struct lifetime_libbpf_version *build,
				    struct lifetime_libbpf_version *runtime)
{
	memset(build, 0, sizeof *build);
	memset(runtime, 0, sizeof *runtime);
#ifdef LIBBPF_MAJOR_VERSION
	build->major = LIBBPF_MAJOR_VERSION;
#ifdef LIBBPF_MINOR_VERSION
	build->minor = LIBBPF_MINOR_VERSION;
	build->known = build->major <= 999u && build->minor <= 999u;
#endif
	{
		unsigned int major = libbpf_major_version();
		unsigned int minor = libbpf_minor_version();

		if (major <= 999u && minor <= 999u) {
			runtime->known = 1;
			runtime->major = major;
			runtime->minor = minor;
		}
	}
#else
	{
		unsigned int (*major_fn)(void) = libbpf_major_version;
		unsigned int (*minor_fn)(void) = libbpf_minor_version;

		if (major_fn && minor_fn) {
			unsigned int major = major_fn();
			unsigned int minor = minor_fn();

			if (major <= 999u && minor <= 999u) {
				runtime->known = 1;
				runtime->major = major;
				runtime->minor = minor;
			}
		}
	}
#endif
}

static int lifetime_btf_format_line(char *out, size_t cap, const char *pointer, int saved_errno,
				   long libbpf_error, const char *category, uint32_t worker_reason,
				   const struct lifetime_libbpf_version *build,
				   const struct lifetime_libbpf_version *runtime)
{
	char build_text[16];
	char runtime_text[16];
	int n;

	if (lifetime_btf_version_text(build_text, sizeof build_text, build->known, build->major, build->minor) !=
		    0 ||
	    lifetime_btf_version_text(runtime_text, sizeof runtime_text, runtime->known, runtime->major,
				      runtime->minor) != 0)
		return -1;
	if (saved_errno < 0 || saved_errno > 999999 || libbpf_error < -999999L || libbpf_error > 999999L ||
	    worker_reason > 999u || !lifetime_btf_text_ok(pointer) || !lifetime_btf_category_ok(category))
		return -1;
	n = snprintf(out, cap,
		     "stage=btf_parse pointer=%s errno=%d libbpf_error=%ld category=%s worker_reason=%u build_header=%s runtime_linkage=%s\n",
		     pointer, saved_errno, libbpf_error, category, worker_reason, build_text, runtime_text);
	if (n < 0 || (size_t)n >= cap || !lifetime_btf_line_ok(out))
		return -1;
	return 0;
}

static int lifetime_btf_fallback_line(char *out, size_t cap, uint32_t worker_reason)
{
	uint32_t reason = worker_reason >= 1u && worker_reason <= LIFETIME_REASON_DIGEST ? worker_reason : 0u;
	int n = snprintf(out, cap,
			 "stage=btf_parse pointer=unknown errno=0 libbpf_error=0 category=unknown worker_reason=%u build_header=unavailable runtime_linkage=unavailable\n",
			 reason);

	if (n < 0 || (size_t)n >= cap || !lifetime_btf_line_ok(out))
		return -1;
	return 0;
}

static void lifetime_btf_store_line(const char *line)
{
	char path[PATH_MAX];
	size_t base;
	size_t len;
	int fd;

	if (!lifetime_btf_line_ok(line)) {
		note("btf parse diagnostic was not retained");
		return;
	}
	base = strlen(g_receipt_path);
	if (base == 0 || base + sizeof ".btf-diag" > sizeof path) {
		note("btf parse diagnostic was not retained");
		return;
	}
	memcpy(path, g_receipt_path, base);
	memcpy(path + base, ".btf-diag", sizeof ".btf-diag");
	fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
	if (fd < 0) {
		note("btf parse diagnostic was not retained");
		return;
	}
	len = strlen(line);
	if (write_full(fd, line, len) != 0) {
		close(fd);
		unlink(path);
		note("btf parse diagnostic was not retained");
		return;
	}
	if (close(fd) != 0)
		note("btf parse diagnostic was not retained");
}

static void lifetime_btf_retain_parse_failure(int saved_errno, long libbpf_error, int pointer_is_null,
					     uint32_t worker_reason)
{
	char line[256];
	const char *pointer = NULL;
	struct lifetime_libbpf_version build;
	struct lifetime_libbpf_version runtime;
	int formatted = -1;

	memset(line, 0, sizeof line);
	if (pointer_is_null)
		pointer = "null";
	else if (libbpf_error != 0)
		pointer = "error_pointer";
	if (pointer && saved_errno >= 0 && saved_errno <= 999999 && libbpf_error >= -999999L &&
	    libbpf_error <= 999999L && worker_reason <= 999u) {
		int magnitude = saved_errno;

		if (libbpf_error != 0)
			magnitude = (int)(libbpf_error < 0 ? -libbpf_error : libbpf_error);
		lifetime_libbpf_versions(&build, &runtime);
		formatted = lifetime_btf_format_line(line, sizeof line, pointer, saved_errno, libbpf_error,
						    lifetime_btf_class_name(magnitude), worker_reason, &build,
						    &runtime);
	}
	if (formatted != 0 && lifetime_btf_fallback_line(line, sizeof line, worker_reason) != 0) {
		note("btf parse diagnostic was not retained");
		return;
	}
	lifetime_btf_store_line(line);
}

static void lifetime_keep_worker_reason(struct lifetime_receipt *receipt, uint32_t worker_reason)
{
	if (!receipt)
		return;
	if (worker_reason < 1u || worker_reason > LIFETIME_REASON_DIGEST)
		return;
	receipt->reason = worker_reason;
}

static void collector_finish(int sock, struct bpf_link **links, int n, struct bpf_object **obj,
			     struct btf **btf, uint32_t code, uint32_t reason, int status)
{
	struct life_msg out;

	if (release_links(links, n, obj, btf) != 0) {
		g_receipt.observation_failed = 1;
		g_receipt.detach_or_loss = 1;
		g_receipt.links_verified = 0;
		g_receipt.enabled_after_validation = 0;
		if (status == 0)
			status = 1;
	}
	memset(&out, 0, sizeof out);
	out.code = code;
	out.reason = reason;
	out.mode = g_mode;
	out.page_size = g_receipt.page_size;
	out.cgroup_id = g_cgroup_id;
	out.clear_refs_state = g_receipt.clear_refs_state;
	out.io_encoding = g_receipt.io_thread_encoding;
	out.links_verified = g_receipt.links_verified;
	out.prototype_ok = g_receipt.prototype_ok;
	out.recursion_field_ok = g_receipt.recursion_field_ok;
	out.config_taskstats = g_receipt.config_taskstats;
	out.config_cgroups = g_receipt.config_cgroups;
	out.btf_ok = g_receipt.btf_ok;
	out.enabled_after_validation = g_receipt.enabled_after_validation;
	send_msg(sock, &out);
	if (send(sock, &g_receipt, sizeof g_receipt, MSG_NOSIGNAL) != (ssize_t)sizeof g_receipt)
		status = 1;
	_exit(status);
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
	int saved_errno = 0;
	long saved_libbpf = 0;
	__u64 baseline[4] = {0};
	struct cpu_view cpu_start;
	uint64_t work_deadline;
	const char *clear_name = "clear_refs_write";

	if (g_worker_park >= 0) {
		char byte = 0;

		if (read(g_worker_park, &byte, 1) != 1)
			_exit(1);
		close(g_worker_park);
		g_worker_park = -1;
	}
	if (g_dirfd >= 0) {
		close(g_dirfd);
		g_dirfd = -1;
	}
	libbpf_set_print(quiet_libbpf);
	memset(&msg, 0, sizeof msg);
	msg.mode = g_mode;
	msg.page_size = g_receipt.page_size;
	msg.cgroup_id = g_cgroup_id;
	/* Save errno before libbpf_get_error. A NULL return keeps the code in
	 * errno; an error pointer keeps it in the pointer. Both are recorded.
	 * The refusal does not become success when the record cannot be stored.
	 */
	errno = 0;
	btf = btf__parse("/sys/kernel/btf/vmlinux", NULL);
	saved_errno = errno;
	saved_libbpf = libbpf_get_error(btf);
	if (!btf || saved_libbpf) {
		int pointer_is_null = btf == NULL;

		g_receipt.btf_ok = 0;
		g_receipt.prototype_ok = 0;
		lifetime_btf_retain_parse_failure(saved_errno, saved_libbpf, pointer_is_null,
						  LIFETIME_REASON_BTF);
		btf = NULL;
		collector_finish(sock, links, 0, &obj, &btf, LIFE_MSG_REFUSED, LIFETIME_REASON_BTF, 1);
	}
	g_receipt.btf_ok = 1;
	clear_func = btf__find_by_name_kind(btf, clear_name, BTF_KIND_FUNC) >= 0;
	clear_proc = access("/proc/self/clear_refs", F_OK) == 0;
	if (prototypes_ok(btf, &io_bitfield) != 0 || io_bitfield < 0) {
		g_receipt.prototype_ok = 0;
		collector_finish(sock, links, 0, &obj, &btf, LIFE_MSG_REFUSED, LIFETIME_REASON_PROTOTYPE, 1);
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
		collector_finish(sock, links, 0, &obj, &btf, LIFE_MSG_REFUSED, LIFETIME_REASON_LINK, 1);
	}
	obj = bpf_object__open_file(object_path, NULL);
	if (!obj || libbpf_get_error(obj)) {
		obj = NULL;
		collector_finish(sock, links, 0, &obj, &btf, LIFE_MSG_REFUSED, LIFETIME_REASON_LINK, 1);
	}
	for (i = 0; i < 4; i++) {
		programs[i] = bpf_object__find_program_by_name(obj, names[i]);
		if (!programs[i])
			collector_finish(sock, links, 0, &obj, &btf, LIFE_MSG_REFUSED, LIFETIME_REASON_LINK, 1);
	}
	if (g_receipt.clear_refs_state == LIFETIME_CLEAR_ABSENT ||
	    g_receipt.clear_refs_state == LIFETIME_CLEAR_UNOBSERVABLE)
		bpf_program__set_autoload(programs[3], false);
	if (bpf_object__load(obj) != 0) {
		g_receipt.links_verified = 0;
		collector_finish(sock, links, 0, &obj, &btf, LIFE_MSG_REFUSED, LIFETIME_REASON_LINK, 1);
	}
	cfg_fd = map_fd_by_name(obj, "lifetime_cfg");
	counters_fd = map_fd_by_name(obj, "lifetime_counters");
	tasks_fd = map_fd_by_name(obj, "lifetime_tasks");
	groups_fd = map_fd_by_name(obj, "lifetime_groups");
	completed_fd = map_fd_by_name(obj, "lifetime_completed");
	if (cfg_fd < 0 || counters_fd < 0 || tasks_fd < 0 || groups_fd < 0 || completed_fd < 0 ||
	    set_cfg(cfg_fd, g_cgroup_id, 0, NULL) != 0) {
		collector_finish(sock, links, 0, &obj, &btf, LIFE_MSG_REFUSED, LIFETIME_REASON_LINK, 1);
	}
	for (i = 0; i < 4; i++) {
		int fd;
		if (i == 3 && (g_receipt.clear_refs_state == LIFETIME_CLEAR_ABSENT ||
			       g_receipt.clear_refs_state == LIFETIME_CLEAR_UNOBSERVABLE))
			continue;
		links[link_count] = bpf_program__attach(programs[i]);
		if (!links[link_count] || libbpf_get_error(links[link_count])) {
			links[link_count] = NULL;
			if (i == 3) {
				g_receipt.clear_refs_state = LIFETIME_CLEAR_ATTACH_FAILED;
				break;
			}
			g_receipt.links_verified = 0;
			collector_finish(sock, links, link_count, &obj, &btf, LIFE_MSG_REFUSED,
					 LIFETIME_REASON_LINK, 1);
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
		collector_finish(sock, links, link_count, &obj, &btf, LIFE_MSG_REFUSED,
				 g_receipt.reason != LIFETIME_REASON_NONE ? g_receipt.reason
									  : LIFETIME_REASON_LINK,
				 1);
	}
	msg.code = LIFE_MSG_ATTACHED;
	if (send_msg(sock, &msg) != 0)
		collector_finish(sock, links, link_count, &obj, &btf, LIFE_MSG_REFUSED, LIFETIME_REASON_LINK, 1);
	if (recv_msg_until(sock, &msg, &g_admission_deadline) != 0 ||
	    (msg.code != LIFE_MSG_GO && msg.code != LIFE_MSG_VALIDATE)) {
		collector_finish(sock, links, link_count, &obj, &btf, LIFE_MSG_REFUSED, LIFETIME_REASON_LINK, 1);
	}
	if (g_mode == LIFETIME_MODE_ADMIT || msg.code == LIFE_MSG_VALIDATE) {
		if (g_mode != LIFETIME_MODE_ADMIT || msg.code != LIFE_MSG_VALIDATE) {
			g_receipt.observation_failed = 1;
			collector_finish(sock, links, link_count, &obj, &btf, LIFE_MSG_REFUSED,
					 LIFETIME_REASON_UNSUPPORTED, 1);
		}
		collector_finish(sock, links, link_count, &obj, &btf, LIFE_MSG_VALIDATE, LIFETIME_REASON_NONE,
				 g_receipt.links_verified ? 0 : 1);
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

/* Cheap gates only. Launch and link results are filled by later supervised steps. */
static int cheap_prerequisites_ok(void)
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
	if (!g_receipt.cpu_stat_ok || !g_receipt.containment_ok)
		return 0;
	return 1;
}

static int disabled_attach_ok(void)
{
	if (g_receipt.collection_enabled || g_receipt.fixture_launched || g_receipt.summary_count)
		return 0;
	if (!g_receipt.links_verified || !g_receipt.prototype_ok || !g_receipt.recursion_field_ok)
		return 0;
	if (!g_receipt.config_taskstats || !g_receipt.config_cgroups)
		return 0;
	if (g_receipt.clear_refs_state != LIFETIME_CLEAR_ABSENT &&
	    g_receipt.clear_refs_state != LIFETIME_CLEAR_ATTACHED)
		return 0;
	if (!g_receipt.enabled_after_validation)
		return 0;
	return 1;
}

static int setup_cgroup(int ctrl)
{
	char relative[PATH_MAX];
	char joined[PATH_MAX];
	char parent_real[PATH_MAX];
	char root_real[PATH_MAX];
	char leaf_real[PATH_MAX];
	int kill_fd;
	int populated = -1;
	uint32_t reply = 0;
	struct cpu_view cpu;

	if (g_leaf_name[0] == 0)
		return -1;
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
	if (snprintf(g_cgroup_rel, sizeof g_cgroup_rel, "%s/%s", relative, g_leaf_name) >= (int)sizeof g_cgroup_rel)
		return -1;
	if (snprintf(g_leaf_path, sizeof g_leaf_path, "%s/%s", parent_real, g_leaf_name) >= (int)sizeof g_leaf_path)
		return -1;
	if (guard_send_path(ctrl, g_leaf_path) != 0)
		return -1;
	if (guard_recv_reply(ctrl, &g_admission_deadline, &reply) != 0 || reply != GUARD_PATH_OK)
		return -1;
	if (mkdir(g_leaf_path, 0755) != 0)
		return -1;
	if (!realpath(g_leaf_path, leaf_real) || strcmp(leaf_real, g_leaf_path) != 0 ||
	    !path_is_under(leaf_real, parent_real))
		return -1;
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
	if (guard_send_fd(ctrl, g_dirfd) != 0)
		return -1;
	reply = 0;
	if (guard_recv_reply(ctrl, &g_admission_deadline, &reply) != 0 || reply != GUARD_CUSTODY_OK)
		return -1;
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

static char g_cleanup_path[PATH_MAX];

static int message_matches_invocation(const struct life_msg *msg, uint32_t code)
{
	return msg->code == code && msg->reason == LIFETIME_REASON_NONE && msg->mode == g_mode &&
	       msg->cgroup_id == g_cgroup_id;
}

static int receipt_blocks_admit(const struct lifetime_receipt *receipt)
{
	if (receipt->observation_failed)
		return 1;
	if (receipt->mode != g_mode || receipt->reason != LIFETIME_REASON_NONE)
		return 1;
	if (receipt->collection_enabled || receipt->fixture_launched || receipt->summary_count)
		return 1;
	if (receipt->coverage_pass || receipt->resource_acceptance || receipt->budget_comparison_allowed)
		return 1;
	return 0;
}

/* The guardian owns the final reap after it has accepted GUARD_WATCH.
 * This only looks at the exit. ECHILD is not exit 0.
 */
static int observe_validate_child(pid_t child, int *status)
{
	if (guard_observe_exit(child, status, &g_admission_deadline) == 0)
		return 0;
	if (guard_signal_pinned(child, SIGKILL) != 0) {
		dprintf(STDERR_FILENO, "lifetime_diag: unreaped_validate_worker=%d\n", (int)child);
		return -1;
	}
	if (guard_observe_exit(child, status, &g_admission_deadline) == 0)
		return 0;
	dprintf(STDERR_FILENO, "lifetime_diag: unreaped_validate_worker=%d\n", (int)child);
	return -1;
}

static int run_validate_worker(int ctrl)
{
	int sv[2] = {-1, -1};
	int park[2] = {-1, -1};
	pid_t child;
	uint32_t reply = 0;
	struct life_msg msg;
	struct lifetime_receipt child_receipt;
	int status = 0;

	if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, sv) != 0)
		return -1;
	if (pipe2(park, O_CLOEXEC) != 0) {
		close(sv[0]);
		close(sv[1]);
		return -1;
	}
	g_worker_park = park[0];
	child = fork();
	if (child < 0) {
		g_worker_park = -1;
		close(park[0]);
		close(park[1]);
		close(sv[0]);
		close(sv[1]);
		return -1;
	}
	if (child == 0) {
		pid_t parent = getppid();

		close(sv[0]);
		close(park[1]);
		if (prctl(PR_SET_PDEATHSIG, SIGKILL) != 0 || getppid() != parent)
			_exit(127);
		collector(sv[1]);
		_exit(1);
	}
	close(sv[1]);
	close(park[0]);
	g_worker_park = -1;
	if (guard_send_simple(ctrl, GUARD_WATCH, child) != 0 ||
	    guard_recv_reply(ctrl, &g_admission_deadline, &reply) != 0 || reply != GUARD_WATCH_OK) {
		/* The guardian did not take this child, so this parent still reaps it. */
		guard_signal_pinned(child, SIGKILL);
		wait_pid_until(child, &status, &g_admission_deadline);
		close(park[1]);
		close(sv[0]);
		return -1;
	}
	if (write(park[1], "g", 1) != 1) {
		guard_signal_pinned(child, SIGKILL);
		close(park[1]);
		close(sv[0]);
		return -1;
	}
	close(park[1]);
	memset(&msg, 0, sizeof msg);
	if (recv_msg_until(sv[0], &msg, &g_admission_deadline) != 0) {
		observe_validate_child(child, &status);
		close(sv[0]);
		return -1;
	}
	if (msg.code == LIFE_MSG_REFUSED) {
		memset(&child_receipt, 0, sizeof child_receipt);
		if (recv_exact_until(sv[0], &child_receipt, sizeof child_receipt, &g_admission_deadline) == 0)
			g_receipt = child_receipt;
		lifetime_keep_worker_reason(&g_receipt, msg.reason);
		g_receipt.observation_failed = 1;
		close(sv[0]);
		observe_validate_child(child, &status);
		return -1;
	}
	if (!message_matches_invocation(&msg, LIFE_MSG_ATTACHED)) {
		g_receipt.observation_failed = 1;
		if (g_receipt.reason == LIFETIME_REASON_NONE)
			g_receipt.reason = LIFETIME_REASON_ATTACH;
		close(sv[0]);
		observe_validate_child(child, &status);
		return -1;
	}
	{
		struct life_msg validate;

		memset(&validate, 0, sizeof validate);
		validate.code = LIFE_MSG_VALIDATE;
		validate.mode = g_mode;
		validate.cgroup_id = g_cgroup_id;
		if (send_msg(sv[0], &validate) != 0 ||
		    recv_msg_until(sv[0], &msg, &g_admission_deadline) != 0) {
			close(sv[0]);
			observe_validate_child(child, &status);
			return -1;
		}
	}
	memset(&child_receipt, 0, sizeof child_receipt);
	if (msg.code == LIFE_MSG_REFUSED || !message_matches_invocation(&msg, LIFE_MSG_VALIDATE)) {
		if (recv_exact_until(sv[0], &child_receipt, sizeof child_receipt, &g_admission_deadline) == 0)
			g_receipt = child_receipt;
		if (msg.code == LIFE_MSG_REFUSED)
			lifetime_keep_worker_reason(&g_receipt, msg.reason);
		g_receipt.observation_failed = 1;
		close(sv[0]);
		observe_validate_child(child, &status);
		return -1;
	}
	if (recv_exact_until(sv[0], &child_receipt, sizeof child_receipt, &g_admission_deadline) != 0) {
		close(sv[0]);
		observe_validate_child(child, &status);
		return -1;
	}
	close(sv[0]);
	g_receipt = child_receipt;
	if (observe_validate_child(child, &status) != 0)
		return -1;
	if (!WIFEXITED(status) || WEXITSTATUS(status) != 0 || receipt_blocks_admit(&g_receipt)) {
		g_receipt.observation_failed = 1;
		return -1;
	}
	return 0;
}

static void controller_main(int ctrl)
{
	uint32_t reply = 0;

	g_is_guardian = 0;
	g_clone_permitted = 0;
	if (lifetime_sha256_selftest() != 0) {
		fill_identity();
		g_receipt.btf_ok = 0;
		g_receipt.reason = LIFETIME_REASON_DIGEST;
		guard_send_result(ctrl, &g_receipt);
		guard_send_simple(ctrl, GUARD_DONE, 0);
		_exit(1);
	}
	fill_identity();
	if (setup_cgroup(ctrl) != 0) {
		note("cgroup setup refused");
		if (g_receipt.reason == LIFETIME_REASON_NONE)
			g_receipt.reason = LIFETIME_REASON_CGROUP;
		guard_send_result(ctrl, &g_receipt);
		guard_send_simple(ctrl, GUARD_DONE, 0);
		_exit(1);
	}
	if (!cheap_prerequisites_ok()) {
		note("admission prerequisites refused");
		guard_send_result(ctrl, &g_receipt);
		guard_send_simple(ctrl, GUARD_DONE, 0);
		_exit(1);
	}
	if (run_validate_worker(ctrl) != 0) {
		g_receipt.observation_failed = 1;
		note("disabled attach worker failed");
		if (g_dirfd >= 0) {
			close(g_dirfd);
			g_dirfd = -1;
		}
		guard_send_result(ctrl, &g_receipt);
		guard_send_simple(ctrl, GUARD_DONE, 0);
		_exit(1);
	}
	if (guard_send_simple(ctrl, GUARD_CLONE, 0) == 0 &&
	    guard_recv_reply(ctrl, &g_admission_deadline, &reply) == 0 && reply == GUARD_CLONE_OK) {
		g_clone_permitted = 1;
		if (probe_direct_launch() != 0) {
			note("direct launch refused");
			g_receipt.observation_failed = 1;
			if (g_receipt.reason == LIFETIME_REASON_NONE)
				g_receipt.reason = LIFETIME_REASON_DIRECT_LAUNCH;
		}
		g_clone_permitted = 0;
	} else {
		note("clone permit refused");
		g_receipt.observation_failed = 1;
		if (g_receipt.reason == LIFETIME_REASON_NONE)
			g_receipt.reason = LIFETIME_REASON_DIRECT_LAUNCH;
	}
	if (g_dirfd >= 0) {
		close(g_dirfd);
		g_dirfd = -1;
	}
	if (g_receipt.collection_enabled || g_receipt.fixture_launched || g_receipt.summary_count ||
	    g_receipt.coverage_pass || g_receipt.resource_acceptance || g_receipt.budget_comparison_allowed ||
	    g_receipt.reason != LIFETIME_REASON_NONE)
		g_receipt.observation_failed = 1;
	guard_send_result(ctrl, &g_receipt);
	guard_send_simple(ctrl, GUARD_DONE, 0);
	_exit(g_receipt.observation_failed || !disabled_attach_ok() || !g_receipt.direct_launch_ok ||
			      g_receipt.reason != LIFETIME_REASON_NONE
		      ? 1
		      : 0);
}

static int publish_admission(struct admission_outcome *out)
{
	struct lifetime_receipt *receipt;
	uint32_t i;
	uint8_t keep_collection;
	uint8_t keep_fixture;
	uint8_t keep_coverage;
	uint8_t keep_accept;
	uint8_t keep_budget;
	uint32_t keep_summaries;
	struct timespec final_deadline;
	pid_t unreaped_publisher = 0;

	if (!out->have_result) {
		memset(&out->receipt, 0, sizeof out->receipt);
		out->receipt.mode = LIFETIME_MODE_ADMIT;
		out->receipt.reason =
			out->timed_out ? LIFETIME_REASON_CONTAINMENT : LIFETIME_REASON_COLLECTOR_DEATH;
		out->receipt.observation_failed = 1;
	}
	receipt = &out->receipt;
	if (receipt->mode == 0)
		receipt->mode = LIFETIME_MODE_ADMIT;
	if (receipt->collection_enabled || receipt->summary_count || receipt->fixture_launched ||
	    receipt->coverage_pass || receipt->resource_acceptance || receipt->budget_comparison_allowed) {
		receipt->observation_failed = 1;
		if (receipt->reason == LIFETIME_REASON_NONE)
			receipt->reason = LIFETIME_REASON_CONTAINMENT;
	}
	keep_collection = receipt->collection_enabled;
	keep_fixture = receipt->fixture_launched;
	keep_coverage = receipt->coverage_pass;
	keep_accept = receipt->resource_acceptance;
	keep_budget = receipt->budget_comparison_allowed;
	keep_summaries = receipt->summary_count;
	for (i = 0; i < LIFETIME_CTR_COUNT; i++) {
		if (receipt->counters[i] != 0)
			receipt->observation_failed = 1;
	}
	if (out->clone_permits != 1 &&
	    (receipt->direct_launch_ok || receipt->clone3_ok ||
	     receipt->launch_path == LIFETIME_LAUNCH_CLONE3)) {
		receipt->observation_failed = 1;
		if (receipt->reason == LIFETIME_REASON_NONE)
			receipt->reason = LIFETIME_REASON_DIRECT_LAUNCH;
	}
	if (out->timed_out || out->controller_lost || out->protocol_failed || out->reap_unconfirmed ||
	    !out->cleanup_confirmed || (out->owned_watched > 0 && out->unreaped_watched > 0)) {
		receipt->observation_failed = 1;
		if (out->controller_lost)
			receipt->collector_death = 1;
		if (receipt->reason == LIFETIME_REASON_NONE)
			receipt->reason =
				out->timed_out ? LIFETIME_REASON_CONTAINMENT : LIFETIME_REASON_COLLECTOR_DEATH;
	}
	receipt->cleanup_attempted = 1;
	receipt->cleanup_pass = out->cleanup_confirmed ? 1 : 0;
	lifetime_apply(receipt);
	receipt->collection_enabled = keep_collection;
	receipt->fixture_launched = keep_fixture;
	receipt->coverage_pass = keep_coverage;
	receipt->resource_acceptance = keep_accept;
	receipt->budget_comparison_allowed = keep_budget;
	receipt->summary_count = keep_summaries;
	if (keep_collection || keep_fixture || keep_coverage || keep_accept || keep_budget || keep_summaries)
		receipt->observation_failed = 1;
	final_deadline = g_admission_deadline;
	guard_add_ms(&final_deadline, LIFETIME_CLEANUP_MS);
	if (receipt_publish_supervised(g_receipt_path, receipt, sizeof *receipt, &final_deadline, -1, -1,
				       &unreaped_publisher) != 0) {
		note("receipt publication unconfirmed");
		if (unreaped_publisher > 0)
			dprintf(STDERR_FILENO, "lifetime_diag: unreaped_publisher=%d\n", (int)unreaped_publisher);
		return 1;
	}
	return lifetime_mode_exit_ok(receipt) ? 0 : 1;
}

int main(int argc, char **argv)
{
	const char *mode_text = NULL;
	const char *path = NULL;
	int i;
	int sv[2] = {-1, -1};
	int park[2] = {-1, -1};
	pid_t child = -1;
	int pidfd = -1;
	unsigned char rnd[8];
	struct admission_guard_ops ops;
	struct admission_outcome outcome;

	if (argc >= 2 && strcmp(argv[1], "--payload") == 0)
		_exit(0);
	for (i = 1; i < argc; i++) {
		if (strcmp(argv[i], "--mode") == 0 && i + 1 < argc)
			mode_text = argv[++i];
		else if (strcmp(argv[i], "--receipt") == 0 && i + 1 < argc)
			path = argv[++i];
		else {
			dprintf(STDERR_FILENO, "usage: lifetime_diag --mode admit --receipt <path>\n");
			return 2;
		}
	}
	if (!mode_text || !path || parse_mode(mode_text) < 0) {
		dprintf(STDERR_FILENO, "usage: lifetime_diag --mode admit --receipt <path>\n");
		return 2;
	}
	if (strlen(path) + 1 > sizeof g_receipt_path) {
		note("receipt path is too long");
		return 2;
	}
	memcpy(g_receipt_path, path, strlen(path) + 1);
	g_mode = (uint32_t)parse_mode(mode_text);
	if (clock_gettime(CLOCK_MONOTONIC, &g_admission_deadline) != 0) {
		note("clock refused");
		return 1;
	}
	guard_add_ms(&g_admission_deadline, LIFETIME_ADMISSION_MS);
	{
		pid_t unreaped_inspect = 0;
		int absent = receipt_confirm_absent(g_receipt_path, &g_admission_deadline, &unreaped_inspect);

		if (absent == -2)
			note("refusing to replace an existing receipt");
		else if (absent != 0)
			note("receipt inspection unconfirmed");
		if (unreaped_inspect > 0)
			dprintf(STDERR_FILENO, "lifetime_diag: unreaped_inspector=%d\n", (int)unreaped_inspect);
		if (absent != 0)
			return 1;
	}
	if (g_mode != LIFETIME_MODE_ADMIT) {
		memset(&outcome, 0, sizeof outcome);
		outcome.have_result = 1;
		outcome.receipt.mode = g_mode;
		outcome.receipt.reason = LIFETIME_REASON_UNSUPPORTED;
		outcome.receipt.observation_failed = 1;
		outcome.protocol_failed = 1;
		note("only --mode admit is enabled");
		return publish_admission(&outcome);
	}
	if (prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0) {
		note("subreaper setup refused");
		memset(&outcome, 0, sizeof outcome);
		outcome.protocol_failed = 1;
		return publish_admission(&outcome);
	}
	if (signal(SIGPIPE, SIG_IGN) == SIG_ERR) {
		note("SIGPIPE setup refused");
		memset(&outcome, 0, sizeof outcome);
		outcome.protocol_failed = 1;
		return publish_admission(&outcome);
	}
	g_is_guardian = 1;
	if (getrandom(rnd, sizeof rnd, GRND_NONBLOCK) != (ssize_t)sizeof rnd) {
		note("leaf name refused");
		memset(&outcome, 0, sizeof outcome);
		outcome.protocol_failed = 1;
		return publish_admission(&outcome);
	}
	if (snprintf(g_leaf_name, sizeof g_leaf_name, "mnemion-bpf-life-%02x%02x%02x%02x%02x%02x%02x%02x",
		     rnd[0], rnd[1], rnd[2], rnd[3], rnd[4], rnd[5], rnd[6], rnd[7]) >= (int)sizeof g_leaf_name) {
		return 1;
	}
	if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, sv) != 0 || pipe2(park, O_CLOEXEC) != 0) {
		note("supervisor channel refused");
		memset(&outcome, 0, sizeof outcome);
		outcome.protocol_failed = 1;
		return publish_admission(&outcome);
	}
	child = fork();
	if (child < 0) {
		note("controller fork refused");
		memset(&outcome, 0, sizeof outcome);
		outcome.protocol_failed = 1;
		return publish_admission(&outcome);
	}
	if (child == 0) {
		char byte = 0;

		close(sv[0]);
		close(park[1]);
		if (read(park[0], &byte, 1) != 1)
			_exit(1);
		close(park[0]);
		controller_main(sv[1]);
		_exit(1);
	}
	close(sv[1]);
	close(park[0]);
	pidfd = (int)syscall(__NR_pidfd_open, child, 0);
	if (pidfd < 0) {
		int status = 0;

		kill(child, SIGKILL);
		if (wait_pid_until(child, &status, &g_admission_deadline) != 0)
			dprintf(STDERR_FILENO, "lifetime_diag: unreaped_controller=%d\n", (int)child);
		close(sv[0]);
		close(park[1]);
		note("controller pidfd refused");
		memset(&outcome, 0, sizeof outcome);
		outcome.protocol_failed = 1;
		return publish_admission(&outcome);
	}
	memset(&ops, 0, sizeof ops);
	ops.kill_write = cleanup_kill;
	ops.read_populated = cleanup_populated;
	ops.remove_leaf = cleanup_remove;
	ops.ctx = g_cleanup_path;
	memset(g_cleanup_path, 0, sizeof g_cleanup_path);
	if (admission_supervise(child, pidfd, sv[0], &g_admission_deadline, LIFETIME_CLEANUP_MS, g_leaf_name,
				"/sys/fs/cgroup", g_cleanup_path, sizeof g_cleanup_path, &ops, park[1],
				&outcome) != 0) {
		outcome.protocol_failed = 1;
	}
	close(pidfd);
	if (outcome.held_cleanup_pidfd >= 0)
		close(outcome.held_cleanup_pidfd);
	if (outcome.held_verify_pidfd >= 0)
		close(outcome.held_verify_pidfd);
	if (outcome.held_watched_pidfd >= 0)
		close(outcome.held_watched_pidfd);
	close(sv[0]);
	return publish_admission(&outcome);
}
