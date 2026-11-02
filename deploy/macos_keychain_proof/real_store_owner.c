/* Real-store supervisor. The public process does not open the stores.
   It records the owner, and the owner records every compiler, signer,
   provisioner, and parent it spawns. Deadlines and SIGKILL are not
   kernel-reap evidence. This lane does not call the helper XPC service. */

#include "protocol.h"
#include "real_store_names.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

extern char **environ;

enum { MAX_CHILDREN = 4, MAX_SUPER_DIRS = 4, CAPTURE_MAX = 8192 };

static long g_deadline = 0;
static long g_grace_deadline = 0;
static int g_grace_on = 0;
static volatile sig_atomic_t g_stop = 0;
static int g_wake[2] = {-1, -1};
static int g_parent_fd = -1;
static dev_t g_parent_dev = 0;
static ino_t g_parent_ino = 0;
static char g_parent[1024];
static char g_arch[16];
static char g_source[41];
static int g_case_failure = 0;
static int g_cancelled = 0;
static int g_deadline_hit = 0;
static int g_report_uncertain = 0;
static int g_cleanup_uncertain = 0;
static int g_record_fd = -1;
static int g_spawns = 0;
static int g_stores_attempted = 0;
static int g_deleted = 0;
static int g_delete_spawned = 0;
static int g_calls_bad = 0;
static long g_calls = -1;
static int g_symlinks = -1;
static int g_check_exit = -1;
static int g_lookup_exit = -1;
static char g_error[40] = "none";
static char g_search_equal[16] = "not_run";
static char g_default_equal[16] = "not_run";
static char g_basename_contract[16] = "not_run";
static char g_custody_id[9];
static char g_sha1[41];
static char g_sha256[65];

struct run_slot {
    int live;
    int fd;
    dev_t dev;
    ino_t ino;
    char name[24];
    char path[1024];
    char id[9];
    char nonce[33];
};

struct child_slot {
    int live;
    int leader_reaped;
    pid_t pid;
    pid_t pgid;
    char kind[16];
};

static struct run_slot g_run;
static struct child_slot g_children[MAX_CHILDREN];

struct sup_slot {
    int live;
    int retired;
    pid_t leader;
    pid_t pgid;
};

struct sup_dir {
    int live;
    unsigned long long dev;
    unsigned long long ino;
};

struct sup_state {
    struct sup_slot slots[REAL_RECORD_BOUND];
    struct sup_dir dirs[MAX_SUPER_DIRS];
    char line[256];
    size_t line_len;
    int phase;
    int stream_uncertain;
};

struct sup_result {
    int timed_out;
    int decision_reaped;
    int unresolved;
    int owner_exit;
    int owner_signaled;
    int cancelled;
    int stream_uncertain;
    int hygiene_collected;
    int hygiene_group_empty;
};

struct child_result {
    int status;
    char reap[16];
    char output[CAPTURE_MAX];
    size_t length;
};

static long mono_ms(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
        return -1;
    }
    return (long)ts.tv_sec * 1000L + (long)(ts.tv_nsec / 1000000L);
}

static long remaining_run(void) {
    long now = mono_ms();
    long left;
    if (now < 0) {
        return 0;
    }
    left = g_deadline - now;
    return left > 0 ? left : 0;
}

static long child_budget(void) {
    long left = remaining_run();
    if (left > REAL_CHILD_MS) {
        return REAL_CHILD_MS;
    }
    return left;
}

static void on_stop(int sig) {
    char byte = 1;
    (void)sig;
    g_stop = 1;
    if (g_wake[1] >= 0) {
        ssize_t wrote = write(g_wake[1], &byte, 1);
        (void)wrote;
    }
}

static void arm_signals(void) {
    struct sigaction action;
    memset(&action, 0, sizeof action);
    action.sa_handler = on_stop;
    sigaction(SIGINT, &action, NULL);
    sigaction(SIGTERM, &action, NULL);
    sigaction(SIGHUP, &action, NULL);
    signal(SIGPIPE, SIG_IGN);
}

static void set_nonblock_cloexec(int fd) {
    int flags;
    if (fd < 0) {
        return;
    }
    flags = fcntl(fd, F_GETFL);
    if (flags >= 0) {
        fcntl(fd, F_SETFL, flags | O_NONBLOCK);
    }
    fcntl(fd, F_SETFD, FD_CLOEXEC);
}

static void drain_wake(void) {
    char buffer[64];
    ssize_t count;
    if (g_wake[0] < 0) {
        return;
    }
    do {
        count = read(g_wake[0], buffer, sizeof buffer);
    } while (count > 0 || (count < 0 && errno == EINTR));
}

static void report_line(const char *line) {
    size_t length;
    size_t filled = 0;
    if (g_record_fd < 0 || g_report_uncertain || line == NULL) {
        return;
    }
    length = strlen(line);
    while (filled < length) {
        ssize_t count = write(g_record_fd, line + filled, length - filled);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            struct pollfd ready;
            ready.fd = g_record_fd;
            ready.events = POLLOUT;
            if (poll(&ready, 1, 50) <= 0) {
                g_report_uncertain = 1;
                return;
            }
            continue;
        }
        if (count <= 0) {
            g_report_uncertain = 1;
            return;
        }
        filled += (size_t)count;
    }
}

static int token_ok(const char *text, size_t length, size_t max_length) {
    size_t index;
    if (text == NULL || length == 0 || length > max_length) {
        return 0;
    }
    for (index = 0; index < length; index++) {
        char character = text[index];
        int digit = character >= '0' && character <= '9';
        int lower = character >= 'a' && character <= 'z';
        if (!digit && !lower && character != '-') {
            return 0;
        }
    }
    return 1;
}

static void report_child(pid_t pgid, pid_t leader, const char *kind) {
    char line[80];
    if (!token_ok(kind, strlen(kind), 15)) {
        g_report_uncertain = 1;
        return;
    }
    snprintf(line, sizeof line, "C %llu %llu %s\n", (unsigned long long)pgid, (unsigned long long)leader, kind);
    report_line(line);
}

static void report_settled(pid_t pgid) {
    char line[64];
    snprintf(line, sizeof line, "X %llu\n", (unsigned long long)pgid);
    report_line(line);
}

static void report_run(dev_t dev, ino_t ino, const char *name) {
    char line[128];
    if (!token_ok(name, strlen(name), 23)) {
        g_report_uncertain = 1;
        return;
    }
    snprintf(line, sizeof line, "R %llu %llu %s\n", (unsigned long long)dev, (unsigned long long)ino, name);
    report_line(line);
}

static void report_run_cleared(dev_t dev, ino_t ino) {
    char line[96];
    snprintf(line, sizeof line, "Y %llu %llu\n", (unsigned long long)dev, (unsigned long long)ino);
    report_line(line);
}

static void report_phase(void) {
    report_line("P\n");
}

static struct child_slot *find_child(pid_t pid) {
    int index;
    for (index = 0; index < MAX_CHILDREN; index++) {
        if (g_children[index].live && g_children[index].pid == pid) {
            return &g_children[index];
        }
    }
    return NULL;
}

static int group_occupied(pid_t pgid) {
    if (pgid <= 1 || pgid == getpid() || pgid == getpgrp()) {
        return -1;
    }
    if (kill(-pgid, 0) == 0) {
        return 1;
    }
    if (errno == ESRCH) {
        return 0;
    }
    return -1;
}

static int note_child(pid_t pid, const char *kind) {
    int index;
    if (pid <= 1 || pid == getpid() || pid == getpgrp() || g_spawns >= REAL_SPAWN_CAP) {
        return -1;
    }
    if (!token_ok(kind, strlen(kind), 15)) {
        return -1;
    }
    for (index = 0; index < MAX_CHILDREN; index++) {
        if (!g_children[index].live) {
            g_children[index].live = 1;
            g_children[index].leader_reaped = 0;
            g_children[index].pid = pid;
            g_children[index].pgid = pid;
            snprintf(g_children[index].kind, sizeof g_children[index].kind, "%s", kind);
            report_child(pid, pid, kind);
            g_spawns++;
            return 0;
        }
    }
    return -1;
}

static void mark_leader_reaped(pid_t pid) {
    struct child_slot *slot = find_child(pid);
    int occupied;
    if (slot == NULL) {
        return;
    }
    slot->leader_reaped = 1;
    occupied = group_occupied(slot->pgid);
    if (occupied == 0) {
        pid_t pgid = slot->pgid;
        slot->live = 0;
        report_settled(pgid);
    }
}

static int children_live(void) {
    int index;
    for (index = 0; index < MAX_CHILDREN; index++) {
        if (g_children[index].live) {
            return 1;
        }
    }
    return 0;
}

static void signal_retained(struct child_slot *slot, int sig) {
    if (slot == NULL || !slot->live) {
        return;
    }
    if (slot->pgid <= 1 || slot->pgid == getpid() || slot->pgid == getpgrp()) {
        return;
    }
    if (kill(-slot->pgid, sig) != 0) {
        return;
    }
}

static int spawn_recorded(char *const argv[], int stdin_fd, int stdout_fd, int stderr_fd, pid_t *pid) {
    posix_spawn_file_actions_t actions;
    posix_spawnattr_t attr;
    pid_t child = -1;
    int rc;
    int setup = 0;
    if (g_stop || (!g_grace_on && remaining_run() == 0)) {
        g_cancelled = 1;
        return -1;
    }
    if (posix_spawnattr_init(&attr) != 0) {
        return -1;
    }
    if (posix_spawnattr_setflags(&attr, POSIX_SPAWN_SETPGROUP) != 0 || posix_spawnattr_setpgroup(&attr, 0) != 0 ||
        posix_spawn_file_actions_init(&actions) != 0) {
        posix_spawnattr_destroy(&attr);
        return -1;
    }
    if (stdin_fd >= 0 && posix_spawn_file_actions_adddup2(&actions, stdin_fd, STDIN_FILENO) != 0) {
        setup = -1;
    }
    if (stdout_fd >= 0 && posix_spawn_file_actions_adddup2(&actions, stdout_fd, STDOUT_FILENO) != 0) {
        setup = -1;
    }
    if (stderr_fd >= 0 && posix_spawn_file_actions_adddup2(&actions, stderr_fd, STDERR_FILENO) != 0) {
        setup = -1;
    } else if (stderr_fd < 0 && stdout_fd >= 0 && posix_spawn_file_actions_adddup2(&actions, stdout_fd, STDERR_FILENO) != 0) {
        setup = -1;
    }
    rc = setup == 0 ? posix_spawnp(&child, argv[0], &actions, &attr, argv, environ) : -1;
    posix_spawn_file_actions_destroy(&actions);
    posix_spawnattr_destroy(&attr);
    if (rc != 0) {
        errno = rc;
        return -1;
    }
    *pid = child;
    return 0;
}

static int read_budget(int fd, char *buffer, size_t cap, size_t *out_len, long budget_ms) {
    size_t filled = 0;
    long start = mono_ms();
    if (start < 0 || cap < 2) {
        return -1;
    }
    while (filled + 1 < cap) {
        struct pollfd polls[2];
        long elapsed = mono_ms() - start;
        int wait_ms;
        int ready;
        ssize_t count;
        if (g_stop) {
            g_cancelled = 1;
            return -1;
        }
        if (elapsed >= budget_ms) {
            return 1;
        }
        wait_ms = (int)(budget_ms - elapsed);
        if (wait_ms > 200) {
            wait_ms = 200;
        }
        polls[0].fd = fd;
        polls[0].events = POLLIN;
        polls[1].fd = g_wake[0];
        polls[1].events = POLLIN;
        ready = poll(polls, g_wake[0] >= 0 ? 2 : 1, wait_ms);
        if (ready < 0 && errno == EINTR) {
            continue;
        }
        if (ready < 0) {
            return -1;
        }
        if (ready == 0) {
            continue;
        }
        if (g_wake[0] >= 0 && (polls[1].revents & POLLIN)) {
            drain_wake();
            g_cancelled = 1;
            return -1;
        }
        count = read(fd, buffer + filled, cap - 1 - filled);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count < 0) {
            return -1;
        }
        if (count == 0) {
            buffer[filled] = '\0';
            *out_len = filled;
            return 0;
        }
        filled += (size_t)count;
    }
    return -1;
}

static int wait_budget(pid_t pid, int *status, char *reap, size_t reap_cap, long budget_ms) {
    long start = mono_ms();
    if (start < 0) {
        return -1;
    }
    snprintf(reap, reap_cap, "not_reaped");
    while (1) {
        int got_status = 0;
        pid_t got = waitpid(pid, &got_status, WNOHANG);
        long elapsed = mono_ms() - start;
        if (got == pid) {
            *status = got_status;
            if (WIFEXITED(got_status)) {
                snprintf(reap, reap_cap, "exited");
            } else if (WIFSIGNALED(got_status)) {
                snprintf(reap, reap_cap, "signaled");
            } else {
                snprintf(reap, reap_cap, "exited");
            }
            mark_leader_reaped(pid);
            return 0;
        }
        if (got < 0 && errno == EINTR) {
            continue;
        }
        if (got < 0 && errno == ECHILD) {
            struct child_slot *slot = find_child(pid);
            if (slot != NULL && slot->leader_reaped) {
                return 0;
            }
            return -1;
        }
        if (got < 0) {
            return -1;
        }
        if (g_stop) {
            g_cancelled = 1;
            return -1;
        }
        if (elapsed >= budget_ms) {
            snprintf(reap, reap_cap, "timeout");
            return 1;
        }
        {
            struct pollfd polls[1];
            int slice = (int)(budget_ms - elapsed);
            if (slice > 50) {
                slice = 50;
            }
            if (g_wake[0] < 0) {
                nanosleep(&(struct timespec){0, 20000000L}, NULL);
            } else {
                int ready;
                polls[0].fd = g_wake[0];
                polls[0].events = POLLIN;
                ready = poll(polls, 1, slice);
                if (ready < 0 && errno != EINTR) {
                    return -1;
                }
                if (ready > 0 && (polls[0].revents & POLLIN)) {
                    drain_wake();
                }
            }
        }
    }
}

static void signal_one(pid_t pid, int sig) {
    signal_retained(find_child(pid), sig);
}

static int arg_ok(const char *text) {
    size_t length;
    if (text == NULL) {
        return 0;
    }
    length = strlen(text);
    if (length == 0 || length > 1000 || strchr(text, '\n') != NULL || strchr(text, '\r') != NULL || strchr(text, '"') != NULL) {
        return 0;
    }
    return 1;
}

static int argv_ok(char *const argv[]) {
    int index;
    if (argv == NULL || argv[0] == NULL) {
        return 0;
    }
    for (index = 0; argv[index] != NULL; index++) {
        if (index > 48 || !arg_ok(argv[index])) {
            return 0;
        }
    }
    return 1;
}

static void fail(const char *category) {
    if (strcmp(g_error, "none") == 0) {
        snprintf(g_error, sizeof g_error, "%s", category);
    }
    g_case_failure = 1;
}

static int exit_accepted(int status, int expect_exit, const char *mismatch) {
    if (!WIFEXITED(status) || (expect_exit >= 0 && WEXITSTATUS(status) != expect_exit)) {
        fail(mismatch != NULL && mismatch[0] != '\0' ? mismatch : "unsupported");
        return -1;
    }
    return 0;
}

static int run_child(char *const argv[], const char *kind, const char *log_name, struct child_result *captured, long budget_ms,
                     int expect_exit, const char *mismatch) {
    int pipes[2] = {-1, -1};
    int log_fd = -1;
    int null_fd = -1;
    pid_t pid = -1;
    int stdout_fd = -1;
    int stderr_fd = -1;
    int read_rc = 0;
    int wait_rc;
    int timed_out = 0;
    if (captured != NULL) {
        captured->output[0] = '\0';
        captured->length = 0;
        captured->status = 0;
        snprintf(captured->reap, sizeof captured->reap, "not_reaped");
    }
    if (!argv_ok(argv) || !token_ok(kind, strlen(kind), 15) || log_name == NULL || !token_ok(log_name, strlen(log_name), 23)) {
        fail("unsupported");
        return -1;
    }
    if (children_live()) {
        fail("cleanup_incomplete");
        return -1;
    }
    null_fd = open("/dev/null", O_RDONLY | O_CLOEXEC);
    log_fd = openat(g_run.fd, log_name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (null_fd < 0 || log_fd < 0 || fchmod(log_fd, 0600) != 0) {
        fail("unsupported");
        goto leave;
    }
    if (captured != NULL) {
        if (pipe(pipes) != 0) {
            fail("unsupported");
            goto leave;
        }
        fcntl(pipes[0], F_SETFD, FD_CLOEXEC);
        fcntl(pipes[1], F_SETFD, FD_CLOEXEC);
        stdout_fd = pipes[1];
        stderr_fd = log_fd;
    } else {
        stdout_fd = log_fd;
        stderr_fd = -1;
    }
    if (spawn_recorded(argv, null_fd, stdout_fd, stderr_fd, &pid) != 0) {
        fail(errno == ENOENT ? "tool_unavailable" : "unsupported");
        goto leave;
    }
    if (note_child(pid, kind) != 0) {
        signal_one(pid, SIGKILL);
        fail("unsupported");
        goto leave;
    }
    if (captured != NULL) {
        close(pipes[1]);
        pipes[1] = -1;
        read_rc = read_budget(pipes[0], captured->output, sizeof captured->output, &captured->length, budget_ms);
        close(pipes[0]);
        pipes[0] = -1;
        if (read_rc != 0) {
            signal_one(pid, SIGTERM);
            wait_budget(pid, &captured->status, captured->reap, sizeof captured->reap, budget_ms);
            g_deadline_hit = 1;
            fail(read_rc == 1 ? "deadline" : "measure_failed");
            goto leave;
        }
        wait_rc = wait_budget(pid, &captured->status, captured->reap, sizeof captured->reap, budget_ms);
        if (wait_rc != 0) {
            timed_out = 1;
        } else if (exit_accepted(captured->status, expect_exit, mismatch) != 0) {
            goto leave;
        }
    } else {
        int status = 0;
        char reap[16];
        wait_rc = wait_budget(pid, &status, reap, sizeof reap, budget_ms);
        if (wait_rc != 0) {
            timed_out = 1;
        } else if (exit_accepted(status, expect_exit, mismatch) != 0) {
            goto leave;
        }
    }
    if (timed_out) {
        g_deadline_hit = 1;
        fail("deadline");
        goto leave;
    }
    close(log_fd);
    close(null_fd);
    return 0;
leave:
    if (pipes[0] >= 0) {
        close(pipes[0]);
    }
    if (pipes[1] >= 0) {
        close(pipes[1]);
    }
    if (log_fd >= 0) {
        close(log_fd);
    }
    if (null_fd >= 0) {
        close(null_fd);
    }
    return -1;
}

static int path_prefix(const char *prefix, const char *path) {
    size_t length = strlen(prefix);
    if (length == 0 || strncmp(prefix, path, length) != 0) {
        return 0;
    }
    return path[length] == '\0' || path[length] == '/';
}

static int walk_parent(const char *path) {
    int fd;
    size_t length = strlen(path);
    size_t cursor = 1;
    struct stat st;
    char cwd[1024];
    if (path[0] != '/' || length < 2 || length > 800 || path[length - 1] == '/') {
        return -1;
    }
    if (strstr(path, "//") != NULL || strchr(path, '\\') != NULL || strchr(path, '"') != NULL || strchr(path, ' ') != NULL) {
        return -1;
    }
    if (path_prefix("/tmp", path) || path_prefix("/var", path) || path_prefix("/private/tmp", path) ||
        path_prefix("/private/var", path) || strstr(path, "/Library/Keychains") != NULL || strstr(path, "login.keychain") != NULL) {
        return -1;
    }
    if (getcwd(cwd, sizeof cwd) == NULL || path_prefix(cwd, path) || path_prefix(path, cwd)) {
        return -1;
    }
    fd = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (fd < 0) {
        return -1;
    }
    while (cursor < length) {
        char name[256];
        size_t name_len = 0;
        int next;
        while (cursor < length && path[cursor] != '/') {
            if (name_len + 1 >= sizeof name) {
                close(fd);
                return -1;
            }
            name[name_len++] = path[cursor++];
        }
        name[name_len] = '\0';
        if (cursor < length && path[cursor] == '/') {
            cursor++;
        }
        if (name_len == 0 || strcmp(name, ".") == 0 || strcmp(name, "..") == 0) {
            close(fd);
            return -1;
        }
        if (fstatat(fd, name, &st, AT_SYMLINK_NOFOLLOW) != 0 || S_ISLNK(st.st_mode) || !S_ISDIR(st.st_mode)) {
            close(fd);
            return -1;
        }
        next = openat(fd, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        close(fd);
        if (next < 0) {
            return -1;
        }
        fd = next;
    }
    if (fstat(fd, &st) != 0 || !S_ISDIR(st.st_mode)) {
        close(fd);
        return -1;
    }
    g_parent_fd = fd;
    g_parent_dev = st.st_dev;
    g_parent_ino = st.st_ino;
    snprintf(g_parent, sizeof g_parent, "%s", path);
    return 0;
}

static int write_all_fd(int fd, const char *bytes, size_t length) {
    size_t filled = 0;
    while (filled < length) {
        ssize_t count = write(fd, bytes + filled, length - filled);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count <= 0) {
            return -1;
        }
        filled += (size_t)count;
    }
    return 0;
}

static int random_bytes(unsigned char *buffer, size_t count) {
    int fd = open("/dev/urandom", O_RDONLY | O_CLOEXEC);
    size_t filled = 0;
    if (fd < 0) {
        return -1;
    }
    while (filled < count) {
        ssize_t got = read(fd, buffer + filled, count - filled);
        if (got < 0 && errno == EINTR) {
            continue;
        }
        if (got <= 0) {
            close(fd);
            return -1;
        }
        filled += (size_t)got;
    }
    close(fd);
    return 0;
}

static void hex_encode(const unsigned char *in, size_t count, char *out) {
    static const char digits[] = "0123456789abcdef";
    size_t index;
    for (index = 0; index < count; index++) {
        out[index * 2] = digits[in[index] >> 4];
        out[index * 2 + 1] = digits[in[index] & 15];
    }
    out[count * 2] = '\0';
}

static int varied_hex(const char *text, size_t expect, int want_lower, int want_upper) {
    size_t index;
    int varied = 0;
    if (text == NULL || strlen(text) != expect) {
        return 0;
    }
    if (strcmp(text, "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA") == 0 ||
        strcmp(text, "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB") == 0) {
        return 0;
    }
    for (index = 0; index < expect; index++) {
        char character = text[index];
        int digit = (character >= '0' && character <= '9') || (character >= 'a' && character <= 'f') ||
                    (character >= 'A' && character <= 'F');
        if (!digit) {
            return 0;
        }
        if (want_lower && character >= 'A' && character <= 'F') {
            return 0;
        }
        if (want_upper && character >= 'a' && character <= 'f') {
            return 0;
        }
        if (character != text[0]) {
            varied = 1;
        }
    }
    return varied;
}

static int create_file(int dirfd, const char *name, const char *body, mode_t mode, struct stat *out) {
    int fd = openat(dirfd, name, O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, mode);
    struct stat st;
    if (fd < 0 || fchmod(fd, mode) != 0) {
        if (fd >= 0) {
            close(fd);
        }
        return -1;
    }
    if (body != NULL && write_all_fd(fd, body, strlen(body)) != 0) {
        close(fd);
        return -1;
    }
    if (fsync(fd) != 0 || fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || (st.st_mode & 07777) != mode) {
        close(fd);
        return -1;
    }
    if (out != NULL) {
        *out = st;
    }
    close(fd);
    return 0;
}

static int create_dir(int dirfd, const char *name) {
    int fd;
    struct stat st;
    if (mkdirat(dirfd, name, 0700) != 0) {
        return -1;
    }
    fd = openat(dirfd, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0 || fchmod(fd, 0700) != 0 || fstat(fd, &st) != 0 || !S_ISDIR(st.st_mode) || (st.st_mode & 07777) != 0700) {
        if (fd >= 0) {
            close(fd);
        }
        return -1;
    }
    if (fsync(fd) != 0) {
        close(fd);
        return -1;
    }
    close(fd);
    return 0;
}

static int make_run(void) {
    unsigned char raw[8];
    unsigned char nonce_raw[16];
    unsigned char id_raw[4];
    unsigned char pass_raw[16];
    char pass[33];
    char record[512];
    char service[80];
    char account[80];
    struct stat st;
    int written;
    int attempt;
    if (random_bytes(raw, sizeof raw) != 0 || random_bytes(nonce_raw, sizeof nonce_raw) != 0 ||
        random_bytes(id_raw, sizeof id_raw) != 0) {
        return -1;
    }
    g_run.name[0] = 'r';
    hex_encode(raw, sizeof raw, g_run.name + 1);
    hex_encode(nonce_raw, sizeof nonce_raw, g_run.nonce);
    hex_encode(id_raw, sizeof id_raw, g_run.id);
    snprintf(g_custody_id, sizeof g_custody_id, "%s", g_run.id);
    if (mkdirat(g_parent_fd, g_run.name, 0700) != 0) {
        return -1;
    }
    g_run.fd = openat(g_parent_fd, g_run.name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (g_run.fd < 0 || fstat(g_run.fd, &st) != 0) {
        return -1;
    }
    g_run.dev = st.st_dev;
    g_run.ino = st.st_ino;
    g_run.live = 1;
    report_run(g_run.dev, g_run.ino, g_run.name);
    if (fchmod(g_run.fd, 0700) != 0) {
        return -1;
    }
    written = snprintf(g_run.path, sizeof g_run.path, "%s/%s", g_parent, g_run.name);
    if (written < 0 || (size_t)written >= sizeof g_run.path || strlen(g_run.path) > 800) {
        return -1;
    }
    snprintf(service, sizeof service, "%s%s", REAL_STORE_SERVICE_PREFIX, g_run.nonce);
    snprintf(account, sizeof account, "%s%s", REAL_STORE_ACCOUNT_PREFIX, g_run.nonce);
    written = snprintf(record, sizeof record, "nonce=%s\nservice=%s\naccount=%s\n", g_run.nonce, service, account);
    if (written < 0 || (size_t)written >= sizeof record) {
        return -1;
    }
    if (create_file(g_run.fd, REAL_STORE_RECORD_BASENAME, record, 0600, NULL) != 0 ||
        create_file(g_run.fd, REAL_STORE_LOCK_BASENAME, "", 0600, NULL) != 0 ||
        create_dir(g_run.fd, REAL_STORE_CIPHERTEXT_BASENAME) != 0 || create_dir(g_run.fd, "include") != 0) {
        return -1;
    }
    for (attempt = 0; attempt < 2; attempt++) {
        const char *name = attempt == 0 ? "signing.pass" : "data.pass";
        int varied = 0;
        int tries;
        for (tries = 0; tries < 3 && !varied; tries++) {
            if (random_bytes(pass_raw, sizeof pass_raw) != 0) {
                return -1;
            }
            hex_encode(pass_raw, sizeof pass_raw, pass);
            varied = varied_hex(pass, 32, 1, 0);
        }
        if (!varied || create_file(g_run.fd, name, pass, 0600, NULL) != 0) {
            memset(pass, 0, sizeof pass);
            return -1;
        }
        memset(pass, 0, sizeof pass);
        memset(pass_raw, 0, sizeof pass_raw);
    }
    return fsync(g_run.fd) == 0 ? 0 : -1;
}

static int under_run(const char *suffix, char *out, size_t cap) {
    int written;
    if (suffix == NULL || suffix[0] == '/' || strstr(suffix, "..") != NULL) {
        return -1;
    }
    written = snprintf(out, cap, "%s/%s", g_run.path, suffix);
    if (written < 0 || (size_t)written >= cap || !arg_ok(out)) {
        return -1;
    }
    return 0;
}

static int capture_field(const char *text, const char *key, char *out, size_t cap) {
    const char *cursor = text;
    size_t key_len = strlen(key);
    if (text == NULL) {
        return -1;
    }
    while (*cursor != '\0') {
        const char *end = strchr(cursor, '\n');
        size_t length = end == NULL ? strlen(cursor) : (size_t)(end - cursor);
        if (length > key_len && strncmp(cursor, key, key_len) == 0 && cursor[key_len] == '=') {
            size_t value_len = length - key_len - 1;
            if (value_len + 1 > cap) {
                return -1;
            }
            memcpy(out, cursor + key_len + 1, value_len);
            out[value_len] = '\0';
            return 0;
        }
        if (end == NULL) {
            break;
        }
        cursor = end + 1;
    }
    return -1;
}

static int allowed_line(const char *line, const char *const *keys) {
    int index;
    for (index = 0; keys[index] != NULL; index++) {
        size_t key_len = strlen(keys[index]);
        if (strncmp(line, keys[index], key_len) == 0 && line[key_len] == '=') {
            return 1;
        }
    }
    return 0;
}

static int capture_allowlisted(const char *text, const char *const *keys) {
    const char *cursor = text;
    if (text == NULL || text[0] == '\0') {
        return -1;
    }
    while (*cursor != '\0') {
        const char *end = strchr(cursor, '\n');
        size_t length = end == NULL ? strlen(cursor) : (size_t)(end - cursor);
        char line[CAPTURE_MAX];
        if (length == 0 || length + 1 > sizeof line) {
            return -1;
        }
        memcpy(line, cursor, length);
        line[length] = '\0';
        if (!allowed_line(line, keys)) {
            return -1;
        }
        if (end == NULL) {
            break;
        }
        cursor = end + 1;
    }
    return 0;
}

static int note_calls(const char *text) {
    char value[32];
    long count = 0;
    size_t index;
    if (capture_field(text, "instrumented_security_calls", value, sizeof value) != 0 || value[0] == '\0') {
        g_calls_bad = 1;
        return -1;
    }
    for (index = 0; value[index] != '\0'; index++) {
        if (value[index] < '0' || value[index] > '9' || index > 8) {
            g_calls_bad = 1;
            return -1;
        }
        count = count * 10 + (value[index] - '0');
    }
    if (g_calls < 0) {
        g_calls = 0;
    }
    g_calls += count;
    return 0;
}

static int category_from_result(const char *result) {
    static const char *allowed[] = {"ok",
                                    "path_rejected",
                                    "store_basename_contract",
                                    "search_list_changed",
                                    "default_store_changed",
                                    "search_list_unreadable",
                                    "interaction_bracket",
                                    "store_create_refused",
                                    "identity_refused",
                                    "import_refused",
                                    "signing_refused",
                                    "lock_refused",
                                    "cleanup_incomplete",
                                    "unsupported",
                                    "companion_unexpected",
                                    NULL};
    int index;
    for (index = 0; allowed[index] != NULL; index++) {
        if (strcmp(result, allowed[index]) == 0) {
            return 0;
        }
    }
    return -1;
}

static int read_git(void) {
    char *argv[4];
    struct child_result captured;
    size_t index;
    argv[0] = "git";
    argv[1] = "rev-parse";
    argv[2] = "HEAD";
    argv[3] = NULL;
    if (run_child(argv, "git", "log-git", &captured, child_budget(), 0, NULL) != 0) {
        return -1;
    }
    if (captured.length < 41 || captured.output[40] != '\n') {
        fail("unsupported");
        return -1;
    }
    for (index = 0; index < 40; index++) {
        char character = captured.output[index];
        if (!((character >= '0' && character <= '9') || (character >= 'a' && character <= 'f'))) {
            fail("unsupported");
            return -1;
        }
        g_source[index] = character;
    }
    g_source[40] = '\0';
    return 0;
}

static void common_flags(char **argv, int *index, const char *output, int with_run_include) {
    char include_path[1100];
    argv[(*index)++] = "clang";
    argv[(*index)++] = "-arch";
    argv[(*index)++] = g_arch;
    argv[(*index)++] = "-mmacosx-version-min=13.0";
    argv[(*index)++] = "-std=gnu11";
    argv[(*index)++] = "-fno-objc-arc";
    argv[(*index)++] = "-fblocks";
    argv[(*index)++] = "-DOS_OBJECT_USE_OBJC=0";
    argv[(*index)++] = "-Werror";
    argv[(*index)++] = "-Wall";
    argv[(*index)++] = "-Wextra";
    argv[(*index)++] = "-Werror=implicit-function-declaration";
    if (with_run_include) {
        if (under_run("include", include_path, sizeof include_path) != 0) {
            return;
        }
        argv[(*index)++] = "-I";
        argv[(*index)++] = include_path;
    }
    argv[(*index)++] = "-I";
    argv[(*index)++] = "deploy/macos_keychain_proof";
    argv[(*index)++] = "-o";
    argv[(*index)++] = (char *)output;
}

static int compile_provision(void) {
    char output[1100];
    char *argv[24];
    int index = 0;
    if (under_run("provision", output, sizeof output) != 0) {
        fail("path_rejected");
        return -1;
    }
    common_flags(argv, &index, output, 0);
    argv[index++] = "deploy/macos_keychain_proof/real_store_provision.m";
    argv[index++] = "deploy/macos_keychain_proof/fixture_store_syntax.c";
    argv[index++] = "-framework";
    argv[index++] = "Security";
    argv[index++] = "-framework";
    argv[index++] = "CoreFoundation";
    argv[index] = NULL;
    return run_child(argv, "clang", "log-clang-provision", NULL, child_budget(), 0, NULL);
}

static int compile_measure(void) {
    char output[1100];
    char *argv[28];
    int index = 0;
    if (under_run("measure", output, sizeof output) != 0) {
        fail("path_rejected");
        return -1;
    }
    common_flags(argv, &index, output, 0);
    argv[index++] = "deploy/macos_keychain_proof/real_store_measure.m";
    argv[index++] = "deploy/macos_keychain_proof/signing.m";
    argv[index++] = "deploy/macos_keychain_proof/bundle_manifest.c";
    argv[index++] = "-framework";
    argv[index++] = "Security";
    argv[index++] = "-framework";
    argv[index++] = "CoreFoundation";
    argv[index] = NULL;
    return run_child(argv, "clang", "log-clang-measure", NULL, child_budget(), 0, NULL);
}

static int compile_helper(void) {
    char output[1100];
    char include_path[1100];
    char *argv[40];
    int index = 0;
    if (under_run("MnemionCredentialHelper.xpc/Contents/MacOS/MnemionCredentialHelper", output, sizeof output) != 0 ||
        under_run("include", include_path, sizeof include_path) != 0) {
        fail("path_rejected");
        return -1;
    }
    argv[index++] = "clang";
    argv[index++] = "-arch";
    argv[index++] = g_arch;
    argv[index++] = "-mmacosx-version-min=13.0";
    argv[index++] = "-std=gnu11";
    argv[index++] = "-fno-objc-arc";
    argv[index++] = "-fblocks";
    argv[index++] = "-DOS_OBJECT_USE_OBJC=0";
    argv[index++] = "-Werror";
    argv[index++] = "-Wall";
    argv[index++] = "-Wextra";
    argv[index++] = "-Werror=implicit-function-declaration";
    argv[index++] = "-I";
    argv[index++] = include_path;
    argv[index++] = "-I";
    argv[index++] = "deploy/macos_keychain_proof";
    argv[index++] = "-o";
    argv[index++] = output;
    argv[index++] = "deploy/macos_keychain_proof/helper_main.m";
    argv[index++] = "deploy/macos_keychain_proof/auth.m";
    argv[index++] = "deploy/macos_keychain_proof/key_item.m";
    argv[index++] = "deploy/macos_keychain_proof/fixture_store.m";
    argv[index++] = "deploy/macos_keychain_proof/fixture_store_syntax.c";
    argv[index++] = "deploy/macos_keychain_proof/v10_crypt.c";
    argv[index++] = "-framework";
    argv[index++] = "Security";
    argv[index++] = "-framework";
    argv[index++] = "CoreFoundation";
    argv[index] = NULL;
    return run_child(argv, "clang", "log-clang-helper", NULL, child_budget(), 0, NULL);
}

static int compile_parent(const char *output_suffix, const char *log_name) {
    char output[1100];
    char include_path[1100];
    char *argv[40];
    int index = 0;
    if (under_run(output_suffix, output, sizeof output) != 0 || under_run("include", include_path, sizeof include_path) != 0) {
        fail("path_rejected");
        return -1;
    }
    argv[index++] = "clang";
    argv[index++] = "-arch";
    argv[index++] = g_arch;
    argv[index++] = "-mmacosx-version-min=13.0";
    argv[index++] = "-std=gnu11";
    argv[index++] = "-fno-objc-arc";
    argv[index++] = "-fblocks";
    argv[index++] = "-DOS_OBJECT_USE_OBJC=0";
    argv[index++] = "-Werror";
    argv[index++] = "-Wall";
    argv[index++] = "-Wextra";
    argv[index++] = "-Werror=implicit-function-declaration";
    argv[index++] = "-I";
    argv[index++] = include_path;
    argv[index++] = "-I";
    argv[index++] = "deploy/macos_keychain_proof";
    argv[index++] = "-o";
    argv[index++] = output;
    argv[index++] = "deploy/macos_keychain_proof/parent_main.m";
    argv[index++] = "deploy/macos_keychain_proof/parent_direct_lookup.m";
    argv[index++] = "deploy/macos_keychain_proof/auth.m";
    argv[index++] = "deploy/macos_keychain_proof/exact_helper.m";
    argv[index++] = "deploy/macos_keychain_proof/bundle_manifest.c";
    argv[index++] = "deploy/macos_keychain_proof/signing.m";
    argv[index++] = "deploy/macos_keychain_proof/fixture_store.m";
    argv[index++] = "deploy/macos_keychain_proof/fixture_store_syntax.c";
    argv[index++] = "-framework";
    argv[index++] = "Security";
    argv[index++] = "-framework";
    argv[index++] = "CoreFoundation";
    argv[index] = NULL;
    return run_child(argv, "clang", log_name, NULL, child_budget(), 0, NULL);
}

static long grace_slice(void);

static int copy_choice(const char *text, const char *key, char *dest, size_t cap, const char *first, const char *second,
                       const char *third) {
    char value[16];
    if (capture_field(text, key, value, sizeof value) != 0) {
        return -1;
    }
    if (strcmp(value, first) != 0 && strcmp(value, second) != 0 && (third == NULL || strcmp(value, third) != 0)) {
        return -1;
    }
    if (strlen(value) + 1 > cap) {
        return -1;
    }
    memcpy(dest, value, strlen(value) + 1);
    return 0;
}

static int provision_command(const char *command, const char *kind, const char *log_name, struct child_result *captured) {
    char binary[1100];
    char *argv[4];
    static const char *create_keys[] = {"result", "instrumented_security_calls", "search_list_equal", "default_equal",
                                        "basename_contract", NULL};
    static const char *import_keys[] = {"result", "instrumented_security_calls", "leaf_sha1", "leaf_sha256", "acl_scope", NULL};
    static const char *plain_keys[] = {"result", "instrumented_security_calls", NULL};
    const char *const *keys = plain_keys;
    char result[64];
    long budget = child_budget();
    if (under_run("provision", binary, sizeof binary) != 0) {
        fail("path_rejected");
        return -1;
    }
    argv[0] = binary;
    argv[1] = (char *)command;
    argv[2] = g_run.path;
    argv[3] = NULL;
    if (strcmp(command, "create-stores") == 0) {
        keys = create_keys;
        g_stores_attempted = 1;
    } else if (strcmp(command, "import-identity") == 0) {
        keys = import_keys;
    }
    if (g_grace_on) {
        budget = grace_slice();
        if (budget <= 0) {
            fail("deadline");
            return -1;
        }
    }
    /* Exit 1 still carries an allowlisted result. The caller classifies it. */
    if (run_child(argv, kind, log_name, captured, budget, -1, NULL) != 0) {
        return -1;
    }
    if (capture_allowlisted(captured->output, keys) != 0 || capture_field(captured->output, "result", result, sizeof result) != 0 ||
        category_from_result(result) != 0) {
        fail("unsupported");
        return -1;
    }
    note_calls(captured->output);
    if (strcmp(command, "create-stores") == 0 &&
        (copy_choice(captured->output, "search_list_equal", g_search_equal, sizeof g_search_equal, "yes", "no", "not_run") != 0 ||
         copy_choice(captured->output, "default_equal", g_default_equal, sizeof g_default_equal, "yes", "no", "not_run") != 0 ||
         copy_choice(captured->output, "basename_contract", g_basename_contract, sizeof g_basename_contract, "pass", "fail",
                     "not_run") != 0)) {
        fail("unsupported");
        return -1;
    }
    if (strcmp(result, "ok") != 0) {
        fail(result);
        return -1;
    }
    if (strcmp(command, "create-stores") == 0 &&
        (strcmp(g_search_equal, "yes") != 0 || strcmp(g_default_equal, "yes") != 0 || strcmp(g_basename_contract, "pass") != 0)) {
        fail("unsupported");
        return -1;
    }
    return 0;
}

static int write_secret_pass(const char *name) {
    unsigned char raw[16];
    char pass[33];
    int tries;
    for (tries = 0; tries < 3; tries++) {
        if (random_bytes(raw, sizeof raw) != 0) {
            return -1;
        }
        hex_encode(raw, sizeof raw, pass);
        if (varied_hex(pass, 32, 1, 0)) {
            int rc = create_file(g_run.fd, name, pass, 0600, NULL);
            memset(pass, 0, sizeof pass);
            memset(raw, 0, sizeof raw);
            return rc;
        }
    }
    memset(pass, 0, sizeof pass);
    return -1;
}

static int write_cnf(void) {
    const char *body = "[req]\n"
                       "distinguished_name=req_distinguished_name\n"
                       "x509_extensions=v3_req\n"
                       "prompt=no\n"
                       "[req_distinguished_name]\n"
                       "CN=Mnemion Fixture Leaf\n"
                       "[v3_req]\n"
                       "basicConstraints=CA:FALSE\n"
                       "keyUsage=digitalSignature\n"
                       "extendedKeyUsage=codeSigning\n";
    return create_file(g_run.fd, "leaf.cnf", body, 0600, NULL);
}

static int run_openssl(char *const argv[], const char *log_name) {
    return run_child(argv, "openssl", log_name, NULL, child_budget(), 0, "identity_refused");
}

static int generate_identity(void) {
    char key_path[1100];
    char cer_path[1100];
    char p12_path[1100];
    char cnf_path[1100];
    char pass_path[1100];
    char *gen[6];
    char *req[16];
    char *pack[14];
    if (write_cnf() != 0 || write_secret_pass("pkcs.pass") != 0 || under_run("leaf.key", key_path, sizeof key_path) != 0 ||
        under_run("leaf.cer", cer_path, sizeof cer_path) != 0 || under_run("leaf.p12", p12_path, sizeof p12_path) != 0 ||
        under_run("leaf.cnf", cnf_path, sizeof cnf_path) != 0 || under_run("pkcs.pass", pass_path, sizeof pass_path) != 0) {
        fail("identity_refused");
        return -1;
    }
    gen[0] = "/usr/bin/openssl";
    gen[1] = "genrsa";
    gen[2] = "-out";
    gen[3] = key_path;
    gen[4] = "2048";
    gen[5] = NULL;
    if (run_openssl(gen, "log-openssl-key") != 0) {
        return -1;
    }
    req[0] = "/usr/bin/openssl";
    req[1] = "req";
    req[2] = "-new";
    req[3] = "-x509";
    req[4] = "-key";
    req[5] = key_path;
    req[6] = "-out";
    req[7] = cer_path;
    req[8] = "-outform";
    req[9] = "DER";
    req[10] = "-days";
    req[11] = "2";
    req[12] = "-config";
    req[13] = cnf_path;
    req[14] = NULL;
    if (run_openssl(req, "log-openssl-req") != 0) {
        return -1;
    }
    pack[0] = "/usr/bin/openssl";
    pack[1] = "pkcs12";
    pack[2] = "-export";
    pack[3] = "-inkey";
    pack[4] = key_path;
    pack[5] = "-in";
    pack[6] = cer_path;
    pack[7] = "-out";
    pack[8] = p12_path;
    pack[9] = "-passout";
    pack[10] = "file:";
    /* The password stays in the file. The next argument is replaced below. */
    pack[10] = NULL;
    {
        char passout[1200];
        int written = snprintf(passout, sizeof passout, "file:%s", pass_path);
        if (written < 0 || (size_t)written >= sizeof passout) {
            fail("identity_refused");
            return -1;
        }
        pack[10] = passout;
        pack[11] = NULL;
        return run_openssl(pack, "log-openssl-p12");
    }
}

static int read_measure(unsigned long long *store_dev, unsigned long long *store_ino, unsigned long long *run_dev,
                        unsigned long long *run_ino) {
    char buffer[512];
    int fd;
    struct stat st;
    size_t filled = 0;
    char symlinks[16];
    char mode[16];
    char regular[8];
    char base[8];
    char get_path[8];
    char signing[8];
    char number[32];
    fd = openat(g_run.fd, "store-measure.txt", O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0 || fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || st.st_size <= 0 || st.st_size >= (off_t)sizeof buffer) {
        if (fd >= 0) {
            close(fd);
        }
        return -1;
    }
    while (filled < (size_t)st.st_size) {
        ssize_t count = read(fd, buffer + filled, (size_t)st.st_size - filled);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count <= 0) {
            close(fd);
            return -1;
        }
        filled += (size_t)count;
    }
    close(fd);
    buffer[filled] = '\0';
    if (capture_field(buffer, "basename_contract", base, sizeof base) != 0 || strcmp(base, "pass") != 0 ||
        capture_field(buffer, "get_path_match", get_path, sizeof get_path) != 0 || strcmp(get_path, "yes") != 0 ||
        capture_field(buffer, "signing_path_match", signing, sizeof signing) != 0 || strcmp(signing, "yes") != 0 ||
        capture_field(buffer, "regular", regular, sizeof regular) != 0 || strcmp(regular, "yes") != 0 ||
        capture_field(buffer, "mode", mode, sizeof mode) != 0 || strcmp(mode, "0600") != 0 ||
        capture_field(buffer, "companion_symlinks", symlinks, sizeof symlinks) != 0) {
        return -1;
    }
    if (capture_field(buffer, "store_device", number, sizeof number) != 0) {
        return -1;
    }
    *store_dev = strtoull(number, NULL, 10);
    if (capture_field(buffer, "store_inode", number, sizeof number) != 0) {
        return -1;
    }
    *store_ino = strtoull(number, NULL, 10);
    if (capture_field(buffer, "run_device", number, sizeof number) != 0) {
        return -1;
    }
    *run_dev = strtoull(number, NULL, 10);
    if (capture_field(buffer, "run_inode", number, sizeof number) != 0) {
        return -1;
    }
    *run_ino = strtoull(number, NULL, 10);
    g_symlinks = atoi(symlinks);
    return 0;
}

static int write_header_file(const char *name, const char *body) {
    int dirfd;
    int fd;
    if (strstr(body, "compile_only") != NULL || strstr(body, "UNSUBSTITUTED") != NULL ||
        strstr(body, "BEGIN PRIVATE") != NULL) {
        return -1;
    }
    dirfd = openat(g_run.fd, "include", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (dirfd < 0) {
        return -1;
    }
    fd = openat(dirfd, name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0 || fchmod(fd, 0600) != 0 || write_all_fd(fd, body, strlen(body)) != 0 || fsync(fd) != 0) {
        if (fd >= 0) {
            close(fd);
        }
        close(dirfd);
        return -1;
    }
    close(fd);
    close(dirfd);
    return 0;
}

static int write_store_header(void) {
    unsigned long long store_dev = 0;
    unsigned long long store_ino = 0;
    unsigned long long run_dev = 0;
    unsigned long long run_ino = 0;
    struct stat run_st;
    struct stat store_st;
    char header[2048];
    char service[80];
    char account[80];
    int written;
    if (read_measure(&store_dev, &store_ino, &run_dev, &run_ino) != 0 || fstat(g_run.fd, &run_st) != 0) {
        fail("store_basename_contract");
        return -1;
    }
    if ((unsigned long long)run_st.st_dev != run_dev || (unsigned long long)run_st.st_ino != run_ino ||
        run_st.st_dev != g_run.dev || run_st.st_ino != g_run.ino) {
        fail("store_basename_contract");
        return -1;
    }
    if (fstatat(g_run.fd, REAL_STORE_DATA_BASENAME, &store_st, AT_SYMLINK_NOFOLLOW) != 0 || !S_ISREG(store_st.st_mode) ||
        S_ISLNK(store_st.st_mode) || (store_st.st_mode & 07777) != 0600 || (unsigned long long)store_st.st_dev != store_dev ||
        (unsigned long long)store_st.st_ino != store_ino) {
        fail("store_basename_contract");
        return -1;
    }
    snprintf(service, sizeof service, "%s%s", REAL_STORE_SERVICE_PREFIX, g_run.nonce);
    snprintf(account, sizeof account, "%s%s", REAL_STORE_ACCOUNT_PREFIX, g_run.nonce);
    written = snprintf(header, sizeof header,
                       "#ifndef MNEMION_FIXTURE_STORE_CONFIG_H\n"
                       "#define MNEMION_FIXTURE_STORE_CONFIG_H\n"
                       "#define MNEMION_FIXTURE_STORE_CLASS \"fixture\"\n"
                       "#define MNEMION_FIXTURE_STORE_METADATA \"fixture: owned private data store for one empty lookup\"\n"
                       "#define MNEMION_FIXTURE_SERVICE_PREFIX \"%s\"\n"
                       "#define MNEMION_FIXTURE_ACCOUNT_PREFIX \"%s\"\n"
                       "#define MNEMION_FIXTURE_STORE_BASENAME \"%s\"\n"
                       "#define MNEMION_FIXTURE_RECORD_BASENAME \"%s\"\n"
                       "#define MNEMION_FIXTURE_RUN_DIRECTORY \"%s\"\n"
                       "#define MNEMION_FIXTURE_NONCE \"%s\"\n"
                       "#define MNEMION_FIXTURE_EUID %llu\n"
                       "#define MNEMION_FIXTURE_RUN_DEVICE %llu\n"
                       "#define MNEMION_FIXTURE_RUN_INODE %llu\n"
                       "#define MNEMION_FIXTURE_STORE_DEVICE %llu\n"
                       "#define MNEMION_FIXTURE_STORE_INODE %llu\n"
                       "#define MNEMION_FIXTURE_SERVICE \"%s\"\n"
                       "#define MNEMION_FIXTURE_ACCOUNT \"%s\"\n"
                       "#endif\n",
                       REAL_STORE_SERVICE_PREFIX, REAL_STORE_ACCOUNT_PREFIX, REAL_STORE_DATA_BASENAME, REAL_STORE_RECORD_BASENAME,
                       g_run.path, g_run.nonce, (unsigned long long)geteuid(), run_dev, run_ino, store_dev, store_ino, service,
                       account);
    if (written < 0 || (size_t)written >= sizeof header || write_header_file("fixture_store_config.h", header) != 0) {
        fail("store_basename_contract");
        return -1;
    }
    return 0;
}

static int write_caller_header(const char *sha1, const char *sha256) {
    char header[1024];
    int written;
    if (!varied_hex(sha1, 40, 1, 0) || !varied_hex(sha256, 64, 1, 0)) {
        fail("pin_rejected");
        return -1;
    }
    written = snprintf(header, sizeof header,
                       "#ifndef MNEMION_CALLER_PIN_H\n"
                       "#define MNEMION_CALLER_PIN_H\n"
                       "#define MNEMION_PIN_CLASS \"fixture\"\n"
                       "#define MNEMION_PIN_METADATA \"fixture: ephemeral leaf for one owned signing store\"\n"
                       "#define MNEMION_FIXTURE_LEAF_SHA1 \"%s\"\n"
                       "#define MNEMION_FIXTURE_LEAF_SHA256 \"%s\"\n"
                       "#endif\n",
                       sha1, sha256);
    if (written < 0 || (size_t)written >= sizeof header || strstr(header, "MNEMION_HELPER_CDHASH") != NULL ||
        write_header_file("caller_pin.h", header) != 0) {
        fail("pin_rejected");
        return -1;
    }
    snprintf(g_sha1, sizeof g_sha1, "%s", sha1);
    snprintf(g_sha256, sizeof g_sha256, "%s", sha256);
    return 0;
}

static int escape_requirement(const char *text, char *out, size_t cap) {
    size_t used = 0;
    size_t index;
    if (text == NULL || text[0] == '\0' || strlen(text) > 800) {
        return -1;
    }
    for (index = 0; text[index] != '\0'; index++) {
        unsigned char character = (unsigned char)text[index];
        int extra = (character == '\\' || character == '"') ? 2 : 1;
        if (character < 32 || character > 126 || used + (size_t)extra + 1 > cap) {
            return -1;
        }
        if (extra == 2) {
            out[used++] = '\\';
        }
        out[used++] = (char)character;
    }
    out[used] = '\0';
    return 0;
}

static int write_parent_header(const char *cdhash, const char *manifest, const char *designated) {
    char escaped[1024];
    char header[2048];
    int written;
    if (!varied_hex(cdhash, strlen(cdhash), 0, 1) || (strlen(cdhash) != 40 && strlen(cdhash) != 64) ||
        !varied_hex(manifest, 64, 1, 0) || escape_requirement(designated, escaped, sizeof escaped) != 0) {
        fail("pin_rejected");
        return -1;
    }
    written = snprintf(header, sizeof header,
                       "#ifndef MNEMION_PARENT_PIN_H\n"
                       "#define MNEMION_PARENT_PIN_H\n"
                       "#define MNEMION_HELPER_CDHASH \"%s\"\n"
                       "#define MNEMION_HELPER_MANIFEST_SHA256 \"%s\"\n"
                       "#define MNEMION_SEALED_HELPER_IDENTIFIER \"%s\"\n"
                       "#define MNEMION_HELPER_DESIGNATED \"%s\"\n"
                       "#endif\n",
                       cdhash, manifest, MNEMION_HELPER_IDENTIFIER, escaped);
    if (written < 0 || (size_t)written >= sizeof header || write_header_file("parent_pin.h", header) != 0) {
        fail("pin_rejected");
        return -1;
    }
    return 0;
}

static int mkdir_rel(const char *relative) {
    char copy[256];
    char *cursor;
    int fd;
    if (strlen(relative) >= sizeof copy || strchr(relative, '\\') != NULL || strstr(relative, "..") != NULL) {
        return -1;
    }
    memcpy(copy, relative, strlen(relative) + 1);
    fd = dup(g_run.fd);
    if (fd < 0) {
        return -1;
    }
    cursor = copy;
    while (cursor != NULL && *cursor != '\0') {
        char *slash = strchr(cursor, '/');
        int next;
        struct stat st;
        if (slash != NULL) {
            *slash = '\0';
        }
        if (cursor[0] == '\0' || strcmp(cursor, ".") == 0 || strcmp(cursor, "..") == 0) {
            close(fd);
            return -1;
        }
        if (fstatat(fd, cursor, &st, AT_SYMLINK_NOFOLLOW) != 0) {
            if (mkdirat(fd, cursor, 0700) != 0) {
                close(fd);
                return -1;
            }
        }
        next = openat(fd, cursor, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        close(fd);
        if (next < 0) {
            return -1;
        }
        fd = next;
        if (fchmod(fd, 0700) != 0) {
            close(fd);
            return -1;
        }
        cursor = slash == NULL ? NULL : slash + 1;
    }
    close(fd);
    return 0;
}

static int copy_bytes(const char *src, int dst_parent, const char *dst_name, mode_t mode) {
    int in;
    int out;
    struct stat st;
    char buffer[16384];
    if (lstat(src, &st) != 0 || !S_ISREG(st.st_mode) || S_ISLNK(st.st_mode)) {
        return -1;
    }
    in = open(src, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    out = openat(dst_parent, dst_name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, mode);
    if (in < 0 || out < 0 || fchmod(out, mode) != 0) {
        if (in >= 0) {
            close(in);
        }
        if (out >= 0) {
            close(out);
        }
        return -1;
    }
    while (1) {
        ssize_t count = read(in, buffer, sizeof buffer);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count < 0) {
            close(in);
            close(out);
            return -1;
        }
        if (count == 0) {
            break;
        }
        if (write_all_fd(out, buffer, (size_t)count) != 0) {
            close(in);
            close(out);
            return -1;
        }
    }
    if (fsync(out) != 0) {
        close(in);
        close(out);
        return -1;
    }
    close(in);
    close(out);
    return 0;
}

static int open_rel(const char *relative) {
    char copy[256];
    char *cursor;
    int fd;
    if (strlen(relative) >= sizeof copy) {
        return -1;
    }
    memcpy(copy, relative, strlen(relative) + 1);
    fd = dup(g_run.fd);
    if (fd < 0) {
        return -1;
    }
    cursor = copy;
    while (cursor != NULL && *cursor != '\0') {
        char *slash = strchr(cursor, '/');
        int next;
        if (slash != NULL) {
            *slash = '\0';
        }
        next = openat(fd, cursor, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        close(fd);
        if (next < 0) {
            return -1;
        }
        fd = next;
        cursor = slash == NULL ? NULL : slash + 1;
    }
    return fd;
}

static int assemble_helper_bundle(void) {
    int resources;
    if (mkdir_rel("MnemionCredentialHelper.xpc/Contents/MacOS") != 0 ||
        mkdir_rel("MnemionCredentialHelper.xpc/Contents/Resources") != 0) {
        return -1;
    }
    resources = open_rel("MnemionCredentialHelper.xpc/Contents");
    if (resources < 0 || copy_bytes("deploy/macos_keychain_proof/HelperInfo.plist", resources, "Info.plist", 0600) != 0) {
        if (resources >= 0) {
            close(resources);
        }
        return -1;
    }
    close(resources);
    resources = open_rel("MnemionCredentialHelper.xpc/Contents/Resources");
    if (resources < 0 || copy_bytes("deploy/macos_keychain_proof/IdentityEpoch", resources, "IdentityEpoch", 0600) != 0) {
        if (resources >= 0) {
            close(resources);
        }
        return -1;
    }
    close(resources);
    return 0;
}

static int copy_tree(int src, int dst, int depth) {
    DIR *dir;
    struct dirent *ent;
    int fd;
    if (depth > 8) {
        return -1;
    }
    fd = dup(src);
    if (fd < 0) {
        return -1;
    }
    dir = fdopendir(fd);
    if (dir == NULL) {
        close(fd);
        return -1;
    }
    errno = 0;
    while ((ent = readdir(dir)) != NULL) {
        struct stat st;
        if (strcmp(ent->d_name, ".") == 0 || strcmp(ent->d_name, "..") == 0) {
            errno = 0;
            continue;
        }
        if (fstatat(dirfd(dir), ent->d_name, &st, AT_SYMLINK_NOFOLLOW) != 0 || S_ISLNK(st.st_mode)) {
            closedir(dir);
            return -1;
        }
        if (S_ISDIR(st.st_mode)) {
            int child_src;
            int child_dst;
            if (mkdirat(dst, ent->d_name, 0700) != 0) {
                closedir(dir);
                return -1;
            }
            child_src = openat(dirfd(dir), ent->d_name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
            child_dst = openat(dst, ent->d_name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
            if (child_src < 0 || child_dst < 0 || fchmod(child_dst, 0700) != 0 || copy_tree(child_src, child_dst, depth + 1) != 0) {
                if (child_src >= 0) {
                    close(child_src);
                }
                if (child_dst >= 0) {
                    close(child_dst);
                }
                closedir(dir);
                return -1;
            }
            close(child_src);
            close(child_dst);
        } else if (S_ISREG(st.st_mode)) {
            int in = openat(dirfd(dir), ent->d_name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
            int out = openat(dst, ent->d_name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
            mode_t mode = (st.st_mode & 0111) != 0 ? 0755 : 0600;
            char buffer[16384];
            if (in < 0 || out < 0 || fchmod(out, mode) != 0) {
                if (in >= 0) {
                    close(in);
                }
                if (out >= 0) {
                    close(out);
                }
                closedir(dir);
                return -1;
            }
            while (1) {
                ssize_t count = read(in, buffer, sizeof buffer);
                if (count < 0 && errno == EINTR) {
                    continue;
                }
                if (count < 0 || (count > 0 && write_all_fd(out, buffer, (size_t)count) != 0)) {
                    close(in);
                    close(out);
                    closedir(dir);
                    return -1;
                }
                if (count == 0) {
                    break;
                }
            }
            if (fsync(out) != 0) {
                close(in);
                close(out);
                closedir(dir);
                return -1;
            }
            close(in);
            close(out);
        } else {
            closedir(dir);
            return -1;
        }
        errno = 0;
    }
    if (errno != 0) {
        closedir(dir);
        return -1;
    }
    closedir(dir);
    return 0;
}

static int freeze_helper_tree(void) {
    int src;
    int dst_parent;
    int dst;
    if (mkdir_rel("frozen") != 0) {
        return -1;
    }
    src = open_rel("MnemionCredentialHelper.xpc");
    dst_parent = open_rel("frozen");
    if (src < 0 || dst_parent < 0 || mkdirat(dst_parent, "MnemionCredentialHelper.xpc", 0700) != 0) {
        if (src >= 0) {
            close(src);
        }
        if (dst_parent >= 0) {
            close(dst_parent);
        }
        return -1;
    }
    dst = openat(dst_parent, "MnemionCredentialHelper.xpc", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    close(dst_parent);
    if (dst < 0 || copy_tree(src, dst, 0) != 0) {
        close(src);
        if (dst >= 0) {
            close(dst);
        }
        return -1;
    }
    close(src);
    close(dst);
    return 0;
}

static int tree_rejects_private_names(int dirfd, int depth) {
    int fd;
    DIR *dir;
    struct dirent *ent;
    if (depth > 8) {
        return -1;
    }
    fd = dup(dirfd);
    if (fd < 0) {
        return -1;
    }
    dir = fdopendir(fd);
    if (dir == NULL) {
        close(fd);
        return -1;
    }
    errno = 0;
    while ((ent = readdir(dir)) != NULL) {
        struct stat st;
        if (strcmp(ent->d_name, ".") == 0 || strcmp(ent->d_name, "..") == 0) {
            errno = 0;
            continue;
        }
        if (strstr(ent->d_name, "parent_pin") != NULL || strstr(ent->d_name, "caller_pin") != NULL ||
            strstr(ent->d_name, "fixture_store_config") != NULL || strstr(ent->d_name, ".p12") != NULL ||
            strstr(ent->d_name, "signing.pass") != NULL) {
            closedir(dir);
            return -1;
        }
        if (fstatat(dirfd, ent->d_name, &st, AT_SYMLINK_NOFOLLOW) != 0 || S_ISLNK(st.st_mode)) {
            closedir(dir);
            return -1;
        }
        if (S_ISDIR(st.st_mode)) {
            int child = openat(dirfd, ent->d_name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
            if (child < 0 || tree_rejects_private_names(child, depth + 1) != 0) {
                if (child >= 0) {
                    close(child);
                }
                closedir(dir);
                return -1;
            }
            close(child);
        } else if (!S_ISREG(st.st_mode)) {
            closedir(dir);
            return -1;
        }
        errno = 0;
    }
    if (errno != 0) {
        closedir(dir);
        return -1;
    }
    closedir(dir);
    return 0;
}

static int assemble_parent(const char *parent_name, const char *generation) {
    char rel_contents[128];
    char rel_resources[160];
    char rel_xpc[160];
    char rel_mac[160];
    int contents;
    int resources;
    int xpc_parent;
    int src;
    int dst;
    snprintf(rel_contents, sizeof rel_contents, "%s/Contents", parent_name);
    snprintf(rel_resources, sizeof rel_resources, "%s/Contents/Resources", parent_name);
    snprintf(rel_mac, sizeof rel_mac, "%s/Contents/MacOS", parent_name);
    snprintf(rel_xpc, sizeof rel_xpc, "%s/Contents/XPCServices", parent_name);
    if (mkdir_rel(rel_resources) != 0 || mkdir_rel(rel_mac) != 0 || mkdir_rel(rel_xpc) != 0) {
        return -1;
    }
    contents = open_rel(rel_contents);
    resources = open_rel(rel_resources);
    if (contents < 0 || resources < 0 || copy_bytes("deploy/macos_keychain_proof/ParentInfo.plist", contents, "Info.plist", 0600) != 0 ||
        copy_bytes(generation, resources, "generation.txt", 0600) != 0) {
        if (contents >= 0) {
            close(contents);
        }
        if (resources >= 0) {
            close(resources);
        }
        return -1;
    }
    close(contents);
    close(resources);
    xpc_parent = open_rel(rel_xpc);
    src = open_rel("frozen/MnemionCredentialHelper.xpc");
    if (xpc_parent < 0 || src < 0 || mkdirat(xpc_parent, "MnemionCredentialHelper.xpc", 0700) != 0) {
        if (xpc_parent >= 0) {
            close(xpc_parent);
        }
        if (src >= 0) {
            close(src);
        }
        return -1;
    }
    dst = openat(xpc_parent, "MnemionCredentialHelper.xpc", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    close(xpc_parent);
    if (dst < 0 || copy_tree(src, dst, 0) != 0) {
        close(src);
        if (dst >= 0) {
            close(dst);
        }
        return -1;
    }
    close(src);
    close(dst);
    return 0;
}

static int sign_bundle(const char *suffix, const char *log_name) {
    char bundle[1100];
    char keychain[1100];
    char upper[41];
    char *argv[10];
    size_t index;
    if (strlen(g_sha1) != 40 || under_run(suffix, bundle, sizeof bundle) != 0 ||
        under_run(REAL_STORE_SIGNING_BASENAME, keychain, sizeof keychain) != 0) {
        fail("signing_refused");
        return -1;
    }
    for (index = 0; index < 40; index++) {
        char character = g_sha1[index];
        if (character >= 'a' && character <= 'f') {
            character = (char)(character - 'a' + 'A');
        }
        upper[index] = character;
    }
    upper[40] = '\0';
    argv[0] = "/usr/bin/codesign";
    argv[1] = "--sign";
    argv[2] = upper;
    argv[3] = "--keychain";
    argv[4] = keychain;
    argv[5] = "--timestamp=none";
    argv[6] = bundle;
    argv[7] = NULL;
    return run_child(argv, "codesign", log_name, NULL, child_budget(), 0, "signing_refused");
}

static int accept_freeze(struct child_result *captured) {
    char cdhash[80];
    char identifier[256];
    char designated[1024];
    char sha1[41];
    char sha256[65];
    char manifest[65];
    static const char *keys[] = {"cdhash", "identifier", "designated", "leaf_sha1", "leaf_sha256", "manifest_sha256", NULL};
    if (capture_allowlisted(captured->output, keys) != 0 || capture_field(captured->output, "cdhash", cdhash, sizeof cdhash) != 0 ||
        capture_field(captured->output, "identifier", identifier, sizeof identifier) != 0 ||
        capture_field(captured->output, "designated", designated, sizeof designated) != 0 ||
        capture_field(captured->output, "leaf_sha1", sha1, sizeof sha1) != 0 ||
        capture_field(captured->output, "leaf_sha256", sha256, sizeof sha256) != 0 ||
        capture_field(captured->output, "manifest_sha256", manifest, sizeof manifest) != 0) {
        fail("measure_failed");
        return -1;
    }
    if (strcmp(identifier, MNEMION_HELPER_IDENTIFIER) != 0) {
        fail("requirement_mismatch");
        return -1;
    }
    if (strcmp(sha1, g_sha1) != 0 || strcmp(sha256, g_sha256) != 0) {
        fail("certificate_mismatch");
        return -1;
    }
    return write_parent_header(cdhash, manifest, designated);
}

static int accept_compare(const char *text) {
    static const char *keys[] = {"trees_equal",
                                 "manifest_equal",
                                 "helper_cdhash_equal",
                                 "helper_requirement_equal",
                                 "helper_identifier_equal",
                                 "helper_der_equal",
                                 "parent_cdhash_distinct",
                                 "parent_identifier_equal",
                                 "parent_der_equal",
                                 "parent_helper_der_equal",
                                 NULL};
    int index;
    if (capture_allowlisted(text, keys) != 0) {
        fail("measure_failed");
        return -1;
    }
    for (index = 0; keys[index] != NULL; index++) {
        char value[8];
        if (capture_field(text, keys[index], value, sizeof value) != 0 || strcmp(value, "yes") != 0) {
            if (strcmp(keys[index], "trees_equal") == 0) {
                fail("tree_mismatch");
            } else if (strcmp(keys[index], "manifest_equal") == 0) {
                fail("manifest_mismatch");
            } else if (strcmp(keys[index], "parent_cdhash_distinct") == 0) {
                fail("cdhash_not_distinct");
            } else if (strstr(keys[index], "der") != NULL) {
                fail("certificate_mismatch");
            } else {
                fail("requirement_mismatch");
            }
            return -1;
        }
    }
    return 0;
}

static int run_measure(const char *command, char *const extra[], int extra_count, const char *log_name, struct child_result *captured) {
    char binary[1100];
    char *argv[8];
    int index;
    if (extra_count < 1 || extra_count > 5 || under_run("measure", binary, sizeof binary) != 0) {
        fail("measure_failed");
        return -1;
    }
    argv[0] = binary;
    argv[1] = (char *)command;
    for (index = 0; index < extra_count; index++) {
        argv[index + 2] = extra[index];
    }
    argv[extra_count + 2] = NULL;
    return run_child(argv, "measure", log_name, captured, child_budget(), -1, "measure_failed");
}

static int file_equals(const char *name, const char *expect) {
    char buffer[256];
    int fd;
    struct stat st;
    size_t filled = 0;
    size_t expect_len = strlen(expect);
    fd = openat(g_run.fd, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0 || fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || (size_t)st.st_size != expect_len || expect_len >= sizeof buffer) {
        if (fd >= 0) {
            close(fd);
        }
        return 0;
    }
    while (filled < expect_len) {
        ssize_t count = read(fd, buffer + filled, expect_len - filled);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count <= 0) {
            close(fd);
            return 0;
        }
        filled += (size_t)count;
    }
    close(fd);
    return memcmp(buffer, expect, expect_len) == 0;
}

static int run_parent(const char *command, const char *log_name, struct child_result *captured) {
    char binary[1100];
    char *argv[3];
    if (under_run("parent-a/MnemionCredentialParent.app/Contents/MacOS/MnemionCredentialParent", binary, sizeof binary) != 0) {
        fail("check_helper_mismatch");
        return -1;
    }
    argv[0] = binary;
    argv[1] = (char *)command;
    argv[2] = NULL;
    return run_child(argv, strcmp(command, "check-helper") == 0 ? "check" : "lookup", log_name, captured, child_budget(), -1, NULL);
}

static int stage(void) {
    struct child_result captured;
    char frozen[1100];
    char helper_a[1100];
    char helper_b[1100];
    char parent_a[1100];
    char parent_b[1100];
    char *compare_args[5];
    char *freeze_args[1];
    int frozen_fd;
    if (read_git() != 0 || compile_provision() != 0) {
        return -1;
    }
    if (provision_command("create-stores", "provision", "log-create", &captured) != 0) {
        return -1;
    }
    if (write_store_header() != 0 || generate_identity() != 0) {
        return -1;
    }
    if (provision_command("import-identity", "import", "log-import", &captured) != 0) {
        return -1;
    }
    {
        char sha1[41];
        char sha256[65];
        char scope[16];
        if (capture_field(captured.output, "leaf_sha1", sha1, sizeof sha1) != 0 ||
            capture_field(captured.output, "leaf_sha256", sha256, sizeof sha256) != 0 ||
            capture_field(captured.output, "acl_scope", scope, sizeof scope) != 0 || strcmp(scope, "codesign") != 0 ||
            write_caller_header(sha1, sha256) != 0) {
            fail("pin_rejected");
            return -1;
        }
    }
    if (compile_measure() != 0 || assemble_helper_bundle() != 0 || compile_helper() != 0) {
        return -1;
    }
    if (provision_command("unlock-signing", "unlock", "log-unlock-sign", &captured) != 0 ||
        sign_bundle("MnemionCredentialHelper.xpc", "log-codesign-helper") != 0) {
        return -1;
    }
    frozen_fd = open_rel("MnemionCredentialHelper.xpc");
    if (frozen_fd < 0 || tree_rejects_private_names(frozen_fd, 0) != 0 || freeze_helper_tree() != 0) {
        if (frozen_fd >= 0) {
            close(frozen_fd);
        }
        fail("signing_refused");
        return -1;
    }
    close(frozen_fd);
    if (under_run("frozen/MnemionCredentialHelper.xpc", frozen, sizeof frozen) != 0) {
        fail("measure_failed");
        return -1;
    }
    freeze_args[0] = frozen;
    if (run_measure("freeze", freeze_args, 1, "log-freeze", &captured) != 0 || accept_freeze(&captured) != 0) {
        return -1;
    }
    if (assemble_parent("parent-a/MnemionCredentialParent.app", "deploy/macos_keychain_proof/generation-a.txt") != 0 ||
        assemble_parent("parent-b/MnemionCredentialParent.app", "deploy/macos_keychain_proof/generation-b.txt") != 0 ||
        compile_parent("parent-a/MnemionCredentialParent.app/Contents/MacOS/MnemionCredentialParent", "log-clang-parent-a") != 0 ||
        sign_bundle("parent-a/MnemionCredentialParent.app", "log-codesign-a") != 0 ||
        compile_parent("parent-b/MnemionCredentialParent.app/Contents/MacOS/MnemionCredentialParent", "log-clang-parent-b") != 0 ||
        sign_bundle("parent-b/MnemionCredentialParent.app", "log-codesign-b") != 0 ||
        provision_command("lock-signing", "lock", "log-lock-sign", &captured) != 0) {
        return -1;
    }
    if (under_run("parent-a/MnemionCredentialParent.app/Contents/XPCServices/MnemionCredentialHelper.xpc", helper_a, sizeof helper_a) != 0 ||
        under_run("parent-b/MnemionCredentialParent.app/Contents/XPCServices/MnemionCredentialHelper.xpc", helper_b, sizeof helper_b) != 0 ||
        under_run("parent-a/MnemionCredentialParent.app", parent_a, sizeof parent_a) != 0 ||
        under_run("parent-b/MnemionCredentialParent.app", parent_b, sizeof parent_b) != 0) {
        fail("measure_failed");
        return -1;
    }
    compare_args[0] = frozen;
    compare_args[1] = helper_a;
    compare_args[2] = helper_b;
    compare_args[3] = parent_a;
    compare_args[4] = parent_b;
    if (run_measure("compare", compare_args, 5, "log-compare", &captured) != 0 || accept_compare(captured.output) != 0) {
        return -1;
    }
    if (run_parent("check-helper", "log-check", &captured) != 0) {
        return -1;
    }
    if (WIFEXITED(captured.status)) {
        g_check_exit = WEXITSTATUS(captured.status);
    }
    if (g_check_exit != 0 || strcmp(captured.output, "result=ok\nkeychain_calls=0\n") != 0 || !file_equals("log-check", "")) {
        fail("check_helper_mismatch");
        return -1;
    }
    if (provision_command("unlock-data", "unlock", "log-unlock-data", &captured) != 0) {
        return -1;
    }
    if (run_parent("direct-lookup", "log-lookup", &captured) != 0) {
        return -1;
    }
    if (WIFEXITED(captured.status)) {
        g_lookup_exit = WEXITSTATUS(captured.status);
    }
    if (g_lookup_exit != 1 || strcmp(captured.output, "result=missing_key\nkeychain_calls=1\n") != 0 ||
        !file_equals("log-lookup", "direct_lookup=interaction_bracket\n")) {
        fail("direct_lookup_mismatch");
        return -1;
    }
    if (provision_command("lock-data", "lock", "log-lock-data", &captured) != 0) {
        return -1;
    }
    return 0;
}

static long grace_slice(void) {
    long now = mono_ms();
    long slice;
    if (now < 0) {
        return 0;
    }
    slice = g_grace_deadline - now;
    if (slice < 0) {
        return 0;
    }
    if (slice > 2000) {
        return 2000;
    }
    return slice;
}

static int cleanup_time_up(void) {
    long now;
    if (!g_grace_on) {
        return 0;
    }
    now = mono_ms();
    return now < 0 || now >= g_grace_deadline;
}

static int identity_is(const struct stat *st, dev_t dev, ino_t ino, mode_t type) {
    return st->st_dev == dev && st->st_ino == ino && (st->st_mode & S_IFMT) == type && !S_ISLNK(st->st_mode);
}

static int remove_tree(int parent_fd, const char *name, dev_t expect_dev, ino_t expect_ino, int depth) {
    int fd;
    struct stat entry;
    struct stat st;
    struct stat again;
    DIR *dir;
    struct dirent *ent;
    if (cleanup_time_up() || depth > 8) {
        return -1;
    }
    if (fstatat(parent_fd, name, &entry, AT_SYMLINK_NOFOLLOW) != 0 || !identity_is(&entry, expect_dev, expect_ino, S_IFDIR)) {
        return -1;
    }
    fd = openat(parent_fd, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) {
        return -1;
    }
    if (fstat(fd, &st) != 0 || !identity_is(&st, entry.st_dev, entry.st_ino, S_IFDIR)) {
        close(fd);
        return -1;
    }
    dir = fdopendir(fd);
    if (dir == NULL) {
        close(fd);
        return -1;
    }
    errno = 0;
    while ((ent = readdir(dir)) != NULL) {
        struct stat child;
        struct stat before_unlink;
        if (cleanup_time_up()) {
            closedir(dir);
            return -1;
        }
        if (strcmp(ent->d_name, ".") == 0 || strcmp(ent->d_name, "..") == 0) {
            errno = 0;
            continue;
        }
        if (fstatat(dirfd(dir), ent->d_name, &child, AT_SYMLINK_NOFOLLOW) != 0) {
            closedir(dir);
            return -1;
        }
        if (S_ISDIR(child.st_mode) && !S_ISLNK(child.st_mode)) {
            if (child.st_dev != expect_dev || remove_tree(dirfd(dir), ent->d_name, expect_dev, child.st_ino, depth + 1) != 0) {
                closedir(dir);
                return -1;
            }
        } else if (S_ISREG(child.st_mode) && !S_ISLNK(child.st_mode)) {
            if (fstatat(dirfd(dir), ent->d_name, &before_unlink, AT_SYMLINK_NOFOLLOW) != 0 ||
                !identity_is(&before_unlink, child.st_dev, child.st_ino, S_IFREG) || unlinkat(dirfd(dir), ent->d_name, 0) != 0) {
                closedir(dir);
                return -1;
            }
        } else {
            closedir(dir);
            return -1;
        }
        errno = 0;
    }
    if (errno != 0) {
        closedir(dir);
        return -1;
    }
    if (closedir(dir) != 0) {
        return -1;
    }
    if (cleanup_time_up() || fstatat(parent_fd, name, &again, AT_SYMLINK_NOFOLLOW) != 0 ||
        !identity_is(&again, expect_dev, expect_ino, S_IFDIR) || unlinkat(parent_fd, name, AT_REMOVEDIR) != 0) {
        return -1;
    }
    return 0;
}

static int unlink_recorded_symlinks(void) {
    char buffer[1024];
    int fd;
    struct stat st;
    size_t filled = 0;
    char *cursor;
    if (g_symlinks < 0) {
        return 0;
    }
    if (g_symlinks == 0) {
        if (fstatat(g_run.fd, "companions.txt", &st, AT_SYMLINK_NOFOLLOW) == 0) {
            return -1;
        }
        return errno == ENOENT ? 0 : -1;
    }
    fd = openat(g_run.fd, "companions.txt", O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0 || fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || st.st_size <= 0 || st.st_size >= (off_t)sizeof buffer) {
        if (fd >= 0) {
            close(fd);
        }
        return -1;
    }
    while (filled < (size_t)st.st_size) {
        ssize_t count = read(fd, buffer + filled, (size_t)st.st_size - filled);
        if (count <= 0) {
            close(fd);
            return -1;
        }
        filled += (size_t)count;
    }
    close(fd);
    buffer[filled] = '\0';
    cursor = buffer;
    while (*cursor != '\0') {
        unsigned long long dev = 0;
        unsigned long long ino = 0;
        char name[80];
        struct stat link_st;
        char *end = strchr(cursor, '\n');
        if (end == NULL || sscanf(cursor, "lnk %llu %llu %79s", &dev, &ino, name) != 3) {
            return -1;
        }
        if (fstatat(g_run.fd, name, &link_st, AT_SYMLINK_NOFOLLOW) != 0 || !S_ISLNK(link_st.st_mode) ||
            (unsigned long long)link_st.st_dev != dev || (unsigned long long)link_st.st_ino != ino ||
            unlinkat(g_run.fd, name, 0) != 0) {
            return -1;
        }
        cursor = end + 1;
    }
    return 0;
}

static void begin_grace(void) {
    long now;
    if (!g_grace_on) {
        g_grace_on = 1;
        now = mono_ms();
        g_grace_deadline = now < 0 ? 0 : now + REAL_CLEANUP_GRACE_MS;
    }
}

static int observe_group_empty(struct child_slot *slot) {
    long start = mono_ms();
    long budget = grace_slice();
    if (slot == NULL || start < 0) {
        return -1;
    }
    while (1) {
        int occupied = group_occupied(slot->pgid);
        long now;
        long elapsed;
        int slice;
        if (occupied == 0) {
            pid_t pgid = slot->pgid;
            slot->live = 0;
            report_settled(pgid);
            return 0;
        }
        if (occupied < 0 || g_stop) {
            return -1;
        }
        now = mono_ms();
        if (now < 0) {
            return -1;
        }
        elapsed = now - start;
        if (elapsed >= budget || grace_slice() == 0) {
            return -1;
        }
        slice = (int)(budget - elapsed);
        if (slice > 50) {
            slice = 50;
        }
        if (g_wake[0] >= 0) {
            struct pollfd polls[1];
            int ready;
            polls[0].fd = g_wake[0];
            polls[0].events = POLLIN;
            ready = poll(polls, 1, slice);
            if (ready < 0 && errno != EINTR) {
                return -1;
            }
            if (ready > 0 && (polls[0].revents & POLLIN)) {
                drain_wake();
            }
        } else {
            nanosleep(&(struct timespec){0, 20000000L}, NULL);
        }
    }
}

static int settle_slot(struct child_slot *slot) {
    int status = 0;
    char reap[16];
    int occupied;
    long slice;
    if (slot == NULL || !slot->live) {
        return 0;
    }
    slice = grace_slice();
    if (!slot->leader_reaped) {
        signal_retained(slot, SIGTERM);
        if (wait_budget(slot->pid, &status, reap, sizeof reap, slice) != 0) {
            signal_retained(slot, SIGKILL);
            slice = grace_slice();
            if (wait_budget(slot->pid, &status, reap, sizeof reap, slice) != 0) {
                return -1;
            }
        }
    }
    if (!slot->live) {
        return 0;
    }
    occupied = group_occupied(slot->pgid);
    if (occupied == 0) {
        pid_t pgid = slot->pgid;
        slot->live = 0;
        report_settled(pgid);
        return 0;
    }
    if (occupied < 0) {
        return -1;
    }
    signal_retained(slot, SIGKILL);
    return observe_group_empty(slot);
}

static int stop_children(void) {
    int index;
    int unreaped = 0;
    begin_grace();
    for (index = 0; index < MAX_CHILDREN; index++) {
        if (settle_slot(&g_children[index]) != 0) {
            unreaped = 1;
        }
    }
    if (children_live()) {
        unreaped = 1;
    }
    return unreaped;
}

static int maybe_delete(void) {
    struct child_result captured;
    const char *log_name;
    if (g_deleted || !g_stores_attempted || children_live() || !g_run.live) {
        return 0;
    }
    if (g_delete_spawned >= 2) {
        fail("cleanup_incomplete");
        return -1;
    }
    log_name = g_delete_spawned == 0 ? "log-delete" : "log-delete-retry";
    g_delete_spawned++;
    if (provision_command("delete-owned", "delete", log_name, &captured) != 0) {
        return -1;
    }
    g_deleted = 1;
    return 0;
}

static int write_custody(void) {
    char name[32];
    char body[1024];
    int fd;
    int written;
    int index;
    snprintf(name, sizeof name, "custody-%s", g_custody_id[0] != '\0' ? g_custody_id : "none");
    written = snprintf(body, sizeof body, "cleanup=incomplete\ncategory=%s\n", g_error);
    if (written < 0 || (size_t)written >= sizeof body) {
        return -1;
    }
    if (g_run.live) {
        int added = snprintf(body + written, sizeof body - (size_t)written, "run_id=%s\n", g_run.id);
        if (added < 0 || (size_t)added >= sizeof body - (size_t)written) {
            return -1;
        }
        written += added;
    }
    for (index = 0; index < MAX_CHILDREN; index++) {
        int added;
        if (!g_children[index].live) {
            continue;
        }
        added = snprintf(body + written, sizeof body - (size_t)written, "pid=%d pgid=%d leader_reaped=%d kind=%s\n",
                         (int)g_children[index].pid, (int)g_children[index].pgid, g_children[index].leader_reaped,
                         g_children[index].kind);
        if (added < 0 || (size_t)added >= sizeof body - (size_t)written) {
            return -1;
        }
        written += added;
    }
    fd = openat(g_parent_fd, name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0 || write_all_fd(fd, body, (size_t)written) != 0) {
        if (fd >= 0) {
            close(fd);
        }
        return -1;
    }
    close(fd);
    return 0;
}

static int release_run(void) {
    struct stat held;
    struct stat name_st;
    if (!g_run.live) {
        return 0;
    }
    if (g_run.fd >= 0 && (fstat(g_run.fd, &held) != 0 || !identity_is(&held, g_run.dev, g_run.ino, S_IFDIR))) {
        return -1;
    }
    if (unlink_recorded_symlinks() != 0) {
        return -1;
    }
    if (fstatat(g_parent_fd, g_run.name, &name_st, AT_SYMLINK_NOFOLLOW) != 0 ||
        !identity_is(&name_st, g_run.dev, g_run.ino, S_IFDIR) || remove_tree(g_parent_fd, g_run.name, g_run.dev, g_run.ino, 0) != 0) {
        return -1;
    }
    if (g_run.fd >= 0) {
        close(g_run.fd);
        g_run.fd = -1;
    }
    report_run_cleared(g_run.dev, g_run.ino);
    g_run.live = 0;
    return 0;
}

static int cleanup_runs(void) {
    struct stat parent_st;
    begin_grace();
    report_phase();
    if (stop_children() != 0 || g_report_uncertain || g_cleanup_uncertain) {
        write_custody();
        return -1;
    }
    if (maybe_delete() != 0 || children_live()) {
        write_custody();
        return -1;
    }
    if (g_parent_fd < 0 || fstat(g_parent_fd, &parent_st) != 0 || !identity_is(&parent_st, g_parent_dev, g_parent_ino, S_IFDIR)) {
        write_custody();
        return -1;
    }
    if (release_run() != 0 || g_report_uncertain) {
        write_custody();
        return -1;
    }
    return 0;
}

static void print_receipt(int cleanup_ok) {
    const char *calls = "unavailable";
    char calls_buf[32];
    const char *deadline = g_deadline_hit ? "expired" : "inside";
    int artifact_ok = strcmp(g_error, "none") == 0 && !g_case_failure;
    int lookup_ok = artifact_ok;
    if (!g_calls_bad && g_calls >= 0) {
        snprintf(calls_buf, sizeof calls_buf, "%ld", g_calls);
        calls = calls_buf;
    }
    if (g_source[0] == '\0') {
        deadline = "not_run";
    }
    printf("receipt_version=1\n");
    printf("lane=real_store\n");
    printf("native_operations=real\n");
    printf("source=%s\n", g_source[0] != '\0' ? g_source : "unreadable");
    printf("architecture=%s\n", g_arch[0] != '\0' ? g_arch : "unreadable");
    printf("stage=%s\n", REAL_STORE_STAGE);
    printf("signing_class=%s\n", REAL_STORE_SIGNING_CLASS);
    printf("instrumented_security_calls=%s\n", calls);
    printf("instrumented_security_calls_coverage=%s\n", calls == calls_buf ? "provisioner_only" : "unavailable");
    printf("external_tool_security_calls=unavailable\n");
    printf("der_compare=%s\n", artifact_ok ? "yes" : (strcmp(g_error, "certificate_mismatch") == 0 ? "no" : "not_run"));
    printf("pin_compare=%s\n", artifact_ok ? "yes" : (strcmp(g_error, "pin_rejected") == 0 ? "no" : "not_run"));
    printf("tree_compare=%s\n", artifact_ok ? "yes" : (strcmp(g_error, "tree_mismatch") == 0 ? "no" : "not_run"));
    printf("parent_cdhash_distinct=%s\n", artifact_ok ? "yes" : (strcmp(g_error, "cdhash_not_distinct") == 0 ? "no" : "not_run"));
    if (g_sha1[0] != '\0' && artifact_ok) {
        printf("leaf_sha1=%s\n", g_sha1);
        printf("leaf_sha256=%s\n", g_sha256);
    } else {
        printf("leaf_sha1=not_run\n");
        printf("leaf_sha256=not_run\n");
    }
    if (artifact_ok) {
        printf("check_helper_exit=0\n");
        printf("check_helper_result=ok\n");
        printf("direct_lookup_exit=1\n");
        printf("direct_lookup_result=missing_key\n");
        printf("direct_lookup_calls=1\n");
        printf("direct_lookup_bracket=yes\n");
    } else {
        if (g_check_exit >= 0 && g_check_exit < 1000) {
            printf("check_helper_exit=%d\n", g_check_exit);
            printf("check_helper_result=mismatch\n");
        } else {
            printf("check_helper_exit=not_run\n");
            printf("check_helper_result=not_run\n");
        }
        if (g_lookup_exit >= 0 && g_lookup_exit < 1000) {
            printf("direct_lookup_exit=%d\n", g_lookup_exit);
            printf("direct_lookup_result=mismatch\n");
            printf("direct_lookup_calls=mismatch\n");
            printf("direct_lookup_bracket=no\n");
        } else {
            printf("direct_lookup_exit=not_run\n");
            printf("direct_lookup_result=not_run\n");
            printf("direct_lookup_calls=not_run\n");
            printf("direct_lookup_bracket=not_run\n");
        }
    }
    printf("search_list_equal=%s\n", g_search_equal);
    printf("default_equal=%s\n", g_default_equal);
    printf("basename_contract=%s\n", g_basename_contract);
    printf("deadline_disposition=%s\n", deadline);
    printf("settlement=%s\n", cleanup_ok && !g_report_uncertain ? "complete" : "incomplete");
    printf("cleanup=%s\n", cleanup_ok ? "complete" : "incomplete");
    printf("custody=%s\n", cleanup_ok ? "none" : "retained");
    printf("kernel_stuck_reaped=0\n");
    printf("xpc_exercised=no\n");
    printf("item_seeded=no\n");
    printf("trust_settings_changed=not_called\n");
    printf("compile_only_pins_used=no\n");
    printf("coverage_artifact_verify=%s\n", artifact_ok ? "yes" : "no");
    printf("coverage_empty_lookup=%s\n", lookup_ok ? "yes" : "no");
    printf("coverage_xpc=no\n");
    printf("coverage_acl_retention=no\n");
    printf("coverage_migration=no\n");
    printf("coverage_electron=no\n");
    printf("coverage_publisher_signing=no\n");
    printf("coverage_notarization=no\n");
    printf("error_category=%s\n", g_error);
    printf("success_command_count=%d\n", REAL_SUCCESS_COMMANDS);
    printf("spawn_count=%d\n", g_spawns);
    printf("spawn_cap=%d\n", REAL_SPAWN_CAP);
    printf("record_bound=%d\n", REAL_RECORD_BOUND);
    printf("stage_budget_ms=%ld\n", REAL_STAGE_MS);
    printf("child_budget_ms=%ld\n", REAL_CHILD_MS);
    printf("cleanup_grace_ms=%ld\n", REAL_CLEANUP_GRACE_MS);
    printf("deadline_does_not_prove_stuck_kernel_reaped=1\n");
}

static int parse_u64(const char **cursor, unsigned long long *out) {
    const char *text = *cursor;
    unsigned long long value = 0;
    int digits = 0;
    if (*text == ' ') {
        text++;
    }
    while (*text >= '0' && *text <= '9') {
        if (digits >= 20) {
            return -1;
        }
        value = value * 10ULL + (unsigned long long)(*text - '0');
        text++;
        digits++;
    }
    if (digits == 0) {
        return -1;
    }
    *out = value;
    *cursor = text;
    return 0;
}

static int sup_add_slot(struct sup_state *state, pid_t leader, pid_t pgid) {
    int index;
    if (leader <= 1 || pgid <= 1 || pgid == getpid() || pgid == getpgrp()) {
        return -1;
    }
    for (index = 0; index < REAL_RECORD_BOUND; index++) {
        if (state->slots[index].retired && state->slots[index].pgid == pgid) {
            state->slots[index].live = 1;
            return 0;
        }
    }
    for (index = 0; index < REAL_RECORD_BOUND; index++) {
        if (state->slots[index].live && state->slots[index].pgid == pgid) {
            return 0;
        }
    }
    for (index = 0; index < REAL_RECORD_BOUND; index++) {
        if (!state->slots[index].live && !state->slots[index].retired) {
            state->slots[index].live = 1;
            state->slots[index].retired = 0;
            state->slots[index].leader = leader;
            state->slots[index].pgid = pgid;
            return 0;
        }
    }
    return -1;
}

static void sup_retire_slot(struct sup_state *state, pid_t pgid) {
    int index;
    int occupied;
    int found = 0;
    if (pgid <= 1 || pgid == getpid() || pgid == getpgrp()) {
        state->stream_uncertain = 1;
        return;
    }
    occupied = group_occupied(pgid);
    for (index = 0; index < REAL_RECORD_BOUND; index++) {
        if (state->slots[index].pgid == pgid && (state->slots[index].live || state->slots[index].retired)) {
            state->slots[index].retired = 1;
            found = 1;
            if (occupied == 0) {
                state->slots[index].live = 0;
            }
        }
    }
    if (found) {
        return;
    }
    for (index = 0; index < REAL_RECORD_BOUND; index++) {
        if (!state->slots[index].live && !state->slots[index].retired) {
            state->slots[index].retired = 1;
            state->slots[index].leader = pgid;
            state->slots[index].pgid = pgid;
            state->slots[index].live = occupied == 0 ? 0 : 1;
            return;
        }
    }
    state->stream_uncertain = 1;
}

static int sup_add_dir(struct sup_state *state, unsigned long long dev, unsigned long long ino) {
    int index;
    for (index = 0; index < MAX_SUPER_DIRS; index++) {
        if (state->dirs[index].live && state->dirs[index].dev == dev && state->dirs[index].ino == ino) {
            return 0;
        }
    }
    for (index = 0; index < MAX_SUPER_DIRS; index++) {
        if (!state->dirs[index].live) {
            state->dirs[index].live = 1;
            state->dirs[index].dev = dev;
            state->dirs[index].ino = ino;
            return 0;
        }
    }
    return -1;
}

static void sup_clear_dir(struct sup_state *state, unsigned long long dev, unsigned long long ino) {
    int index;
    for (index = 0; index < MAX_SUPER_DIRS; index++) {
        if (state->dirs[index].live && state->dirs[index].dev == dev && state->dirs[index].ino == ino) {
            state->dirs[index].live = 0;
        }
    }
}

static int sup_parse(struct sup_state *state, const char *line) {
    const char *cursor;
    unsigned long long first;
    unsigned long long second;
    if (strcmp(line, "P") == 0) {
        state->phase = 1;
        return 0;
    }
    if (line[0] == 'X' && line[1] == ' ') {
        cursor = line + 2;
        if (parse_u64(&cursor, &first) != 0 || *cursor != '\0' || first > 0x7fffffffULL) {
            return -1;
        }
        sup_retire_slot(state, (pid_t)first);
        return 0;
    }
    if (line[0] == 'C' && line[1] == ' ') {
        const char *kind;
        cursor = line + 2;
        if (parse_u64(&cursor, &first) != 0 || parse_u64(&cursor, &second) != 0 || *cursor != ' ') {
            return -1;
        }
        kind = cursor + 1;
        if (!token_ok(kind, strlen(kind), 15) || first > 0x7fffffffULL || second > 0x7fffffffULL) {
            return -1;
        }
        return sup_add_slot(state, (pid_t)second, (pid_t)first);
    }
    if (line[0] == 'R' && line[1] == ' ') {
        const char *name;
        cursor = line + 2;
        if (parse_u64(&cursor, &first) != 0 || parse_u64(&cursor, &second) != 0 || *cursor != ' ') {
            return -1;
        }
        name = cursor + 1;
        if (!token_ok(name, strlen(name), 23)) {
            return -1;
        }
        return sup_add_dir(state, first, second);
    }
    if (line[0] == 'Y' && line[1] == ' ') {
        cursor = line + 2;
        if (parse_u64(&cursor, &first) != 0 || parse_u64(&cursor, &second) != 0 || *cursor != '\0') {
            return -1;
        }
        sup_clear_dir(state, first, second);
        return 0;
    }
    return -1;
}

static void sup_consume(struct sup_state *state, int record_fd) {
    char buffer[256];
    ssize_t count;
    if (record_fd < 0 || state->stream_uncertain) {
        return;
    }
    while ((count = read(record_fd, buffer, sizeof buffer)) > 0) {
        ssize_t index;
        for (index = 0; index < count; index++) {
            char character = buffer[index];
            if (character == '\n') {
                state->line[state->line_len] = '\0';
                if (state->line_len > 0 && sup_parse(state, state->line) != 0) {
                    state->stream_uncertain = 1;
                }
                state->line_len = 0;
                continue;
            }
            if (state->line_len + 1 >= sizeof state->line) {
                state->stream_uncertain = 1;
                state->line_len = 0;
                continue;
            }
            state->line[state->line_len++] = character;
        }
    }
    if (count == 0 && state->line_len > 0) {
        state->stream_uncertain = 1;
    }
    if (count < 0 && errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) {
        state->stream_uncertain = 1;
    }
}

static void sup_signal(struct sup_state *state, int sig) {
    int index;
    for (index = 0; index < REAL_RECORD_BOUND; index++) {
        pid_t pgid;
        if (!state->slots[index].live || state->slots[index].retired) {
            continue;
        }
        pgid = state->slots[index].pgid;
        if (pgid <= 1 || pgid == getpid() || pgid == getpgrp()) {
            continue;
        }
        kill(-pgid, sig);
    }
}

static int sup_unresolved(struct sup_state *state) {
    int index;
    int open = 0;
    if (state->stream_uncertain) {
        return 1;
    }
    for (index = 0; index < REAL_RECORD_BOUND; index++) {
        int occupied;
        if (!state->slots[index].live) {
            continue;
        }
        occupied = group_occupied(state->slots[index].pgid);
        if (occupied == 0) {
            state->slots[index].live = 0;
            continue;
        }
        open = 1;
    }
    for (index = 0; index < MAX_SUPER_DIRS; index++) {
        if (state->dirs[index].live) {
            open = 1;
        }
    }
    return open;
}

static void note_collected(struct sup_result *result, int status) {
    result->decision_reaped = 1;
    if (WIFEXITED(status)) {
        result->owner_exit = WEXITSTATUS(status);
        result->owner_signaled = 0;
    } else {
        result->owner_signaled = 1;
        result->owner_exit = -1;
    }
}

static int hygiene_collect(pid_t pid) {
    long start = mono_ms();
    int status = 0;
    if (pid <= 1 || start < 0) {
        return 0;
    }
    while (mono_ms() - start < REAL_HYGIENE_MS) {
        pid_t got = waitpid(pid, &status, WNOHANG);
        if (got == pid) {
            return 1;
        }
        if (got < 0 && errno == EINTR) {
            continue;
        }
        if (got < 0) {
            return 0;
        }
        nanosleep(&(struct timespec){0, 20000000L}, NULL);
    }
    return 0;
}

static void note_hygiene(struct sup_result *result, pid_t pid) {
    int occupied;
    result->hygiene_collected = hygiene_collect(pid);
    occupied = group_occupied(pid);
    result->hygiene_group_empty = occupied == 0 ? 1 : 0;
}

static int spawn_supervisor_child(char *const argv[], int record_write, pid_t *pid) {
    posix_spawn_file_actions_t actions;
    posix_spawnattr_t attr;
    pid_t child = -1;
    int rc;
    if (posix_spawnattr_init(&attr) != 0) {
        return -1;
    }
    if (posix_spawnattr_setflags(&attr, POSIX_SPAWN_SETPGROUP) != 0 || posix_spawnattr_setpgroup(&attr, 0) != 0 ||
        posix_spawn_file_actions_init(&actions) != 0) {
        posix_spawnattr_destroy(&attr);
        return -1;
    }
    if (record_write >= 0 && posix_spawn_file_actions_adddup2(&actions, record_write, 3) != 0) {
        posix_spawn_file_actions_destroy(&actions);
        posix_spawnattr_destroy(&attr);
        return -1;
    }
    rc = posix_spawnp(&child, argv[0], &actions, &attr, argv, environ);
    posix_spawn_file_actions_destroy(&actions);
    posix_spawnattr_destroy(&attr);
    if (rc != 0 || child <= 1) {
        return -1;
    }
    *pid = child;
    return 0;
}

static void supervise_child(pid_t pid, int record_fd, long start_ms, long normal_ms, long grace_ms, struct sup_result *result) {
    struct sup_state state;
    long normal_end;
    long grace_end = 0;
    int grace_on = 0;
    memset(&state, 0, sizeof state);
    result->owner_exit = -1;
    if (start_ms < 0 || sup_add_slot(&state, pid, pid) != 0) {
        result->unresolved = 1;
        result->decision_reaped = 0;
        if (pid > 1 && pid != getpid() && pid != getpgrp()) {
            kill(-pid, SIGKILL);
        }
        note_hygiene(result, pid);
        return;
    }
    normal_end = start_ms + normal_ms;
    while (1) {
        struct pollfd polls[2];
        int nfds = 0;
        int status = 0;
        int slice;
        long now = mono_ms();
        long active;
        pid_t got;
        if (now < 0) {
            result->timed_out = 1;
            result->unresolved = 1;
            result->decision_reaped = 0;
            sup_signal(&state, SIGKILL);
            note_hygiene(result, pid);
            break;
        }
        sup_consume(&state, record_fd);
        got = waitpid(pid, &status, WNOHANG);
        if (got == pid) {
            note_collected(result, status);
            sup_consume(&state, record_fd);
            break;
        }
        if (got < 0 && errno == EINTR) {
            continue;
        }
        if (got < 0) {
            result->decision_reaped = 0;
            result->unresolved = 1;
            sup_signal(&state, SIGKILL);
            note_hygiene(result, pid);
            break;
        }
        if (!grace_on && (state.phase || g_stop || now >= normal_end)) {
            if (g_stop || now >= normal_end) {
                sup_signal(&state, SIGTERM);
            }
            grace_on = 1;
            now = mono_ms();
            grace_end = now < 0 ? 0 : now + grace_ms;
            if (g_stop) {
                result->cancelled = 1;
            }
        }
        now = mono_ms();
        active = grace_on ? grace_end : normal_end;
        if (grace_on && (now < 0 || now >= grace_end)) {
            got = waitpid(pid, &status, WNOHANG);
            if (got == pid) {
                note_collected(result, status);
            } else {
                result->decision_reaped = 0;
            }
            result->timed_out = 1;
            result->unresolved = 1;
            sup_signal(&state, SIGKILL);
            note_hygiene(result, pid);
            break;
        }
        slice = 200;
        if (now >= 0 && active - now < slice) {
            slice = (int)(active - now);
        }
        if (slice < 0) {
            slice = 0;
        }
        if (record_fd >= 0) {
            polls[nfds].fd = record_fd;
            polls[nfds].events = POLLIN;
            nfds++;
        }
        if (g_wake[0] >= 0) {
            polls[nfds].fd = g_wake[0];
            polls[nfds].events = POLLIN;
            nfds++;
        }
        if (poll(nfds > 0 ? polls : NULL, (nfds_t)nfds, slice) < 0 && errno != EINTR) {
            result->stream_uncertain = 1;
            result->unresolved = 1;
            break;
        }
        drain_wake();
    }
    if (!result->timed_out) {
        result->unresolved = sup_unresolved(&state) || state.stream_uncertain;
    }
    result->stream_uncertain = state.stream_uncertain;
    if (result->stream_uncertain) {
        result->unresolved = 1;
    }
}

static int stall_child_main(void) {
    signal(SIGTERM, SIG_IGN);
    signal(SIGINT, SIG_IGN);
    signal(SIGHUP, SIG_IGN);
    signal(SIGPIPE, SIG_IGN);
    for (;;) {
        pause();
    }
    return 0;
}

static int case_supervisor_stall(const char *exe, const char *arch) {
    char *argv[3];
    struct sup_result result;
    int pipes[2];
    long start;
    pid_t pid = -1;
    int deadline_ok;
    int settled;
    argv[0] = (char *)exe;
    argv[1] = "--stall-child";
    argv[2] = NULL;
    memset(&result, 0, sizeof result);
    if (pipe(pipes) != 0) {
        return 1;
    }
    set_nonblock_cloexec(pipes[0]);
    fcntl(pipes[1], F_SETFD, FD_CLOEXEC);
    if (spawn_supervisor_child(argv, pipes[1], &pid) != 0) {
        close(pipes[0]);
        close(pipes[1]);
        return 1;
    }
    close(pipes[1]);
    start = mono_ms();
    supervise_child(pid, pipes[0], start, REAL_STALL_NORMAL_MS, REAL_STALL_GRACE_MS, &result);
    close(pipes[0]);
    deadline_ok = result.timed_out && !result.decision_reaped && result.unresolved;
    settled = result.hygiene_collected && result.hygiene_group_empty;
    printf("case=supervisor-stall arch=%s source=na step=finite result=%s native_security_calls=not_this_step "
           "cleanup=incomplete verdict=%s evidence=supervisor deadline_does_not_prove_stuck_kernel_reaped=1 "
           "kernel_stuck_reaped=0 custody=retained decision_reaped=%d hygiene_collected=%d hygiene_group_empty=%d "
           "native_operations=real\n",
           arch, deadline_ok ? "incomplete" : "wrong", deadline_ok && settled ? "pass" : "test_failure", result.decision_reaped,
           result.hygiene_collected, result.hygiene_group_empty);
    if (!deadline_ok) {
        return 1;
    }
    if (!settled) {
        return 2;
    }
    return 0;
}

static int finish_supervisor(const char *arch, const struct sup_result *result) {
    const char *reap = "not_reaped";
    const char *cleanup = "complete";
    const char *verdict = "pass";
    const char *custody = "none";
    const char *child_exit = "na";
    char exit_text[16];
    int code = 0;
    int incomplete = !result->decision_reaped || result->timed_out || result->unresolved || result->stream_uncertain;
    if (result->decision_reaped && !result->owner_signaled) {
        reap = "exited";
    } else if (result->decision_reaped && result->owner_signaled) {
        reap = "signaled";
    }
    if (result->owner_exit >= 0) {
        snprintf(exit_text, sizeof exit_text, "%d", result->owner_exit);
        child_exit = exit_text;
    }
    if (incomplete || result->owner_exit == 2 || result->owner_signaled) {
        cleanup = "incomplete";
        custody = "retained";
        verdict = "incomplete_cleanup";
        code = 2;
    } else if (result->owner_exit == 1) {
        verdict = "test_failure";
        code = 1;
    } else if (result->owner_exit == 4) {
        verdict = "test_failure";
        code = 4;
    } else if (result->cancelled || result->owner_exit == 3) {
        verdict = "cancelled";
        code = 3;
    } else if (result->owner_exit != 0) {
        cleanup = "incomplete";
        custody = "retained";
        verdict = "incomplete_cleanup";
        code = 2;
    }
    printf("case=supervisor arch=%s source=na step=settle result=%s native_security_calls=unavailable child_exit=%s "
           "child_reap=%s cleanup=%s verdict=%s evidence=supervisor deadline_does_not_prove_stuck_kernel_reaped=1 "
           "kernel_stuck_reaped=0 custody=%s decision_reaped=%d native_operations=real\n",
           arch, cleanup, child_exit, reap, cleanup, verdict, custody, result->decision_reaped);
    return code;
}

static int supervisor_main(const char *exe, const char *arch, const char *parent) {
    char *argv[5];
    struct sup_result result;
    int record[2];
    long start;
    pid_t pid = -1;
    int stall_code;
    if (pipe(g_wake) != 0) {
        return 1;
    }
    set_nonblock_cloexec(g_wake[0]);
    set_nonblock_cloexec(g_wake[1]);
    arm_signals();
    stall_code = case_supervisor_stall(exe, arch);
    if (stall_code != 0) {
        return stall_code;
    }
    if (g_stop) {
        return 3;
    }
    start = mono_ms();
    if (start < 0 || pipe(record) != 0) {
        return 1;
    }
    set_nonblock_cloexec(record[0]);
    fcntl(record[1], F_SETFD, FD_CLOEXEC);
    argv[0] = (char *)exe;
    argv[1] = "--owner";
    argv[2] = (char *)arch;
    argv[3] = (char *)parent;
    argv[4] = NULL;
    if (spawn_supervisor_child(argv, record[1], &pid) != 0) {
        close(record[0]);
        close(record[1]);
        return 1;
    }
    close(record[1]);
    memset(&result, 0, sizeof result);
    supervise_child(pid, record[0], start, REAL_STAGE_MS, REAL_CLEANUP_GRACE_MS, &result);
    close(record[0]);
    return finish_supervisor(arch, &result);
}

static int owner_main(const char *arch, const char *parent) {
    long start = mono_ms();
    int cleanup_ok;
    int exit_code;
    g_run.fd = -1;
    if (arch == NULL || parent == NULL || (strcmp(arch, "arm64") != 0 && strcmp(arch, "x86_64") != 0)) {
        return 4;
    }
    if (start < 0) {
        return 1;
    }
    g_deadline = start + REAL_STAGE_MS;
    snprintf(g_arch, sizeof g_arch, "%s", arch);
    if (pipe(g_wake) != 0) {
        return 1;
    }
    set_nonblock_cloexec(g_wake[0]);
    set_nonblock_cloexec(g_wake[1]);
    arm_signals();
    umask(077);
    if (walk_parent(parent) != 0) {
        fail("path_rejected");
        print_receipt(1);
        return 4;
    }
    if (make_run() != 0) {
        fail("path_rejected");
    } else if (stage() != 0) {
        g_case_failure = 1;
    } else if (maybe_delete() != 0) {
        g_case_failure = 1;
    } else {
        g_deleted = 1;
    }
    if (g_stop || remaining_run() == 0) {
        g_cancelled = 1;
        if (strcmp(g_error, "none") == 0) {
            fail("cancelled");
        }
    }
    cleanup_ok = cleanup_runs() == 0;
    print_receipt(cleanup_ok);
    if (!cleanup_ok) {
        exit_code = 2;
    } else if (g_case_failure) {
        exit_code = 1;
    } else if (g_cancelled) {
        exit_code = 3;
    } else {
        exit_code = 0;
    }
    if (g_parent_fd >= 0) {
        close(g_parent_fd);
    }
    return exit_code;
}

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--stall-child") == 0) {
        return stall_child_main();
    }
    if (argc == 4 && strcmp(argv[1], "--owner") == 0) {
        if (fcntl(3, F_GETFL) < 0) {
            return 1;
        }
        set_nonblock_cloexec(3);
        g_record_fd = 3;
        return owner_main(argv[2], argv[3]);
    }
    if (argc == 3 && (strcmp(argv[1], "arm64") == 0 || strcmp(argv[1], "x86_64") == 0)) {
        return supervisor_main(argv[0], argv[1], argv[2]);
    }
    fprintf(stderr, "usage: real-store-owner arm64|x86_64 absolute-private-parent\n");
    return 4;
}
