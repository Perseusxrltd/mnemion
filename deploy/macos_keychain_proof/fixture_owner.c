/* External disposable owner for the injected Keychain fixture.
   The public process is a supervisor. It does not open, unlink, or fsync the
   fixture tree. It spawns the owner, which is the process that can block in
   that I/O. A 60s monotonic budget covers the owner's setup, worker build,
   and cases. Each child wait is at most 10s and does not move that deadline.
   Cleanup has a separate grace of 10s. A deadline, a signal, or a supervisor
   return does not prove that a stuck kernel operation was reaped. This
   program reports decision_reaped only when waitpid collected that process,
   and kernel_stuck_reaped stays 0. The store file written here is not a
   Keychain. Process groups are the ids posix_spawn created. They are not
   looked up again with getpgid. */

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

enum {
    RUN_LIMIT_MS = 60000,
    CHILD_WAIT_MS = 10000,
    CLEANUP_GRACE_MS = 10000,
    STALL_NORMAL_MS = 400,
    STALL_GRACE_MS = 200,
    HYGIENE_MS = 100,
    MAX_RUNS = 5,
    MAX_CHILDREN = 8,
    MAX_SUPER_DIRS = 8,
    /* Permanent history of reported groups, not a concurrent-child cap.
       The existing successful sequence needs 38 entries. Fixed capacity is
       64. Overflow stays fail-closed. Retired numbers stay ineligible for
       signals and are not recycled. */
    MAX_SUPER_SLOTS = 64
};

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
static int g_symbols = 0;
static char g_custody_id[9];
static int g_record_fd = -1;
static int g_report_uncertain = 0;
static int g_cleanup_uncertain = 0;

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

struct paused_child {
    pid_t pid;
    int hold_fd;
    int out_fd;
};

static struct run_slot g_runs[MAX_RUNS];
static struct run_slot g_hold;
static struct child_slot g_children[MAX_CHILDREN];

static const char *k_forbidden[] = {"SecItemAdd",
                                    "SecItemCopyMatching",
                                    "SecItemUpdate",
                                    "SecItemDelete",
                                    "SecKeychainOpen",
                                    "SecKeychainCreate",
                                    "SecKeychainGetPath",
                                    "SecKeychainItemCopyKeychain",
                                    "SecKeychainItemGetTypeID",
                                    "SecKeychainGetUserInteractionAllowed",
                                    "SecKeychainSetUserInteractionAllowed",
                                    "SecKeychainSetSearchList",
                                    "SecKeychainCopySearchList",
                                    "SecKeychainCopyDefault",
                                    "SecKeychainSetDefault",
                                    "SecRandomCopyBytes",
                                    "SecKeychainUnlock",
                                    "SecAccessCreate",
                                    NULL};

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
    if (left > CHILD_WAIT_MS) {
        return CHILD_WAIT_MS;
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

/* kill(pgid, 0) asks whether this retained group currently has a member.
   It is not waitpid and it is not proof a stuck kernel operation ended.
   ESRCH means this probe saw nobody. A later occupant of the same number
   is a different identity and is never signaled. */
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
    if (pid <= 1 || pid == getpid() || pid == getpgrp()) {
        return -1;
    }
    for (index = 0; index < MAX_CHILDREN; index++) {
        if (!g_children[index].live) {
            g_children[index].live = 1;
            g_children[index].leader_reaped = 0;
            g_children[index].pid = pid;
            /* POSIX_SPAWN_SETPGROUP with pgroup 0 makes the new group id the child pid. */
            g_children[index].pgid = pid;
            snprintf(g_children[index].kind, sizeof g_children[index].kind, "%s", kind);
            report_child(pid, pid, kind);
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

static int cleanup_complete_allowed(void) {
    int index;
    for (index = 0; index < MAX_CHILDREN; index++) {
        if (g_children[index].live) {
            return 0;
        }
    }
    return 1;
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

static int contains_text(const char *haystack, const char *needle) {
    return haystack != NULL && needle != NULL && needle[0] != '\0' && strstr(haystack, needle) != NULL;
}

static int public_text_ok(const char *text) {
    size_t index;
    if (text == NULL) {
        return 0;
    }
    if (contains_text(text, g_parent) || contains_text(text, "fixture-synthetic") || contains_text(text, "power") ||
        contains_text(text, "BEGIN PRIVATE") || contains_text(text, "login.keychain")) {
        return 0;
    }
    for (index = 0; text[index] != '\0'; index++) {
        unsigned char character = (unsigned char)text[index];
        if (character < 32 && character != '\n' && character != '\t') {
            return 0;
        }
        if (character == '/' || character == '\\' || character == '"' || character == '\'') {
            return 0;
        }
    }
    for (index = 0; index < MAX_RUNS; index++) {
        if (g_runs[index].live && g_runs[index].nonce[0] != '\0' && contains_text(text, g_runs[index].nonce)) {
            return 0;
        }
        if (g_runs[index].live && contains_text(text, g_runs[index].path)) {
            return 0;
        }
    }
    return 1;
}

static void emit_safe(const char *line) {
    if (!public_text_ok(line)) {
        printf("case=redacted arch=%s source=%s step=receipt result=rejected native_security_calls=0 "
               "forbidden_native_calls=0 unconfigured=0 data_ops=0 marker=unknown publication=unknown child_exit=na "
               "child_reap=na cleanup=pending verdict=test_failure evidence=owner\n",
               g_arch, g_source[0] != '\0' ? g_source : "unreadable");
        g_case_failure = 1;
        return;
    }
    fputs(line, stdout);
    if (line[0] == '\0' || line[strlen(line) - 1] != '\n') {
        fputc('\n', stdout);
    }
}

static int path_prefix(const char *prefix, const char *path) {
    size_t length = strlen(prefix);
    if (length == 0 || strncmp(prefix, path, length) != 0) {
        return 0;
    }
    return path[length] == '\0' || path[length] == '/';
}

static int rejected_root(const char *path) {
    return path_prefix("/tmp", path) || path_prefix("/var", path) || path_prefix("/private/tmp", path) ||
           path_prefix("/private/var", path) || contains_text(path, "/Library/Keychains") ||
           contains_text(path, "login.keychain");
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
    if (strstr(path, "//") != NULL || strchr(path, '\\') != NULL || strchr(path, '"') != NULL) {
        return -1;
    }
    if (rejected_root(path)) {
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

static int create_file(int dirfd, const char *name, const char *body, struct stat *out) {
    int fd = openat(dirfd, name, O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    struct stat st;
    if (fd < 0 || fchmod(fd, 0600) != 0) {
        if (fd >= 0) {
            close(fd);
        }
        return -1;
    }
    if (body != NULL && write_all_fd(fd, body, strlen(body)) != 0) {
        close(fd);
        return -1;
    }
    if (fsync(fd) != 0 || fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || (st.st_mode & 07777) != 0600) {
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

static int make_run(struct run_slot *run) {
    unsigned char raw[8];
    unsigned char nonce_raw[16];
    unsigned char id_raw[4];
    struct stat st;
    struct stat store_st;
    char record[512];
    char header[2048];
    char service[96];
    char account[96];
    int include_fd;
    int header_fd;
    int written;
    if (random_bytes(raw, sizeof raw) != 0 || random_bytes(nonce_raw, sizeof nonce_raw) != 0 ||
        random_bytes(id_raw, sizeof id_raw) != 0) {
        return -1;
    }
    run->name[0] = 'f';
    hex_encode(raw, sizeof raw, run->name + 1);
    hex_encode(nonce_raw, sizeof nonce_raw, run->nonce);
    hex_encode(id_raw, sizeof id_raw, run->id);
    if (g_custody_id[0] == '\0') {
        snprintf(g_custody_id, sizeof g_custody_id, "%s", run->id);
    }
    if (mkdirat(g_parent_fd, run->name, 0700) != 0) {
        return -1;
    }
    run->fd = openat(g_parent_fd, run->name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (run->fd < 0 || fstat(run->fd, &st) != 0) {
        if (run->fd >= 0) {
            close(run->fd);
            run->fd = -1;
        }
        if (fstatat(g_parent_fd, run->name, &st, AT_SYMLINK_NOFOLLOW) == 0 && S_ISDIR(st.st_mode)) {
            run->dev = st.st_dev;
            run->ino = st.st_ino;
            run->live = 1;
            run->fd = -1;
            snprintf(run->path, sizeof run->path, "%s/%s", g_parent, run->name);
            report_run(run->dev, run->ino, run->name);
        }
        return -1;
    }
    run->dev = st.st_dev;
    run->ino = st.st_ino;
    run->live = 1;
    report_run(run->dev, run->ino, run->name);
    if (fchmod(run->fd, 0700) != 0 || fstat(run->fd, &st) != 0 || (st.st_mode & 07777) != 0700 ||
        st.st_dev != run->dev || st.st_ino != run->ino) {
        return -1;
    }
    written = snprintf(run->path, sizeof run->path, "%s/%s", g_parent, run->name);
    if (written < 0 || (size_t)written >= sizeof run->path || strlen(run->path) > 900) {
        return -1;
    }
    snprintf(service, sizeof service, "mnemion-disposable-service-%s", run->nonce);
    snprintf(account, sizeof account, "mnemion-disposable-account-%s", run->nonce);
    written = snprintf(record, sizeof record, "nonce=%s\nservice=%s\naccount=%s\n", run->nonce, service, account);
    if (written < 0 || (size_t)written >= sizeof record) {
        return -1;
    }
    if (create_file(run->fd, "throwaway.keychain", "not-a-keychain\n", &store_st) != 0 ||
        create_file(run->fd, "fixture-run.txt", record, NULL) != 0 || create_file(run->fd, "fixture.lock", "", NULL) != 0 ||
        create_dir(run->fd, "ciphertext") != 0 || create_dir(run->fd, "include") != 0) {
        return -1;
    }
    written = snprintf(header, sizeof header,
                       "#ifndef MNEMION_FIXTURE_STORE_CONFIG_H\n"
                       "#define MNEMION_FIXTURE_STORE_CONFIG_H\n"
                       "#define MNEMION_FIXTURE_STORE_CLASS \"fixture\"\n"
                       "#define MNEMION_FIXTURE_STORE_METADATA \"fixture: injected api boundary, not a keychain, not "
                       "native acceptance\"\n"
                       "#define MNEMION_FIXTURE_SERVICE_PREFIX \"mnemion-disposable-service-\"\n"
                       "#define MNEMION_FIXTURE_ACCOUNT_PREFIX \"mnemion-disposable-account-\"\n"
                       "#define MNEMION_FIXTURE_STORE_BASENAME \"throwaway.keychain\"\n"
                       "#define MNEMION_FIXTURE_RECORD_BASENAME \"fixture-run.txt\"\n"
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
                       run->path, run->nonce, (unsigned long long)geteuid(), (unsigned long long)run->dev,
                       (unsigned long long)run->ino, (unsigned long long)store_st.st_dev,
                       (unsigned long long)store_st.st_ino, service, account);
    if (written < 0 || (size_t)written >= sizeof header || contains_text(header, "compile_only") ||
        contains_text(header, "UNSUBSTITUTED") || contains_text(header, "ProtectedCloudStorage")) {
        return -1;
    }
    include_fd = openat(run->fd, "include", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (include_fd < 0) {
        return -1;
    }
    header_fd = openat(include_fd, "fixture_store_config.h", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (header_fd < 0 || fchmod(header_fd, 0600) != 0 || write_all_fd(header_fd, header, (size_t)written) != 0 ||
        fsync(header_fd) != 0) {
        if (header_fd >= 0) {
            close(header_fd);
        }
        close(include_fd);
        return -1;
    }
    close(header_fd);
    close(include_fd);
    if (fsync(run->fd) != 0) {
        return -1;
    }
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
        if (elapsed >= budget_ms || remaining_run() == 0) {
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

/* Success is the six-byte frame only. End of file is not required, and it is
   not success by itself: a live descendant may still hold another descriptor. */
static int read_ready_frame(int fd, long budget_ms) {
    char buffer[8];
    size_t filled = 0;
    long start = mono_ms();
    if (start < 0) {
        return -1;
    }
    while (filled < 6) {
        struct pollfd polls[2];
        long elapsed = mono_ms() - start;
        int wait_ms;
        int ready;
        ssize_t count;
        if (g_stop) {
            g_cancelled = 1;
            return -1;
        }
        if (elapsed < 0 || elapsed >= budget_ms || remaining_run() == 0) {
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
        count = read(fd, buffer + filled, 6 - filled);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count <= 0) {
            return -1;
        }
        filled += (size_t)count;
    }
    if (memcmp(buffer, "ready\n", 6) != 0) {
        return -1;
    }
    return 0;
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
            polls[0].fd = g_wake[0] >= 0 ? g_wake[0] : STDOUT_FILENO;
            polls[0].events = POLLIN;
            if (g_wake[0] < 0) {
                polls[0].fd = -1;
                nanosleep(&(struct timespec){0, 20000000L}, NULL);
            } else {
                int ready = poll(polls, 1, slice);
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
    /* The group id is the one recorded at posix_spawn. Do not call getpgid. */
    signal_retained(find_child(pid), sig);
}

static int spawn_recorded(char *const argv[], int stdin_fd, int stdout_fd, int ready_write, int hold_read, pid_t *pid) {
    posix_spawn_file_actions_t actions;
    posix_spawnattr_t attr;
    pid_t child = -1;
    int rc;
    int setup = 0;
    if (remaining_run() == 0 || g_stop) {
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
    if (stdout_fd >= 0 && (posix_spawn_file_actions_adddup2(&actions, stdout_fd, STDOUT_FILENO) != 0 ||
                           posix_spawn_file_actions_adddup2(&actions, stdout_fd, STDERR_FILENO) != 0)) {
        setup = -1;
    }
    if (ready_write >= 0 && posix_spawn_file_actions_adddup2(&actions, ready_write, 3) != 0) {
        setup = -1;
    }
    if (hold_read >= 0 && posix_spawn_file_actions_adddup2(&actions, hold_read, 4) != 0) {
        setup = -1;
    }
    rc = setup == 0 ? posix_spawnp(&child, argv[0], &actions, &attr, argv, environ) : -1;
    posix_spawn_file_actions_destroy(&actions);
    posix_spawnattr_destroy(&attr);
    if (rc != 0) {
        return -1;
    }
    *pid = child;
    if (note_child(child, "child") != 0) {
        int status = 0;
        long start = mono_ms();
        if (child > 1 && child != getpgrp()) {
            kill(-child, SIGKILL);
        }
        while (start >= 0 && mono_ms() - start < 1000) {
            pid_t got = waitpid(child, &status, WNOHANG);
            if (got == child || (got < 0 && errno != EINTR)) {
                break;
            }
            nanosleep(&(struct timespec){0, 20000000L}, NULL);
        }
        return -1;
    }
    return 0;
}

static int run_captured(char *const argv[], char *output, size_t cap, int *status, char *reap, size_t reap_cap) {
    int pipes[2];
    pid_t pid = -1;
    size_t length = 0;
    long budget;
    long start;
    int read_rc;
    int wait_rc;
    if (pipe(pipes) != 0) {
        return -1;
    }
    fcntl(pipes[0], F_SETFD, FD_CLOEXEC);
    fcntl(pipes[1], F_SETFD, FD_CLOEXEC);
    budget = child_budget();
    start = mono_ms();
    (void)start;
    if (spawn_recorded(argv, -1, pipes[1], -1, -1, &pid) != 0) {
        close(pipes[0]);
        close(pipes[1]);
        return -1;
    }
    close(pipes[1]);
    read_rc = read_budget(pipes[0], output, cap, &length, budget);
    close(pipes[0]);
    if (read_rc != 0) {
        signal_one(pid, SIGTERM);
        wait_rc = wait_budget(pid, status, reap, reap_cap, child_budget());
        if (wait_rc != 0) {
            snprintf(reap, reap_cap, "timeout");
        }
        return read_rc;
    }
    wait_rc = wait_budget(pid, status, reap, reap_cap, child_budget());
    return wait_rc == 0 ? 0 : wait_rc;
}

static int build_worker(struct run_slot *run) {
    char arch_define[64];
    char source_define[96];
    char include_dir[1100];
    char output_path[1100];
    char *argv[36];
    char output[1024];
    int status = 0;
    int log_fd;
    int index = 0;
    snprintf(arch_define, sizeof arch_define, "-DFIXTURE_ARCH=\"%s\"", g_arch);
    snprintf(source_define, sizeof source_define, "-DFIXTURE_SOURCE=\"%s\"", g_source);
    snprintf(include_dir, sizeof include_dir, "%s/include", run->path);
    snprintf(output_path, sizeof output_path, "%s/worker", run->path);
    argv[index++] = "clang";
    argv[index++] = "-arch";
    argv[index++] = g_arch;
    argv[index++] = "-mmacosx-version-min=13.0";
    argv[index++] = "-std=gnu11";
    argv[index++] = "-fno-objc-arc";
    argv[index++] = "-fblocks";
    argv[index++] = "-DOS_OBJECT_USE_OBJC=0";
    argv[index++] = "-DMNEMION_FIXTURE_INJECT=1";
    argv[index++] = arch_define;
    argv[index++] = source_define;
    argv[index++] = "-Werror";
    argv[index++] = "-Wall";
    argv[index++] = "-Wextra";
    argv[index++] = "-Werror=implicit-function-declaration";
    argv[index++] = "-I";
    argv[index++] = include_dir;
    argv[index++] = "-I";
    argv[index++] = "deploy/macos_keychain_proof";
    argv[index++] = "-o";
    argv[index++] = output_path;
    argv[index++] = "deploy/macos_keychain_proof/fixture_worker.c";
    argv[index++] = "deploy/macos_keychain_proof/fixture_inject.c";
    argv[index++] = "deploy/macos_keychain_proof/fixture_store.m";
    argv[index++] = "deploy/macos_keychain_proof/fixture_store_syntax.c";
    argv[index++] = "deploy/macos_keychain_proof/parent_direct_lookup.m";
    argv[index++] = "deploy/macos_keychain_proof/key_item.m";
    argv[index++] = "deploy/macos_keychain_proof/v10_crypt.c";
    argv[index++] = "-framework";
    argv[index++] = "CoreFoundation";
    argv[index++] = "-framework";
    argv[index++] = "Security";
    argv[index] = NULL;
    log_fd = openat(run->fd, "build-log", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (log_fd < 0) {
        return -1;
    }
    /* The compiler log stays inside the private run. It is not a receipt. */
    {
        pid_t pid = -1;
        long budget;
        char reap_local[16];
        budget = child_budget();
        if (spawn_recorded(argv, -1, log_fd, -1, -1, &pid) != 0) {
            close(log_fd);
            return -1;
        }
        close(log_fd);
        if (wait_budget(pid, &status, reap_local, sizeof reap_local, budget) != 0 || !WIFEXITED(status) ||
            WEXITSTATUS(status) != 0) {
            snprintf(output, sizeof output,
                     "case=build arch=%s source=%s step=compile result=failed native_security_calls=0 "
                     "forbidden_native_calls=0 unconfigured=0 data_ops=0 marker=na publication=na child_exit=na "
                     "child_reap=%s cleanup=pending verdict=test_failure evidence=owner run=%s\n",
                     g_arch, g_source, reap_local, run->id);
            emit_safe(output);
            return -1;
        }
    }
    return 0;
}

static int symbol_gate(struct run_slot *run) {
    char worker[1100];
    char *argv[4];
    char output[65536];
    char reap[16];
    char line[512];
    int status = 0;
    int count = 0;
    int index;
    snprintf(worker, sizeof worker, "%s/worker", run->path);
    argv[0] = "nm";
    argv[1] = "-g";
    argv[2] = worker;
    argv[3] = NULL;
    output[0] = '\0';
    if (run_captured(argv, output, sizeof output, &status, reap, sizeof reap) != 0 || !WIFEXITED(status) ||
        WEXITSTATUS(status) != 0) {
        snprintf(line, sizeof line,
                 "case=symbol-gate arch=%s source=%s step=nm result=failed native_security_calls=0 "
                 "forbidden_native_calls=0 unconfigured=0 data_ops=0 marker=na publication=na child_exit=na "
                 "child_reap=%s cleanup=pending verdict=test_failure evidence=owner run=%s\n",
                 g_arch, g_source, reap, run->id);
        emit_safe(line);
        return -1;
    }
    for (index = 0; k_forbidden[index] != NULL; index++) {
        if (strstr(output, k_forbidden[index]) != NULL) {
            count++;
        }
    }
    g_symbols += count;
    snprintf(line, sizeof line,
             "case=symbol-gate arch=%s source=%s step=nm result=%s native_security_calls=0 forbidden_native_calls=%d "
             "unconfigured=0 data_ops=0 marker=na publication=na child_exit=%d child_reap=%s cleanup=pending "
             "verdict=%s evidence=owner run=%s\n",
             g_arch, g_source, count == 0 ? "ok" : "refused", count, WEXITSTATUS(status), reap,
             count == 0 ? "pass" : "test_failure", run->id);
    emit_safe(line);
    return count == 0 ? 0 : -1;
}

static int verdict_ok(const char *line) {
    const char *mark = strstr(line, "verdict=");
    if (mark == NULL) {
        return 0;
    }
    mark += 8;
    return strncmp(mark, "pass", 4) == 0 || strncmp(mark, "expected_refusal", 16) == 0;
}

static int run_worker(struct run_slot *run, const char *case_name) {
    char worker[1100];
    char *argv[5];
    int out_pipe[2] = {-1, -1};
    int status = 0;
    char reap[16];
    char output[8192];
    char published[8700];
    size_t length = 0;
    pid_t pid = -1;
    long budget;
    int exit_code = 1;
    int failed = 0;
    snprintf(worker, sizeof worker, "%s/worker", run->path);
    argv[0] = worker;
    argv[1] = (char *)case_name;
    argv[2] = "-1";
    argv[3] = "-1";
    argv[4] = NULL;
    if (pipe(out_pipe) != 0) {
        return -1;
    }
    fcntl(out_pipe[0], F_SETFD, FD_CLOEXEC);
    fcntl(out_pipe[1], F_SETFD, FD_CLOEXEC);
    budget = child_budget();
    if (spawn_recorded(argv, -1, out_pipe[1], -1, -1, &pid) != 0) {
        close(out_pipe[0]);
        close(out_pipe[1]);
        return -1;
    }
    close(out_pipe[1]);
    if (read_budget(out_pipe[0], output, sizeof output, &length, budget) != 0) {
        close(out_pipe[0]);
        signal_one(pid, SIGTERM);
        g_case_failure = 1;
        snprintf(reap, sizeof reap, "timeout");
        snprintf(published, sizeof published,
                 "case=%s arch=%s source=%s step=%s result=timeout native_security_calls=0 forbidden_native_calls=0 "
                 "unconfigured=0 data_ops=0 marker=unknown publication=unknown child_exit=na child_reap=%s "
                 "cleanup=pending verdict=test_failure evidence=owner run=%s\n",
                 case_name, g_arch, g_source, case_name, reap, run->id);
        emit_safe(published);
        return -1;
    }
    close(out_pipe[0]);
    if (wait_budget(pid, &status, reap, sizeof reap, child_budget()) != 0) {
        signal_one(pid, SIGTERM);
        g_case_failure = 1;
        snprintf(published, sizeof published,
                 "case=%s arch=%s source=%s step=%s result=timeout native_security_calls=0 forbidden_native_calls=0 "
                 "unconfigured=0 data_ops=0 marker=unknown publication=unknown child_exit=na child_reap=%s "
                 "cleanup=pending verdict=test_failure evidence=owner run=%s\n",
                 case_name, g_arch, g_source, case_name, reap, run->id);
        emit_safe(published);
        return -1;
    }
    if (WIFEXITED(status)) {
        exit_code = WEXITSTATUS(status);
    }
    if (!public_text_ok(output) || length == 0 || output[length - 1] != '\n') {
        g_case_failure = 1;
        snprintf(published, sizeof published,
                 "case=%s arch=%s source=%s step=receipt result=rejected native_security_calls=0 "
                 "forbidden_native_calls=0 unconfigured=0 data_ops=0 marker=unknown publication=unknown child_exit=%d "
                 "child_reap=%s cleanup=pending verdict=test_failure evidence=owner run=%s\n",
                 case_name, g_arch, g_source, exit_code, reap, run->id);
        emit_safe(published);
        return -1;
    }
    output[length - 1] = '\0';
    if (!verdict_ok(output) || exit_code != 0) {
        failed = 1;
    }
    snprintf(published, sizeof published, "%s child_exit=%d child_reap=%s cleanup=pending run=%s\n", output, exit_code, reap,
             run->id);
    {
        int marked = g_case_failure;
        emit_safe(published);
        if (failed || g_case_failure != marked) {
            g_case_failure = 1;
            return -1;
        }
    }
    return 0;
}

static int finish_paused(pid_t pid, int hold_fd, int out_fd, const char *case_name, struct run_slot *run) {
    char output[8192];
    char published[8700];
    char reap[16];
    size_t length = 0;
    int status = 0;
    long budget = child_budget();
    int exit_code = 1;
    int failed = 0;
    close(hold_fd);
    if (read_budget(out_fd, output, sizeof output, &length, budget) != 0 ||
        wait_budget(pid, &status, reap, sizeof reap, child_budget()) != 0) {
        signal_one(pid, SIGTERM);
        g_case_failure = 1;
        snprintf(published, sizeof published,
                 "case=%s arch=%s source=%s step=%s result=timeout native_security_calls=0 forbidden_native_calls=0 "
                 "unconfigured=0 data_ops=0 marker=unknown publication=unknown child_exit=na child_reap=timeout "
                 "cleanup=pending verdict=test_failure evidence=lock_contention run=%s\n",
                 case_name, g_arch, g_source, case_name, run->id);
        emit_safe(published);
        close(out_fd);
        return -1;
    }
    close(out_fd);
    if (WIFEXITED(status)) {
        exit_code = WEXITSTATUS(status);
    }
    if (!public_text_ok(output) || length == 0) {
        g_case_failure = 1;
        return -1;
    }
    if (output[length - 1] == '\n') {
        output[length - 1] = '\0';
    }
    if (!verdict_ok(output) || exit_code != 0) {
        failed = 1;
    }
    snprintf(published, sizeof published, "%s child_exit=%d child_reap=%s cleanup=pending run=%s\n", output, exit_code, reap,
             run->id);
    {
        int marked = g_case_failure;
        emit_safe(published);
        if (failed || g_case_failure != marked) {
            g_case_failure = 1;
            return -1;
        }
    }
    return 0;
}

static const char *marker_of(int fd) {
    struct stat st;
    if (fstatat(fd, "creation-attempted", &st, AT_SYMLINK_NOFOLLOW) != 0) {
        return errno == ENOENT ? "absent" : "error";
    }
    if (!S_ISREG(st.st_mode) || S_ISLNK(st.st_mode)) {
        return "error";
    }
    return st.st_size < 64 ? "partial" : "present";
}

static int marker_ino(int fd, ino_t *ino) {
    struct stat st;
    if (fstatat(fd, "creation-attempted", &st, AT_SYMLINK_NOFOLLOW) != 0 || !S_ISREG(st.st_mode)) {
        return -1;
    }
    *ino = st.st_ino;
    return 0;
}

static int add_named_file(struct run_slot *run, const char *dir_name, const char *file_name, const char *body,
                          ino_t *ino) {
    int dirfd = openat(run->fd, dir_name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    struct stat st;
    int fd;
    if (dirfd < 0) {
        return -1;
    }
    fd = openat(dirfd, file_name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0 || fchmod(fd, 0600) != 0 || write_all_fd(fd, body, strlen(body)) != 0 || fsync(fd) != 0 ||
        fstat(fd, &st) != 0) {
        if (fd >= 0) {
            close(fd);
        }
        close(dirfd);
        return -1;
    }
    *ino = st.st_ino;
    close(fd);
    close(dirfd);
    return 0;
}

static int remove_named_file(struct run_slot *run, const char *dir_name, const char *file_name, ino_t ino) {
    int dirfd = openat(run->fd, dir_name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    struct stat st;
    if (dirfd < 0 || fstatat(dirfd, file_name, &st, AT_SYMLINK_NOFOLLOW) != 0 || !S_ISREG(st.st_mode) ||
        S_ISLNK(st.st_mode) || st.st_ino != ino || unlinkat(dirfd, file_name, 0) != 0) {
        if (dirfd >= 0) {
            close(dirfd);
        }
        return -1;
    }
    close(dirfd);
    return 0;
}

static int simple_cases(struct run_slot *run) {
    static const char *names[] = {"ui-prior-enabled",
                                  "ui-prior-disabled",
                                  "ui-fail-get",
                                  "ui-fail-disable",
                                  "ui-fail-readback",
                                  "ui-fail-readback-mismatch",
                                  "ui-fail-operation",
                                  "bind-foreign-path",
                                  "copy-foreign-store",
                                  "dispose-key-item",
                                  "dispose-parent",
                                  NULL};
    int index;
    for (index = 0; names[index] != NULL; index++) {
        if (g_stop || remaining_run() == 0) {
            g_cancelled = 1;
            return -1;
        }
        if (run_worker(run, names[index]) != 0) {
            return -1;
        }
    }
    return 0;
}

static void close_pair(int pair[2]) {
    if (pair[0] >= 0) {
        close(pair[0]);
    }
    if (pair[1] >= 0) {
        close(pair[1]);
    }
}

static void abort_paused(struct paused_child *child) {
    if (child->pid > 1) {
        signal_one(child->pid, SIGTERM);
    }
    if (child->hold_fd >= 0) {
        close(child->hold_fd);
        child->hold_fd = -1;
    }
    if (child->out_fd >= 0) {
        close(child->out_fd);
        child->out_fd = -1;
    }
}

static int spawn_paused(struct run_slot *run, const char *case_name, struct paused_child *out, char *ready,
                        size_t ready_cap) {
    int out_pipe[2] = {-1, -1};
    int ready_pipe[2] = {-1, -1};
    int hold_pipe[2] = {-1, -1};
    char worker[1100];
    char *argv[5];
    pid_t pid = -1;
    size_t ready_len = 0;
    out->pid = -1;
    out->hold_fd = -1;
    out->out_fd = -1;
    if (pipe(out_pipe) != 0) {
        return -1;
    }
    if (pipe(ready_pipe) != 0) {
        close_pair(out_pipe);
        return -1;
    }
    if (pipe(hold_pipe) != 0) {
        close_pair(out_pipe);
        close_pair(ready_pipe);
        return -1;
    }
    fcntl(out_pipe[0], F_SETFD, FD_CLOEXEC);
    fcntl(out_pipe[1], F_SETFD, FD_CLOEXEC);
    fcntl(ready_pipe[0], F_SETFD, FD_CLOEXEC);
    fcntl(ready_pipe[1], F_SETFD, FD_CLOEXEC);
    fcntl(hold_pipe[0], F_SETFD, FD_CLOEXEC);
    fcntl(hold_pipe[1], F_SETFD, FD_CLOEXEC);
    snprintf(worker, sizeof worker, "%s/worker", run->path);
    argv[0] = worker;
    argv[1] = (char *)case_name;
    argv[2] = "3";
    argv[3] = "4";
    argv[4] = NULL;
    if (spawn_recorded(argv, -1, out_pipe[1], ready_pipe[1], hold_pipe[0], &pid) != 0) {
        close_pair(out_pipe);
        close_pair(ready_pipe);
        close_pair(hold_pipe);
        return -1;
    }
    close(out_pipe[1]);
    close(ready_pipe[1]);
    close(hold_pipe[0]);
    if (read_budget(ready_pipe[0], ready, ready_cap, &ready_len, child_budget()) != 0) {
        close(ready_pipe[0]);
        close(hold_pipe[1]);
        close(out_pipe[0]);
        signal_one(pid, SIGTERM);
        g_case_failure = 1;
        return -1;
    }
    close(ready_pipe[0]);
    out->pid = pid;
    out->hold_fd = hold_pipe[1];
    out->out_fd = out_pipe[0];
    return 0;
}

static int lock_cases(struct run_slot *run) {
    struct paused_child hold;
    struct paused_child reuse;
    char ready[2048];
    if (spawn_paused(run, "lock-hold", &hold, ready, sizeof ready) != 0) {
        return -1;
    }
    if (!public_text_ok(ready) || strstr(ready, "lock_acquired") == NULL || strstr(ready, "sec_add") != NULL) {
        abort_paused(&hold);
        g_case_failure = 1;
        return -1;
    }
    if (run_worker(run, "lock-try") != 0) {
        abort_paused(&hold);
        return -1;
    }
    if (finish_paused(hold.pid, hold.hold_fd, hold.out_fd, "lock-hold", run) != 0) {
        return -1;
    }
    if (spawn_paused(run, "lock-reuse", &reuse, ready, sizeof ready) != 0) {
        return -1;
    }
    if (!public_text_ok(ready) || strstr(ready, "lock_acquired") == NULL || strstr(ready, "sec_add") != NULL) {
        abort_paused(&reuse);
        g_case_failure = 1;
        return -1;
    }
    return finish_paused(reuse.pid, reuse.hold_fd, reuse.out_fd, "lock-reuse", run);
}

static int cleanup_time_up(void) {
    long now;
    if (!g_grace_on) {
        return 0;
    }
    now = mono_ms();
    if (now < 0) {
        return 1;
    }
    return now >= g_grace_deadline;
}

static int identity_is(const struct stat *st, dev_t dev, ino_t ino, mode_t type) {
    return st->st_dev == dev && st->st_ino == ino && (st->st_mode & S_IFMT) == type && !S_ISLNK(st->st_mode);
}

/* A failed directory open is uncertainty. Do not unlink that name.
   Every opened directory must match the device, inode, and directory type
   recorded for it, and the name is checked again before it is removed.
   The check and unlinkat are not one kernel operation. */
static int remove_tree(int parent_fd, const char *name, dev_t expect_dev, ino_t expect_ino, int depth) {
    int fd;
    struct stat entry;
    struct stat st;
    struct stat again;
    DIR *dir;
    struct dirent *ent;
    if (cleanup_time_up() || depth > 6) {
        return -1;
    }
    if (fstatat(parent_fd, name, &entry, AT_SYMLINK_NOFOLLOW) != 0 ||
        !identity_is(&entry, expect_dev, expect_ino, S_IFDIR)) {
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
            if (child.st_dev != expect_dev ||
                remove_tree(dirfd(dir), ent->d_name, expect_dev, child.st_ino, depth + 1) != 0) {
                closedir(dir);
                return -1;
            }
        } else if (S_ISREG(child.st_mode) && !S_ISLNK(child.st_mode)) {
            if (fstatat(dirfd(dir), ent->d_name, &before_unlink, AT_SYMLINK_NOFOLLOW) != 0 ||
                !identity_is(&before_unlink, child.st_dev, child.st_ino, S_IFREG) ||
                unlinkat(dirfd(dir), ent->d_name, 0) != 0) {
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

static void begin_grace(void) {
    long now;
    if (!g_grace_on) {
        g_grace_on = 1;
        now = mono_ms();
        g_grace_deadline = now < 0 ? 0 : now + CLEANUP_GRACE_MS;
    }
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

/* After SIGKILL, watch the retained group for at most two seconds within
   the cleanup grace. Expiry leaves it unresolved; elapsed time is not a reap. */
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
    if (!cleanup_complete_allowed()) {
        unreaped = 1;
    }
    return unreaped;
}

static int write_custody(void) {
    char name[32];
    char body[4096];
    int fd;
    int written;
    int index;
    int offset;
    snprintf(name, sizeof name, "custody-%s", g_custody_id[0] != '\0' ? g_custody_id : "none");
    offset = snprintf(body, sizeof body, "cleanup=incomplete\nparent=%s\n", g_parent);
    if (offset < 0 || (size_t)offset >= sizeof body) {
        return -1;
    }
    for (index = 0; index < MAX_RUNS; index++) {
        int added;
        if (!g_runs[index].live) {
            continue;
        }
        added = snprintf(body + offset, sizeof body - (size_t)offset, "run_id=%s path=%s\n", g_runs[index].id,
                         g_runs[index].path);
        if (added < 0 || (size_t)added >= sizeof body - (size_t)offset) {
            return -1;
        }
        offset += added;
    }
    if (g_hold.live) {
        int added = snprintf(body + offset, sizeof body - (size_t)offset, "run_id=%s path=%s\n",
                             g_hold.id[0] != '\0' ? g_hold.id : "hold", g_hold.path);
        if (added < 0 || (size_t)added >= sizeof body - (size_t)offset) {
            return -1;
        }
        offset += added;
    }
    for (index = 0; index < MAX_CHILDREN; index++) {
        int added;
        if (!g_children[index].live) {
            continue;
        }
        added = snprintf(body + offset, sizeof body - (size_t)offset, "pid=%d pgid=%d leader_reaped=%d kind=%s\n",
                         (int)g_children[index].pid, (int)g_children[index].pgid, g_children[index].leader_reaped,
                         g_children[index].kind);
        if (added < 0 || (size_t)added >= sizeof body - (size_t)offset) {
            return -1;
        }
        offset += added;
    }
    written = offset;
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

static int release_run(struct run_slot *run) {
    struct stat held;
    struct stat name_st;
    dev_t dev;
    ino_t ino;
    if (run == NULL || !run->live) {
        return 0;
    }
    dev = run->dev;
    ino = run->ino;
    if (run->fd >= 0) {
        if (fstat(run->fd, &held) != 0 || !identity_is(&held, dev, ino, S_IFDIR)) {
            return -1;
        }
    }
    if (fstatat(g_parent_fd, run->name, &name_st, AT_SYMLINK_NOFOLLOW) != 0 ||
        !identity_is(&name_st, dev, ino, S_IFDIR)) {
        return -1;
    }
    if (remove_tree(g_parent_fd, run->name, dev, ino, 0) != 0) {
        return -1;
    }
    if (run->fd >= 0) {
        close(run->fd);
        run->fd = -1;
    }
    report_run_cleared(dev, ino);
    run->live = 0;
    return 0;
}

static int cleanup_runs(void) {
    int index;
    int failed = 0;
    struct stat parent_st;
    begin_grace();
    report_phase();
    if (stop_children() != 0 || g_report_uncertain || g_cleanup_uncertain) {
        write_custody();
        return -1;
    }
    if (g_parent_fd < 0 || fstat(g_parent_fd, &parent_st) != 0 || !identity_is(&parent_st, g_parent_dev, g_parent_ino, S_IFDIR)) {
        write_custody();
        return -1;
    }
    for (index = 0; index < MAX_RUNS; index++) {
        if (release_run(&g_runs[index]) != 0) {
            failed = 1;
        }
    }
    if (release_run(&g_hold) != 0) {
        failed = 1;
    }
    if (g_report_uncertain || g_cleanup_uncertain) {
        failed = 1;
    }
    if (failed) {
        write_custody();
        return -1;
    }
    return 0;
}

static int read_source(void) {
    char *git_argv[4];
    char output[128];
    char reap[16];
    int status = 0;
    size_t index;
    git_argv[0] = "git";
    git_argv[1] = "rev-parse";
    git_argv[2] = "HEAD";
    git_argv[3] = NULL;
    output[0] = '\0';
    if (run_captured(git_argv, output, sizeof output, &status, reap, sizeof reap) != 0 || !WIFEXITED(status) ||
        WEXITSTATUS(status) != 0) {
        return -1;
    }
    if (strlen(output) < 41 || output[40] != '\n') {
        return -1;
    }
    for (index = 0; index < 40; index++) {
        char character = output[index];
        if (!((character >= '0' && character <= '9') || (character >= 'a' && character <= 'f'))) {
            return -1;
        }
        g_source[index] = character;
    }
    g_source[40] = '\0';
    return 0;
}

static int prepare_slot(struct run_slot *run) {
    if (make_run(run) != 0 || build_worker(run) != 0 || symbol_gate(run) != 0) {
        g_case_failure = 1;
        return -1;
    }
    return 0;
}

static void summary(int cleanup_ok) {
    const char *verdict = "pass";
    const char *cleanup = cleanup_ok ? "complete" : "incomplete";
    if (!cleanup_ok) {
        verdict = "incomplete_cleanup";
    } else if (g_case_failure) {
        verdict = "test_failure";
    } else if (g_cancelled) {
        verdict = "cancelled";
    }
    printf("case=owner-summary arch=%s source=%s step=none order=none result=%s native_security_calls=0 "
           "forbidden_native_calls=%d unconfigured=0 data_ops=0 marker=na publication=na child_exit=na child_reap=na "
           "cleanup=%s verdict=%s evidence=owner deadline_does_not_prove_stuck_kernel_reaped=1 custody=%s "
           "store_file=not_a_keychain experiment=process_restart\n",
           g_arch, g_source[0] != '\0' ? g_source : "unreadable", verdict, g_symbols, cleanup, verdict,
           cleanup_ok ? "none" : "retained");
}

static int make_case_name(char prefix, char *name, size_t cap) {
    unsigned char raw[8];
    if (cap < 18 || random_bytes(raw, sizeof raw) != 0) {
        return -1;
    }
    name[0] = prefix;
    hex_encode(raw, sizeof raw, name + 1);
    return 0;
}

static void retain_hold(int fd, const char *name, const struct stat *st) {
    g_hold.live = 1;
    g_hold.fd = fd;
    g_hold.dev = st->st_dev;
    g_hold.ino = st->st_ino;
    snprintf(g_hold.name, sizeof g_hold.name, "%s", name);
    snprintf(g_hold.path, sizeof g_hold.path, "%s/%s", g_parent, name);
    snprintf(g_hold.id, sizeof g_hold.id, "holdcase");
    report_run(g_hold.dev, g_hold.ino, g_hold.name);
}

static int unlink_matching(int dirfd, const char *name, const struct stat *want, mode_t type) {
    struct stat now;
    if (fstatat(dirfd, name, &now, AT_SYMLINK_NOFOLLOW) != 0 || now.st_dev != want->st_dev || now.st_ino != want->st_ino) {
        return -1;
    }
    if (type == S_IFLNK) {
        if (!S_ISLNK(now.st_mode)) {
            return -1;
        }
    } else if (!identity_is(&now, want->st_dev, want->st_ino, type)) {
        return -1;
    }
    return unlinkat(dirfd, name, 0);
}

static int case_replaced_cleanup_entry(void) {
    char name[24];
    char side[24];
    char line[640];
    struct stat recorded;
    struct stat child_dir;
    struct stat replacement_dir;
    struct stat file_st;
    struct stat link_st;
    struct stat now;
    const char *owned_name = NULL;
    int fd = -1;
    int failed = 0;
    int have_record = 0;
    int have_file = 0;
    int have_link = 0;
    g_hold.live = 0;
    g_hold.fd = -1;
    memset(&recorded, 0, sizeof recorded);
    if (make_case_name('c', name, sizeof name) != 0 || make_case_name('s', side, sizeof side) != 0 ||
        mkdirat(g_parent_fd, name, 0700) != 0) {
        failed = 1;
        goto done;
    }
    owned_name = name;
    fd = openat(g_parent_fd, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0 || fstat(fd, &recorded) != 0 || !S_ISDIR(recorded.st_mode)) {
        failed = 1;
        goto done;
    }
    have_record = 1;
    if (mkdirat(fd, "sub", 0700) != 0 || fstatat(fd, "sub", &child_dir, AT_SYMLINK_NOFOLLOW) != 0 ||
        !S_ISDIR(child_dir.st_mode) || child_dir.st_dev != recorded.st_dev ||
        renameat(fd, "sub", fd, "sub-aside") != 0 || mkdirat(fd, "sub", 0700) != 0 ||
        fstatat(fd, "sub", &replacement_dir, AT_SYMLINK_NOFOLLOW) != 0 || !S_ISDIR(replacement_dir.st_mode) ||
        replacement_dir.st_ino == child_dir.st_ino) {
        failed = 1;
        goto done;
    }
    if (remove_tree(fd, "sub", recorded.st_dev, child_dir.st_ino, 0) == 0 ||
        fstatat(fd, "sub", &now, AT_SYMLINK_NOFOLLOW) != 0 || now.st_ino != replacement_dir.st_ino || !S_ISDIR(now.st_mode) ||
        fstatat(fd, "sub-aside", &now, AT_SYMLINK_NOFOLLOW) != 0 || now.st_ino != child_dir.st_ino || !S_ISDIR(now.st_mode) ||
        remove_tree(fd, "sub", recorded.st_dev, replacement_dir.st_ino, 0) != 0 ||
        remove_tree(fd, "sub-aside", recorded.st_dev, child_dir.st_ino, 0) != 0 ||
        renameat(g_parent_fd, name, g_parent_fd, side) != 0) {
        failed = 1;
        goto done;
    }
    owned_name = side;
    if (create_file(g_parent_fd, name, "replacement\n", &file_st) != 0 || !S_ISREG(file_st.st_mode)) {
        failed = 1;
        goto done;
    }
    have_file = 1;
    if (remove_tree(g_parent_fd, name, recorded.st_dev, recorded.st_ino, 0) == 0 ||
        fstatat(g_parent_fd, name, &now, AT_SYMLINK_NOFOLLOW) != 0 ||
        !identity_is(&now, file_st.st_dev, file_st.st_ino, S_IFREG) ||
        fstatat(g_parent_fd, side, &now, AT_SYMLINK_NOFOLLOW) != 0 ||
        !identity_is(&now, recorded.st_dev, recorded.st_ino, S_IFDIR) || unlink_matching(g_parent_fd, name, &file_st, S_IFREG) != 0) {
        failed = 1;
        goto done;
    }
    have_file = 0;
    if (symlinkat("not-a-target", g_parent_fd, name) != 0 || fstatat(g_parent_fd, name, &link_st, AT_SYMLINK_NOFOLLOW) != 0 ||
        !S_ISLNK(link_st.st_mode)) {
        failed = 1;
        goto done;
    }
    have_link = 1;
    if (remove_tree(g_parent_fd, name, recorded.st_dev, recorded.st_ino, 0) == 0 ||
        fstatat(g_parent_fd, name, &now, AT_SYMLINK_NOFOLLOW) != 0 || !S_ISLNK(now.st_mode) || now.st_dev != link_st.st_dev ||
        now.st_ino != link_st.st_ino || unlink_matching(g_parent_fd, name, &link_st, S_IFLNK) != 0 ||
        renameat(g_parent_fd, side, g_parent_fd, name) != 0) {
        failed = 1;
        goto done;
    }
    have_link = 0;
    owned_name = name;
    if (remove_tree(g_parent_fd, name, recorded.st_dev, recorded.st_ino, 0) != 0 ||
        (fstatat(g_parent_fd, name, &now, AT_SYMLINK_NOFOLLOW) == 0 || errno != ENOENT)) {
        failed = 1;
        goto done;
    }
    owned_name = NULL;
done:
    if (have_file && unlink_matching(g_parent_fd, name, &file_st, S_IFREG) != 0) {
        g_cleanup_uncertain = 1;
    }
    if (have_link && unlink_matching(g_parent_fd, name, &link_st, S_IFLNK) != 0) {
        g_cleanup_uncertain = 1;
    }
    if (failed && owned_name != NULL) {
        struct stat still;
        if (!have_record && fstatat(g_parent_fd, owned_name, &still, AT_SYMLINK_NOFOLLOW) == 0 && S_ISDIR(still.st_mode)) {
            recorded = still;
            have_record = 1;
        }
        if (have_record && fstatat(g_parent_fd, owned_name, &still, AT_SYMLINK_NOFOLLOW) == 0 &&
            identity_is(&still, recorded.st_dev, recorded.st_ino, S_IFDIR)) {
            int hold_fd = -1;
            if (fd >= 0) {
                struct stat held;
                if (fstat(fd, &held) == 0 && identity_is(&held, recorded.st_dev, recorded.st_ino, S_IFDIR)) {
                    hold_fd = fd;
                    fd = -1;
                }
            }
            retain_hold(hold_fd, owned_name, &recorded);
        }
    }
    if (fd >= 0) {
        close(fd);
    }
    snprintf(line, sizeof line,
             "case=replaced-cleanup-entry arch=%s source=%s step=identity result=%s native_security_calls=0 "
             "forbidden_native_calls=0 unconfigured=0 data_ops=0 marker=na publication=na child_exit=na child_reap=na "
             "cleanup=pending verdict=%s evidence=owner\n",
             g_arch, g_source[0] != '\0' ? g_source : "unreadable", failed ? "wrong" : "refused",
             failed ? "test_failure" : "pass");
    emit_safe(line);
    return failed ? -1 : 0;
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

static int descendant_leader_main(void) {
    int ack[2];
    pid_t child;
    char byte = 0;
    /* The owner catches SIGTERM. This leader must die on SIGTERM; its child ignores it. */
    signal(SIGTERM, SIG_DFL);
    signal(SIGINT, SIG_DFL);
    signal(SIGHUP, SIG_DFL);
    if (pipe(ack) != 0) {
        return 1;
    }
    child = fork();
    if (child < 0) {
        close(ack[0]);
        close(ack[1]);
        return 1;
    }
    if (child == 0) {
        close(ack[0]);
        signal(SIGTERM, SIG_IGN);
        signal(SIGINT, SIG_IGN);
        signal(SIGHUP, SIG_IGN);
        signal(SIGPIPE, SIG_IGN);
        if (write(ack[1], "t", 1) != 1) {
            close(ack[1]);
            return 1;
        }
        close(ack[1]);
        close(STDOUT_FILENO);
        close(STDERR_FILENO);
        for (;;) {
            pause();
        }
    }
    close(ack[1]);
    {
        ssize_t got;
        do {
            got = read(ack[0], &byte, 1);
        } while (got < 0 && errno == EINTR);
        close(ack[0]);
        if (got != 1 || byte != 't') {
            return 1;
        }
    }
    if (write_all_fd(STDOUT_FILENO, "ready\n", 6) != 0) {
        return 1;
    }
    close(STDOUT_FILENO);
    close(STDERR_FILENO);
    for (;;) {
        pause();
    }
    return 0;
}

static int case_descendant(const char *exe) {
    char *argv[3];
    char reap[16];
    char line[640];
    int pipes[2];
    int status = 0;
    int ok = 0;
    pid_t pid = -1;
    struct child_slot *slot;
    argv[0] = (char *)exe;
    argv[1] = "--descendant-leader";
    argv[2] = NULL;
    if (exe == NULL || exe[0] == '\0' || pipe(pipes) != 0) {
        return -1;
    }
    fcntl(pipes[0], F_SETFD, FD_CLOEXEC);
    fcntl(pipes[1], F_SETFD, FD_CLOEXEC);
    if (spawn_recorded(argv, -1, pipes[1], -1, -1, &pid) != 0) {
        close(pipes[0]);
        close(pipes[1]);
        return -1;
    }
    close(pipes[1]);
    if (read_ready_frame(pipes[0], child_budget()) != 0) {
        close(pipes[0]);
        signal_one(pid, SIGTERM);
        snprintf(line, sizeof line,
                 "case=descendant-survives-leader arch=%s source=%s step=term_reap result=wrong native_security_calls=0 "
                 "forbidden_native_calls=0 unconfigured=0 data_ops=0 marker=na publication=na child_exit=na "
                 "child_reap=not_reaped cleanup=pending verdict=test_failure evidence=owner group_settled=0\n",
                 g_arch, g_source[0] != '\0' ? g_source : "unreadable");
        emit_safe(line);
        return -1;
    }
    close(pipes[0]);
    signal_one(pid, SIGTERM);
    if (wait_budget(pid, &status, reap, sizeof reap, child_budget()) == 0 && WIFSIGNALED(status)) {
        slot = find_child(pid);
        if (slot != NULL && slot->live && slot->leader_reaped && slot->pgid == pid && group_occupied(slot->pgid) == 1 &&
            !cleanup_complete_allowed()) {
            ok = 1;
        }
    }
    snprintf(line, sizeof line,
             "case=descendant-survives-leader arch=%s source=%s step=term_reap result=%s native_security_calls=0 "
             "forbidden_native_calls=0 unconfigured=0 data_ops=0 marker=na publication=na child_exit=na child_reap=%s "
             "cleanup=pending verdict=%s evidence=owner group_settled=%s\n",
             g_arch, g_source[0] != '\0' ? g_source : "unreadable", ok ? "unsettled" : "wrong", ok ? reap : "not_reaped",
             ok ? "pass" : "test_failure", ok ? "0" : "na");
    emit_safe(line);
    return ok ? 0 : -1;
}

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
    struct sup_slot slots[MAX_SUPER_SLOTS];
    struct sup_dir dirs[MAX_SUPER_DIRS];
    char line[160];
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
    for (index = 0; index < MAX_SUPER_SLOTS; index++) {
        if (state->slots[index].retired && state->slots[index].pgid == pgid) {
            /* A later report may keep the result unresolved. It does not restore signals. */
            state->slots[index].live = 1;
            return 0;
        }
    }
    for (index = 0; index < MAX_SUPER_SLOTS; index++) {
        if (state->slots[index].live && state->slots[index].pgid == pgid) {
            return 0;
        }
    }
    for (index = 0; index < MAX_SUPER_SLOTS; index++) {
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

/* X retires the numeric group for every later signal. A disagreeing or
   uncertain probe keeps the slot unresolved and still not signalable. */
static void sup_retire_slot(struct sup_state *state, pid_t pgid) {
    int index;
    int occupied;
    int found = 0;
    if (pgid <= 1 || pgid == getpid() || pgid == getpgrp()) {
        state->stream_uncertain = 1;
        return;
    }
    occupied = group_occupied(pgid);
    for (index = 0; index < MAX_SUPER_SLOTS; index++) {
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
    for (index = 0; index < MAX_SUPER_SLOTS; index++) {
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
    for (index = 0; index < MAX_SUPER_SLOTS; index++) {
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
    for (index = 0; index < MAX_SUPER_SLOTS; index++) {
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

/* 1 only when this waitpid collected pid. It does not change decision_reaped.
   ECHILD and expiry are not collection. */
static int hygiene_collect(pid_t pid) {
    long start = mono_ms();
    int status = 0;
    if (pid <= 1 || start < 0) {
        return 0;
    }
    while (mono_ms() - start < HYGIENE_MS) {
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

/* The decision flags are fixed before SIGKILL. A later waitpid is only hygiene
   and does not change decision_reaped. Neither step proves a kernel-stuck
   process was reaped. */
static void supervise_child(pid_t pid, int record_fd, long start_ms, long normal_ms, long grace_ms, struct sup_result *result) {
    struct sup_state state;
    long normal_end;
    long grace_end = 0;
    int grace_on = 0;
    memset(&state, 0, sizeof state);
    result->owner_exit = -1;
    if (start_ms < 0 || sup_add_slot(&state, pid, pid) != 0) {
        result->timed_out = 0;
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

static void stall_failure_line(const char *arch) {
    printf("case=supervisor-stall arch=%s source=na step=finite result=wrong native_security_calls=0 "
           "forbidden_native_calls=0 unconfigured=0 data_ops=0 marker=na publication=na child_exit=na "
           "child_reap=not_reaped cleanup=incomplete verdict=test_failure evidence=supervisor "
           "deadline_does_not_prove_stuck_kernel_reaped=1 kernel_stuck_reaped=0 custody=retained decision_reaped=0\n",
           arch);
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
        stall_failure_line(arch);
        return 1;
    }
    set_nonblock_cloexec(pipes[0]);
    fcntl(pipes[1], F_SETFD, FD_CLOEXEC);
    if (spawn_supervisor_child(argv, pipes[1], &pid) != 0) {
        close(pipes[0]);
        close(pipes[1]);
        stall_failure_line(arch);
        return 1;
    }
    close(pipes[1]);
    start = mono_ms();
    supervise_child(pid, pipes[0], start, STALL_NORMAL_MS, STALL_GRACE_MS, &result);
    close(pipes[0]);
    deadline_ok = result.timed_out && !result.decision_reaped && result.unresolved;
    settled = result.hygiene_collected && result.hygiene_group_empty;
    printf("case=supervisor-stall arch=%s source=na step=finite result=%s native_security_calls=0 "
           "forbidden_native_calls=0 unconfigured=0 data_ops=0 marker=na publication=na child_exit=na "
           "child_reap=not_reaped cleanup=incomplete verdict=%s evidence=supervisor "
           "deadline_does_not_prove_stuck_kernel_reaped=1 kernel_stuck_reaped=0 custody=retained decision_reaped=%d "
           "hygiene_collected=%d hygiene_group_empty=%d\n",
           arch, deadline_ok ? "incomplete" : "wrong",
           deadline_ok && settled ? "pass" : (deadline_ok ? "incomplete_cleanup" : "test_failure"), result.decision_reaped,
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
    printf("case=supervisor arch=%s source=na step=settle result=%s native_security_calls=0 forbidden_native_calls=0 "
           "unconfigured=0 data_ops=0 marker=na publication=na child_exit=%s child_reap=%s cleanup=%s verdict=%s "
           "evidence=supervisor deadline_does_not_prove_stuck_kernel_reaped=1 kernel_stuck_reaped=0 custody=%s "
           "decision_reaped=%d\n",
           arch, cleanup, child_exit, reap, cleanup, verdict, custody, result->decision_reaped);
    return code;
}

static int supervisor_main(const char *exe, const char *arch, const char *parent) {
    char *argv[5];
    struct sup_result result;
    int record[2];
    long start;
    pid_t pid = -1;
    if (pipe(g_wake) != 0) {
        return 1;
    }
    set_nonblock_cloexec(g_wake[0]);
    set_nonblock_cloexec(g_wake[1]);
    arm_signals();
    {
        int stall_code = case_supervisor_stall(exe, arch);
        if (stall_code != 0) {
            return stall_code;
        }
    }
    if (g_stop) {
        printf("case=supervisor arch=%s source=na step=settle result=cancelled native_security_calls=0 "
               "forbidden_native_calls=0 unconfigured=0 data_ops=0 marker=na publication=na child_exit=na "
               "child_reap=not_reaped cleanup=complete verdict=cancelled evidence=supervisor "
               "deadline_does_not_prove_stuck_kernel_reaped=1 kernel_stuck_reaped=0 custody=none decision_reaped=0\n",
               arch);
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
    supervise_child(pid, record[0], start, RUN_LIMIT_MS, CLEANUP_GRACE_MS, &result);
    close(record[0]);
    return finish_supervisor(arch, &result);
}

static int usage(void) {
    fprintf(stderr, "usage: fixture-owner arm64|x86_64 absolute-private-parent\n");
    return 4;
}

static int owner_main(const char *exe, const char *arch, const char *parent) {
    long start = mono_ms();
    int cleanup_ok;
    int exit_code;
    struct run_slot *main_run;
    ino_t sealed_file = 0;
    g_hold.live = 0;
    g_hold.fd = -1;
    if (arch == NULL || parent == NULL || (strcmp(arch, "arm64") != 0 && strcmp(arch, "x86_64") != 0)) {
        return usage();
    }
    if (start < 0) {
        return 1;
    }
    g_deadline = start + RUN_LIMIT_MS;
    snprintf(g_arch, sizeof g_arch, "%s", arch);
    if (pipe(g_wake) != 0) {
        return 1;
    }
    set_nonblock_cloexec(g_wake[0]);
    set_nonblock_cloexec(g_wake[1]);
    arm_signals();
    if (walk_parent(parent) != 0) {
        printf("case=preflight arch=%s source=unreadable step=parent result=rejected native_security_calls=0 "
               "forbidden_native_calls=0 unconfigured=0 data_ops=0 marker=na publication=na child_exit=na "
               "child_reap=na cleanup=complete verdict=test_failure evidence=owner\n",
               g_arch);
        return 4;
    }
    if (read_source() != 0) {
        g_case_failure = 1;
        cleanup_ok = cleanup_runs() == 0;
        summary(cleanup_ok);
        if (g_parent_fd >= 0) {
            close(g_parent_fd);
        }
        return cleanup_ok ? 1 : 2;
    }
    main_run = &g_runs[0];
    if (prepare_slot(main_run) != 0 || simple_cases(main_run) != 0 || lock_cases(main_run) != 0) {
        g_case_failure = 1;
    } else if (add_named_file(main_run, "ciphertext", "sealed-file", "fixture-file\n", &sealed_file) != 0 ||
               run_worker(main_run, "ciphertext-missing-key") != 0 ||
               remove_named_file(main_run, "ciphertext", "sealed-file", sealed_file) != 0 ||
               run_worker(main_run, "add-fail") != 0 ||
               run_worker(main_run, "readable-consumed-marker") != 0 ||
               run_worker(main_run, "publish-partial") != 0 ||
               run_worker(main_run, "publish-fsync") != 0 ||
               run_worker(main_run, "publish-dir-fsync") != 0) {
        g_case_failure = 1;
    }
    if (!g_case_failure && !g_cancelled) {
        struct run_slot *restart = &g_runs[1];
        struct run_slot *partial = &g_runs[2];
        struct run_slot *file_sync = &g_runs[3];
        struct run_slot *dir_sync = &g_runs[4];
        char ready[2048];
        ino_t first_ino = 0;
        ino_t second_ino = 0;
        if (prepare_slot(restart) != 0) {
            g_case_failure = 1;
        } else {
            struct paused_child paused;
            if (spawn_paused(restart, "restart-first", &paused, ready, sizeof ready) != 0) {
                g_case_failure = 1;
            } else if (!public_text_ok(ready) || strstr(ready, "marker_create,") == NULL ||
                       strstr(ready, "marker_fsync,") == NULL || strstr(ready, "dir_fsync\n") == NULL ||
                       strstr(ready, "sec_add") != NULL || strcmp(marker_of(restart->fd), "present") != 0 ||
                       marker_ino(restart->fd, &first_ino) != 0) {
                g_case_failure = 1;
                abort_paused(&paused);
            } else {
                int status = 0;
                char reap[16];
                char line[1024];
                int identity_ok;
                /* Leave the hold pipe open so the child stays blocked, then signal
                   that child's retained group. Closing the hold first would let it return. */
                signal_one(paused.pid, SIGTERM);
                if (wait_budget(paused.pid, &status, reap, sizeof reap, child_budget()) != 0) {
                    g_case_failure = 1;
                } else if (!WIFSIGNALED(status)) {
                    g_case_failure = 1;
                }
                if (paused.hold_fd >= 0) {
                    close(paused.hold_fd);
                    paused.hold_fd = -1;
                }
                if (paused.out_fd >= 0) {
                    close(paused.out_fd);
                    paused.out_fd = -1;
                }
                snprintf(line, sizeof line,
                         "case=restart-first arch=%s source=%s step=pause_before_add order=withheld result=terminated "
                         "native_security_calls=0 forbidden_native_calls=0 unconfigured=0 data_ops=0 marker=%s "
                         "publication=none child_exit=na child_reap=%s cleanup=pending verdict=%s "
                         "evidence=process_restart run=%s\n",
                         g_arch, g_source, marker_of(restart->fd), reap,
                         g_case_failure ? "test_failure" : "expected_refusal", restart->id);
                emit_safe(line);
                if (!g_case_failure) {
                    identity_ok = run_worker(restart, "restart-second") == 0 &&
                                  marker_ino(restart->fd, &second_ino) == 0 && first_ino == second_ino;
                    if (!identity_ok) {
                        g_case_failure = 1;
                    }
                    snprintf(line, sizeof line,
                             "case=restart-identity arch=%s source=%s step=restart_second result=refused "
                             "native_security_calls=0 forbidden_native_calls=0 unconfigured=0 data_ops=0 marker=%s "
                             "publication=none child_exit=na child_reap=na cleanup=pending verdict=%s "
                             "evidence=process_restart marker_identity=%s run=%s\n",
                             g_arch, g_source, marker_of(restart->fd), identity_ok ? "pass" : "test_failure",
                             identity_ok ? "stable" : "changed", restart->id);
                    emit_safe(line);
                }
            }
        }
        if (!g_case_failure &&
            (prepare_slot(partial) != 0 || run_worker(partial, "marker-partial-write") != 0 ||
             prepare_slot(file_sync) != 0 || run_worker(file_sync, "marker-fsync-fail") != 0 ||
             prepare_slot(dir_sync) != 0 || run_worker(dir_sync, "marker-dir-fsync-fail") != 0)) {
            g_case_failure = 1;
        }
    }
    if (g_stop || remaining_run() == 0) {
        g_cancelled = 1;
    } else {
        if (case_replaced_cleanup_entry() != 0) {
            g_case_failure = 1;
        }
        if (case_descendant(exe) != 0) {
            g_case_failure = 1;
        }
    }
    cleanup_ok = cleanup_runs() == 0;
    summary(cleanup_ok);
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
    if (argc == 2 && strcmp(argv[1], "--descendant-leader") == 0) {
        return descendant_leader_main();
    }
    if (argc == 4 && strcmp(argv[1], "--owner") == 0) {
        if (fcntl(3, F_GETFL) < 0) {
            return 1;
        }
        set_nonblock_cloexec(3);
        g_record_fd = 3;
        return owner_main(argv[0], argv[2], argv[3]);
    }
    if (argc != 3 || (strcmp(argv[1], "arm64") != 0 && strcmp(argv[1], "x86_64") != 0)) {
        return usage();
    }
    return supervisor_main(argv[0], argv[1], argv[2]);
}
