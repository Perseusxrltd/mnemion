/*
 * Owned-child check for MACH_TASK_BASIC_INFO resident counters.
 *
 * Uses task_name_for_pid and task_info only. A name-port failure is recorded
 * and is not replaced with task_for_pid, a read port, or a zero size.
 * resident_size and resident_size_max are bytes (mach_task_basic_info).
 * On Darwin, getrusage ru_maxrss is bytes. The child samples it after the
 * baseline task_info and before the live task_info, so the accepted order is
 * baseline peak <= child peak <= live peak. Equality is not required.
 *
 * The child stays an unreaped child of this process until the live sample
 * has been taken. Pipes carry the handshake. There is no sleep-based sync.
 */

#include <errno.h>
#include <mach/mach.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

enum {
    DEADLINE_MS = 10000,
    ALLOC_BYTES = 8 * 1024 * 1024,
    TOUCH_STRIDE = 4096,
    OP_READY = 1,
    OP_ALLOC = 2,
    OP_DONE = 3,
    OP_RELEASE = 4
};

static volatile sig_atomic_t owned_child_pid;

static void on_term(int sig) {
    pid_t child = (pid_t)owned_child_pid;
    if (child > 1) {
        kill(child, SIGKILL);
    }
    _exit(128 + (sig > 0 ? sig : 1));
}

static int64_t now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static int transfer_all(int fd, void *buf, size_t n, int64_t deadline, int writing) {
    unsigned char *cursor = buf;
    size_t done = 0;
    while (done < n) {
        int64_t left = deadline - now_ms();
        struct pollfd pfd;
        int pr;
        ssize_t nbyte;
        if (left <= 0) {
            return -2;
        }
        pfd.fd = fd;
        pfd.events = writing ? POLLOUT : POLLIN;
        pr = poll(&pfd, 1, left > 250 ? 250 : (int)left);
        if (pr < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        if (pr == 0) {
            continue;
        }
        nbyte = writing ? write(fd, cursor + done, n - done) : read(fd, cursor + done, n - done);
        if (nbyte < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        if (nbyte == 0) {
            return -1;
        }
        done += (size_t)nbyte;
    }
    return 0;
}

static void store_u32(unsigned char *p, uint32_t v) {
    p[0] = (unsigned char)v;
    p[1] = (unsigned char)(v >> 8);
    p[2] = (unsigned char)(v >> 16);
    p[3] = (unsigned char)(v >> 24);
}

static void store_u64(unsigned char *p, uint64_t v) {
    int i;
    for (i = 0; i < 8; i++) {
        p[i] = (unsigned char)(v >> (8 * i));
    }
}

static uint32_t load_u32(const unsigned char *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
        ((uint32_t)p[3] << 24);
}

static uint64_t load_u64(const unsigned char *p) {
    uint64_t v = 0;
    int i;
    for (i = 0; i < 8; i++) {
        v |= (uint64_t)p[i] << (8 * i);
    }
    return v;
}

static int write_frame(int fd, uint32_t op, uint64_t value, int64_t deadline) {
    unsigned char buf[12];
    store_u32(buf, op);
    store_u64(buf + 4, value);
    return transfer_all(fd, buf, sizeof buf, deadline, 1);
}

static int read_frame(int fd, uint32_t *op, uint64_t *value, int64_t deadline) {
    unsigned char buf[12];
    int rc = transfer_all(fd, buf, sizeof buf, deadline, 0);
    if (rc != 0) {
        return rc;
    }
    *op = load_u32(buf);
    /* The uint64 starts after the uint32 opcode. buf[0] aliases that opcode. */
    *value = load_u64(buf + 4);
    return 0;
}

static void child_main(int to_parent, int from_parent, int64_t deadline) {
    uint32_t op = 0;
    uint64_t ignored = 0;
    unsigned char *block;
    size_t i;
    struct rusage usage;
    int rc;

    signal(SIGTERM, SIG_DFL);
    if (write_frame(to_parent, OP_READY, 0, deadline) != 0) {
        _exit(2);
    }
    rc = read_frame(from_parent, &op, &ignored, deadline);
    if (rc == -2) {
        _exit(9);
    }
    if (rc != 0) {
        _exit(3);
    }
    if (op == OP_RELEASE) {
        _exit(0);
    }
    if (op != OP_ALLOC) {
        _exit(3);
    }

    block = malloc(ALLOC_BYTES);
    if (block == NULL) {
        _exit(4);
    }
    for (i = 0; i < ALLOC_BYTES; i += TOUCH_STRIDE) {
        ((volatile unsigned char *)block)[i] = 1;
    }
    ((volatile unsigned char *)block)[ALLOC_BYTES - 1] = 1;
    memset(&usage, 0, sizeof usage);
    if (getrusage(RUSAGE_SELF, &usage) != 0 || usage.ru_maxrss < 0) {
        _exit(5);
    }
    if (write_frame(to_parent, OP_DONE, (uint64_t)usage.ru_maxrss, deadline) != 0) {
        _exit(6);
    }
    rc = read_frame(from_parent, &op, &ignored, deadline);
    if (rc != 0 || op != OP_RELEASE) {
        _exit(7);
    }
    free(block);
    _exit(0);
}

struct sample {
    int queried;
    int complete;
    kern_return_t kr;
    mach_msg_type_number_t count;
    mach_vm_size_t resident_size;
    mach_vm_size_t resident_size_max;
};

static void query_basic(mach_port_t port, struct sample *sample) {
    mach_task_basic_info_data_t info;
    mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
    memset(sample, 0, sizeof *sample);
    memset(&info, 0, sizeof info);
    sample->queried = 1;
    sample->count = count;
    sample->kr = task_info(port, MACH_TASK_BASIC_INFO, (task_info_t)&info, &count);
    sample->count = count;
    if (sample->kr == KERN_SUCCESS && count == MACH_TASK_BASIC_INFO_COUNT) {
        sample->complete = 1;
        sample->resident_size = info.resident_size;
        sample->resident_size_max = info.resident_size_max;
    }
}

struct run {
    pid_t child;
    int to_child;
    int from_child;
    int child_reaped;
    int have_status;
    int status;
    int timed_out;
    int kill_failed;
    int dealloc_ok;
    int dealloc_called;
    kern_return_t dealloc_kr;
    int name_called;
    kern_return_t name_kr;
    int name_port_is_null;
    mach_port_t port;
    int port_held;
    struct sample baseline;
    struct sample live;
    struct sample post;
    int have_rss;
    uint64_t child_rss;
    int64_t deadline;
    const char *detail;
};

static int still_unreaped(struct run *r) {
    int status = 0;
    pid_t wr;
    if (r->child <= 1 || r->child_reaped) {
        return 0;
    }
    do {
        wr = waitpid(r->child, &status, WNOHANG);
    } while (wr < 0 && errno == EINTR);
    if (wr == 0) {
        return 1;
    }
    if (wr == r->child) {
        r->have_status = 1;
        r->status = status;
        r->child_reaped = 1;
        owned_child_pid = 0;
        r->detail = "child_exited_early";
        return 0;
    }
    r->detail = "not_our_child";
    r->kill_failed = 1;
    return 0;
}

static void reap_owned(struct run *r) {
    int status = 0;
    if (r->child <= 1 || r->child_reaped) {
        return;
    }
    for (;;) {
        pid_t wr = waitpid(r->child, &status, WNOHANG);
        if (wr == r->child) {
            r->have_status = 1;
            r->status = status;
            r->child_reaped = 1;
            owned_child_pid = 0;
            return;
        }
        if (wr < 0 && errno == EINTR) {
            continue;
        }
        if (wr < 0) {
            r->detail = "not_our_child";
            r->kill_failed = 1;
            return;
        }
        if (now_ms() >= r->deadline) {
            r->timed_out = 1;
            if (kill(r->child, SIGKILL) < 0 && errno != ESRCH) {
                r->kill_failed = 1;
                r->detail = "kill_failed";
                return;
            }
            do {
                wr = waitpid(r->child, &status, 0);
            } while (wr < 0 && errno == EINTR);
            if (wr == r->child) {
                r->have_status = 1;
                r->status = status;
                r->child_reaped = 1;
                owned_child_pid = 0;
            }
            return;
        }
        poll(NULL, 0, 50);
    }
}

static void release_and_reap(struct run *r) {
    int rc;
    if (r->child <= 1 || r->child_reaped) {
        return;
    }
    if (!r->timed_out && r->to_child >= 0 && now_ms() < r->deadline) {
        rc = write_frame(r->to_child, OP_RELEASE, 0, r->deadline);
        if (rc == -2) {
            r->timed_out = 1;
        }
    }
    if (r->to_child >= 0) {
        close(r->to_child);
        r->to_child = -1;
    }
    reap_owned(r);
}

static void drop_port(struct run *r) {
    if (!r->port_held) {
        if (!r->dealloc_called) {
            r->dealloc_ok = 1;
        }
        return;
    }
    if (r->child_reaped) {
        query_basic(r->port, &r->post);
    }
    r->dealloc_kr = mach_port_deallocate(mach_task_self(), r->port);
    r->dealloc_called = 1;
    r->port = MACH_PORT_NULL;
    r->port_held = 0;
    r->dealloc_ok = r->dealloc_kr == KERN_SUCCESS;
}

static const char *decide(const struct run *r) {
    int clean = r->have_status && WIFEXITED(r->status) && WEXITSTATUS(r->status) == 0;
    if (r->timed_out || !r->child_reaped || !r->dealloc_ok || r->kill_failed || !clean) {
        return "child_or_cleanup_failure";
    }
    if (!r->name_called) {
        return "child_or_cleanup_failure";
    }
    if (r->name_kr != KERN_SUCCESS) {
        return "name_port_denied";
    }
    if (r->name_port_is_null || !r->baseline.complete || !r->live.complete || !r->have_rss) {
        return "counter_missing";
    }
    if (r->live.resident_size_max == 0) {
        return "zero_peak_rss";
    }
    if (r->live.resident_size_max < r->baseline.resident_size_max ||
        r->live.resident_size <= r->baseline.resident_size) {
        return "peak_or_allocation_check_failed";
    }
    if ((unsigned long long)r->child_rss < (unsigned long long)r->baseline.resident_size_max ||
        (unsigned long long)r->child_rss > (unsigned long long)r->live.resident_size_max) {
        return "child_peak_out_of_order";
    }
    return "live_counter_ok";
}

static int exit_for(const char *outcome) {
    if (strcmp(outcome, "live_counter_ok") == 0) {
        return 0;
    }
    if (strcmp(outcome, "name_port_denied") == 0) {
        return 2;
    }
    if (strcmp(outcome, "counter_missing") == 0) {
        return 3;
    }
    if (strcmp(outcome, "child_or_cleanup_failure") == 0) {
        return 4;
    }
    if (strcmp(outcome, "child_peak_out_of_order") == 0) {
        return 5;
    }
    return 5;
}

static void json_string(const char *text) {
    const unsigned char *cursor = (const unsigned char *)(text == NULL ? "" : text);
    fputc('"', stdout);
    for (; *cursor != 0; cursor++) {
        if (*cursor == '"' || *cursor == '\\') {
            fprintf(stdout, "\\%c", *cursor);
        } else if (*cursor < 0x20) {
            fprintf(stdout, "\\u%04x", *cursor);
        } else {
            fputc(*cursor, stdout);
        }
    }
    fputc('"', stdout);
}

static void json_size(int present, mach_vm_size_t value) {
    if (!present) {
        fputs("null", stdout);
        return;
    }
    fprintf(stdout, "%llu", (unsigned long long)value);
}

static void json_kern(int present, kern_return_t value) {
    if (!present) {
        fputs("null", stdout);
        return;
    }
    fprintf(stdout, "%d", (int)value);
}

static void json_count(int present, mach_msg_type_number_t value) {
    if (!present) {
        fputs("null", stdout);
        return;
    }
    fprintf(stdout, "%u", (unsigned)value);
}

static int source_is_sha(const char *text) {
    size_t i;
    if (text == NULL) {
        return 0;
    }
    for (i = 0; i < 40; i++) {
        char ch = text[i];
        int hex = (ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f');
        if (!hex) {
            return 0;
        }
    }
    return text[40] == 0;
}

static void emit(const struct run *r, const char *outcome) {
    struct utsname name;
    const char *source = getenv("MNEMION_PROBE_SOURCE");
    int source_ok = source_is_sha(source);
    int source_rejected = source != NULL && !source_ok;
    int uname_ok = uname(&name) == 0;
    int peaks_known = r->baseline.complete && r->live.complete;
    int clean_exit = r->have_status && WIFEXITED(r->status);
    int signaled = r->have_status && WIFSIGNALED(r->status);
    const char *kind = clean_exit ? "exited" : signaled ? "signaled" : "unexited";
    int cleanup_ok = r->dealloc_ok && !r->kill_failed && (r->child <= 1 || r->child_reaped);

    fputc('{', stdout);
    fputs("\"allocation_bytes\":8388608", stdout);
    fputs(",\"allocation_observed\":", stdout);
    if (!peaks_known) {
        fputs("null", stdout);
    } else {
        fputs(r->live.resident_size > r->baseline.resident_size ? "true" : "false", stdout);
    }
    fputs(",\"arch\":", stdout);
    json_string(uname_ok ? name.machine : "unknown");
    fputs(",\"baseline_resident_size\":", stdout);
    json_size(r->baseline.complete, r->baseline.resident_size);
    fputs(",\"baseline_resident_size_max\":", stdout);
    json_size(r->baseline.complete, r->baseline.resident_size_max);
    fputs(",\"baseline_task_info_count\":", stdout);
    json_count(r->baseline.queried, r->baseline.count);
    fputs(",\"baseline_task_info_kern_return\":", stdout);
    json_kern(r->baseline.queried, r->baseline.kr);
    fputs(",\"child_exit_kind\":", stdout);
    json_string(r->have_status ? kind : "unexited");
    fputs(",\"child_exit_status\":", stdout);
    if (clean_exit) {
        fprintf(stdout, "%d", WEXITSTATUS(r->status));
    } else {
        fputs("null", stdout);
    }
    fputs(",\"child_pid\":", stdout);
    if (r->child > 1) {
        fprintf(stdout, "%ld", (long)r->child);
    } else {
        fputs("null", stdout);
    }
    fputs(",\"child_reaped\":", stdout);
    fputs(r->child_reaped ? "true" : "false", stdout);
    fputs(",\"child_ru_maxrss\":", stdout);
    if (r->have_rss) {
        fprintf(stdout, "%llu", (unsigned long long)r->child_rss);
    } else {
        fputs("null", stdout);
    }
    fputs(",\"child_ru_maxrss_unit\":\"bytes\"", stdout);
    fputs(",\"child_term_signal\":", stdout);
    if (signaled) {
        fprintf(stdout, "%d", WTERMSIG(r->status));
    } else {
        fputs("null", stdout);
    }
    fputs(",\"cleanup_ok\":", stdout);
    fputs(cleanup_ok ? "true" : "false", stdout);
    fputs(",\"detail\":", stdout);
    json_string(r->detail != NULL ? r->detail : "");
    fputs(",\"live_resident_size\":", stdout);
    json_size(r->live.complete, r->live.resident_size);
    fputs(",\"live_resident_size_max\":", stdout);
    json_size(r->live.complete, r->live.resident_size_max);
    fputs(",\"live_task_info_count\":", stdout);
    json_count(r->live.queried, r->live.count);
    fputs(",\"live_task_info_kern_return\":", stdout);
    json_kern(r->live.queried, r->live.kr);
    fputs(",\"name_port_is_null\":", stdout);
    fputs(r->name_port_is_null ? "true" : "false", stdout);
    fputs(",\"name_port_kern_return\":", stdout);
    json_kern(r->name_called, r->name_kr);
    fputs(",\"os\":", stdout);
    json_string(uname_ok ? name.sysname : "unknown");
    fputs(",\"os_release\":", stdout);
    json_string(uname_ok ? name.release : "unknown");
    fputs(",\"outcome\":", stdout);
    json_string(outcome);
    fputs(",\"peaks_nondecreasing\":", stdout);
    if (!peaks_known) {
        fputs("null", stdout);
    } else {
        fputs(r->live.resident_size_max >= r->baseline.resident_size_max ? "true" : "false", stdout);
    }
    fputs(",\"port_deallocate_kern_return\":", stdout);
    json_kern(r->dealloc_called, r->dealloc_kr);
    fputs(",\"post_exit_queried\":", stdout);
    fputs(r->post.queried ? "true" : "false", stdout);
    fputs(",\"post_exit_resident_size\":", stdout);
    json_size(r->post.complete, r->post.resident_size);
    fputs(",\"post_exit_resident_size_max\":", stdout);
    json_size(r->post.complete, r->post.resident_size_max);
    fputs(",\"post_exit_supported\":", stdout);
    if (!r->post.queried) {
        fputs("null", stdout);
    } else {
        fputs(r->post.complete ? "true" : "false", stdout);
    }
    fputs(",\"post_exit_task_info_count\":", stdout);
    json_count(r->post.queried, r->post.count);
    fputs(",\"post_exit_task_info_kern_return\":", stdout);
    json_kern(r->post.queried, r->post.kr);
    fputs(",\"probe\":\"darwin_residency_counters\"", stdout);
    fputs(",\"resident_size_max_unit\":\"bytes\"", stdout);
    fputs(",\"resident_size_unit\":\"bytes\"", stdout);
    fputs(",\"resource_budget_acceptance\":false", stdout);
    fputs(",\"source\":", stdout);
    if (source_ok) {
        json_string(source);
    } else {
        fputs("null", stdout);
    }
    fputs(",\"source_rejected\":", stdout);
    fputs(source_rejected ? "true" : "false", stdout);
    fputs(",\"telemetry_acceptance\":false", stdout);
    fputs(",\"timed_out\":", stdout);
    fputs(r->timed_out ? "true" : "false", stdout);
    fputs(",\"workload_acceptance\":false", stdout);
    fputs("}\n", stdout);
}

static int parent_main(struct run *r) {
    uint32_t op = 0;
    uint64_t value = 0;
    int rc;
    const char *outcome;

    rc = read_frame(r->from_child, &op, &value, r->deadline);
    if (rc == -2) {
        r->timed_out = 1;
        r->detail = "timeout";
    } else if (rc != 0 || op != OP_READY) {
        r->detail = "handshake_failed";
    } else if (!still_unreaped(r)) {
        if (r->detail == NULL) {
            r->detail = "child_exited_early";
        }
    } else {
        r->port = MACH_PORT_NULL;
        r->name_kr = task_name_for_pid(mach_task_self(), (int)r->child, &r->port);
        r->name_called = 1;
        r->name_port_is_null = r->port == MACH_PORT_NULL;
        if (r->name_kr != KERN_SUCCESS || r->port == MACH_PORT_NULL) {
            r->detail = "name_port_rejected";
            if (r->port != MACH_PORT_NULL) {
                r->dealloc_kr = mach_port_deallocate(mach_task_self(), r->port);
                r->dealloc_called = 1;
                r->dealloc_ok = r->dealloc_kr == KERN_SUCCESS;
                r->port = MACH_PORT_NULL;
            }
        } else {
            r->port_held = 1;
            query_basic(r->port, &r->baseline);
            if (!r->baseline.complete) {
                r->detail = "counter_incomplete";
            } else if (write_frame(r->to_child, OP_ALLOC, 0, r->deadline) != 0) {
                r->detail = now_ms() >= r->deadline ? "timeout" : "handshake_failed";
                if (now_ms() >= r->deadline) {
                    r->timed_out = 1;
                }
            } else {
                rc = read_frame(r->from_child, &op, &value, r->deadline);
                if (rc == -2) {
                    r->timed_out = 1;
                    r->detail = "timeout";
                } else if (rc != 0 || op != OP_DONE) {
                    r->detail = "handshake_failed";
                } else if (!still_unreaped(r)) {
                    if (r->detail == NULL) {
                        r->detail = "child_exited_early";
                    }
                } else {
                    r->have_rss = 1;
                    r->child_rss = value;
                    query_basic(r->port, &r->live);
                    if (!r->live.complete) {
                        r->detail = "counter_incomplete";
                    } else if (r->live.resident_size_max == 0) {
                        r->detail = "zero_peak";
                    } else if (r->live.resident_size_max < r->baseline.resident_size_max) {
                        r->detail = "peak_decreased";
                    } else if (r->live.resident_size <= r->baseline.resident_size) {
                        r->detail = "allocation_not_observed";
                    } else if ((unsigned long long)r->child_rss <
                                   (unsigned long long)r->baseline.resident_size_max ||
                               (unsigned long long)r->child_rss >
                                   (unsigned long long)r->live.resident_size_max) {
                        r->detail = "child_peak_out_of_order";
                    } else {
                        r->detail = "ok";
                    }
                }
            }
        }
    }

    release_and_reap(r);
    drop_port(r);
    if (r->child > 1 && r->child_reaped) {
        int ignored = 0;
        pid_t again = waitpid(r->child, &ignored, WNOHANG);
        if (!(again < 0 && errno == ECHILD)) {
            r->kill_failed = 1;
            r->detail = "reap_not_confirmed";
        }
    }
    if (r->from_child >= 0) {
        close(r->from_child);
        r->from_child = -1;
    }
    outcome = decide(r);
    emit(r, outcome);
    return exit_for(outcome);
}

int main(void) {
    struct run r;
    int parent_to_child[2] = {-1, -1};
    int child_to_parent[2] = {-1, -1};
    pid_t child;
    sigset_t blocked;
    sigset_t previous;
    struct sigaction action;

    memset(&r, 0, sizeof r);
    r.to_child = -1;
    r.from_child = -1;
    r.deadline = now_ms() + DEADLINE_MS;
    r.detail = "fork_failed";
    r.dealloc_ok = 1;
    signal(SIGPIPE, SIG_IGN);
    memset(&action, 0, sizeof action);
    action.sa_handler = on_term;
    sigaction(SIGTERM, &action, NULL);

    if (pipe(parent_to_child) != 0) {
        r.detail = "pipe_failed";
        emit(&r, decide(&r));
        return exit_for(decide(&r));
    }
    if (pipe(child_to_parent) != 0) {
        close(parent_to_child[0]);
        close(parent_to_child[1]);
        r.detail = "pipe_failed";
        emit(&r, decide(&r));
        return exit_for(decide(&r));
    }

    sigemptyset(&blocked);
    sigaddset(&blocked, SIGTERM);
    sigprocmask(SIG_BLOCK, &blocked, &previous);
    child = fork();
    if (child == 0) {
        signal(SIGTERM, SIG_DFL);
        sigprocmask(SIG_SETMASK, &previous, NULL);
        close(parent_to_child[1]);
        close(child_to_parent[0]);
        child_main(child_to_parent[1], parent_to_child[0], r.deadline);
        _exit(1);
    }
    if (child > 0) {
        owned_child_pid = (sig_atomic_t)child;
    }
    sigprocmask(SIG_SETMASK, &previous, NULL);

    if (child < 0) {
        close(parent_to_child[0]);
        close(parent_to_child[1]);
        close(child_to_parent[0]);
        close(child_to_parent[1]);
        r.detail = "fork_failed";
        emit(&r, decide(&r));
        return exit_for(decide(&r));
    }

    close(parent_to_child[0]);
    close(child_to_parent[1]);
    r.child = child;
    r.to_child = parent_to_child[1];
    r.from_child = child_to_parent[0];
    return parent_main(&r);
}
