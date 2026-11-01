#include "fixture_inject.h"
#include "fixture_store.h"
#include "key_item.h"
#include "parent_direct_lookup.h"
#include "protocol.h"

#if !defined(MNEMION_FIXTURE_INJECT)
#error "fixture_worker.c is the injected fixture target, not the helper"
#endif
#ifndef FIXTURE_ARCH
#error "fixture worker requires FIXTURE_ARCH"
#endif
#ifndef FIXTURE_SOURCE
#error "fixture worker requires FIXTURE_SOURCE"
#endif

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Drives the real bind, copy, add, and publication functions. Receipts use
   fixed categories only. This is not a power-loss experiment. */

static int g_bad = 0;
static int g_ready_fd = -1;
static int g_hold_fd = -1;
static const char *g_step = "na";
static const char *g_result = "na";
static const char *g_marker = "na";
static const char *g_publication = "na";
static const char *g_directory = "na";
static const char *g_prior = "na";
static const char *g_reenter = "na";
static const char *g_load = "na";
static const char *g_add = "na";
static const char *g_absence = "na";
static const char *g_evidence = "injected_api";
static const char *g_verdict = "pass";
static const char *g_order = "";
static const char *g_side_order = "na";
static int g_native = 0;
static int g_unconfigured = 0;
static int g_data_ops = 0;
static int g_issued = 0;
static int g_disposed = 0;
static char g_order_buf[1600];
static char g_side_buf[1600];

static const char *k_bind_order =
    "ui_get,ui_set_disable,ui_get_readback,sec_open,sec_path,ui_set_restore,ui_get_readback";
static const char *k_setup_fail_get = "ui_get";
static const char *k_setup_fail_disable = "ui_get,ui_set_disable,ui_set_restore,ui_get_readback";
static const char *k_setup_fail_readback =
    "ui_get,ui_set_disable,ui_get_readback,ui_set_restore,ui_get_readback";
static const char *k_open_fail =
    "ui_get,ui_set_disable,ui_get_readback,sec_open,ui_set_restore,ui_get_readback";
/* copy_matching_holding() revalidates the bound store before its copy query
   (fixture_store.m), so these copy orders, and dispose-parent's copy bracket,
   require one sec_path immediately before sec_copy. add_holding() revalidates
   and then calls that function, so the six add/probe orders require two
   adjacent sec_path tokens before sec_copy. Both checks stay exact. */
static const char *k_copy_hit =
    "ui_get,ui_set_disable,ui_get_readback,sec_path,sec_copy,sec_item_keychain,sec_path,ui_set_restore,ui_get_readback";
static const char *k_copy_miss =
    "ui_get,ui_set_disable,ui_get_readback,sec_path,sec_copy,ui_set_restore,ui_get_readback";
static const char *k_copy_restore_fail =
    "ui_get,ui_set_disable,ui_get_readback,sec_path,sec_copy,sec_item_keychain,sec_path,ui_set_restore";

static void fail(void) {
    g_bad = 1;
}

static void expect(int condition) {
    if (!condition) {
        fail();
    }
}

static int parse_fd(const char *text) {
    long value = 0;
    size_t index;
    if (text == NULL || strcmp(text, "-1") == 0) {
        return -1;
    }
    if (text[0] == '\0') {
        return -2;
    }
    for (index = 0; text[index] != '\0'; index++) {
        if (text[index] < '0' || text[index] > '9' || index > 3) {
            return -2;
        }
        value = value * 10 + (text[index] - '0');
    }
    if (value < 0 || value > 200) {
        return -2;
    }
    return (int)value;
}

static void keep_order(char *dest, size_t cap) {
    const char *order = fixture_inject_order();
    if (order == NULL) {
        dest[0] = '\0';
        return;
    }
    if (strlen(order) >= cap) {
        dest[0] = '\0';
        fail();
        return;
    }
    memcpy(dest, order, strlen(order) + 1);
}

static void fill_observe(void) {
    int marker = -1;
    int publication = -1;
    int directory = -1;
    if (fixture_observe_run(&marker, &publication, &directory) != 0) {
        fail();
        g_marker = "error";
        g_publication = "error";
        g_directory = "error";
        return;
    }
    if (marker == FIXTURE_MARKER_ABSENT) {
        g_marker = "absent";
    } else if (marker == FIXTURE_MARKER_PRESENT) {
        g_marker = "present";
    } else if (marker == FIXTURE_MARKER_PARTIAL) {
        g_marker = "partial";
    } else {
        g_marker = "error";
        fail();
    }
    if (publication == FIXTURE_PUB_NONE) {
        g_publication = "none";
    } else if (publication == FIXTURE_PUB_RETAINED) {
        g_publication = "retained";
    } else {
        g_publication = "error";
        fail();
    }
    if (directory == FIXTURE_DIR_EMPTY) {
        g_directory = "empty";
    } else if (directory == FIXTURE_DIR_OCCUPIED) {
        g_directory = "occupied";
    } else {
        g_directory = "error";
        fail();
    }
}

static void note_prior(void) {
    int prior = fixture_inject_observed_prior();
    if (prior == 1) {
        g_prior = "enabled";
    } else if (prior == 0) {
        g_prior = "disabled";
    } else {
        g_prior = "na";
    }
}

static int bind_prepared(int prior_enabled) {
    int rc;
    fixture_inject_set_prior_ui(prior_enabled);
    fixture_inject_arm_bind();
    rc = fixture_store_bind();
    note_prior();
    return rc;
}

static void snapshot(int *data_ops, int *issued, int *disposed) {
    *data_ops = fixture_inject_data_operations();
    *issued = fixture_inject_issued_objects();
    *disposed = fixture_inject_disposed_objects();
}

static void finish_counts(int data_before, int issued_before, int disposed_before) {
    g_native = fixture_inject_native_security_calls();
    g_unconfigured = fixture_inject_unconfigured_calls();
    g_data_ops = fixture_inject_data_operations() - data_before;
    g_issued = fixture_inject_issued_objects() - issued_before;
    g_disposed = fixture_inject_disposed_objects() - disposed_before;
    if (g_native != 0 || g_unconfigured != 0 || fixture_inject_query_rejects() != 0 || g_data_ops < 0 || g_issued < 0 ||
        g_disposed < 0) {
        fail();
    }
}

static int case_bind_prior(int prior_enabled) {
    int rc = bind_prepared(prior_enabled);
    keep_order(g_order_buf, sizeof g_order_buf);
    g_order = g_order_buf;
    expect(rc == 0);
    expect(strcmp(g_order_buf, k_bind_order) == 0);
    expect(fixture_inject_data_operations() == 1);
    g_result = rc == 0 ? "ok" : "refused";
    g_verdict = "pass";
    g_evidence = "injected_api";
    finish_counts(0, 0, 0);
    fill_observe();
    expect(strcmp(g_marker, "absent") == 0);
    return 0;
}

static int case_setup_fault(int fault, const char *order, const char *step) {
    int rc;
    g_step = step;
    fixture_inject_set_prior_ui(1);
    fixture_inject_arm_bind();
    fixture_inject_fail_on_bracket(1, fault);
    rc = fixture_store_bind();
    note_prior();
    keep_order(g_order_buf, sizeof g_order_buf);
    g_order = g_order_buf;
    expect(rc != 0);
    expect(strcmp(g_order_buf, order) == 0);
    expect(fixture_inject_data_operations() == 0);
    g_result = "refused";
    g_verdict = "expected_refusal";
    finish_counts(0, 0, 0);
    fill_observe();
    return 0;
}

static int case_open_fault(void) {
    int rc;
    g_step = "open";
    fixture_inject_set_prior_ui(1);
    fixture_inject_arm_bind();
    fixture_inject_fail_on_bracket(1, FIXTURE_FAULT_OPEN);
    rc = fixture_store_bind();
    note_prior();
    keep_order(g_order_buf, sizeof g_order_buf);
    g_order = g_order_buf;
    expect(rc != 0);
    expect(strcmp(g_order_buf, k_open_fail) == 0);
    expect(fixture_inject_data_operations() == 1);
    g_result = "refused";
    g_verdict = "expected_refusal";
    finish_counts(0, 0, 0);
    fill_observe();
    return 0;
}

static int case_foreign_path(void) {
    int rc;
    g_step = "path_foreign";
    fixture_inject_set_prior_ui(1);
    fixture_inject_arm_bind();
    fixture_inject_fail_on_bracket(1, FIXTURE_FAULT_PATH_FOREIGN);
    rc = fixture_store_bind();
    keep_order(g_order_buf, sizeof g_order_buf);
    g_order = g_order_buf;
    expect(rc != 0);
    expect(strcmp(g_order_buf, k_bind_order) == 0);
    g_result = "refused";
    g_verdict = "expected_refusal";
    g_evidence = "injected_api";
    finish_counts(0, 0, 0);
    fill_observe();
    return 0;
}

static int case_foreign_store(void) {
    CFDataRef found = NULL;
    OSStatus status = errSecSuccess;
    int invoked = 0;
    int rc;
    int before_data;
    int before_issued;
    int before_disposed;
    g_step = "foreign_store";
    expect(bind_prepared(1) == 0);
    fixture_inject_order_clear();
    fixture_inject_arm_copy(FIXTURE_COPY_FOREIGN);
    snapshot(&before_data, &before_issued, &before_disposed);
    rc = fixture_store_copy_matching(&found, &status, &invoked);
    if (found != NULL) {
        CFRelease(found);
        fail();
    }
    keep_order(g_order_buf, sizeof g_order_buf);
    g_order = g_order_buf;
    expect(rc != 0);
    expect(status == errSecParam);
    expect(strcmp(g_order_buf, k_copy_hit) == 0);
    g_result = "refused";
    g_verdict = "expected_refusal";
    finish_counts(before_data, before_issued, before_disposed);
    expect(g_issued == 0 && g_disposed == 0);
    fill_observe();
    return 0;
}

static int load_restore_fault(enum key_result *loaded) {
    struct key_state state;
    int before_data;
    int before_issued;
    int before_disposed;
    key_state_init(&state);
    fixture_inject_order_clear();
    fixture_inject_arm_copy(FIXTURE_COPY_PRESENT);
    fixture_inject_fail_on_bracket(2, FIXTURE_FAULT_UI_RESTORE);
    snapshot(&before_data, &before_issued, &before_disposed);
    *loaded = key_item_load(&state);
    keep_order(g_order_buf, sizeof g_order_buf);
    g_order = g_order_buf;
    expect(*loaded == KEY_UNAVAILABLE);
    expect(state.derived_valid == 0);
    expect(strcmp(g_order_buf, k_copy_restore_fail) == 0);
    finish_counts(before_data, before_issued, before_disposed);
    expect(g_issued == 1 && g_disposed == 1 && g_data_ops == 1);
    key_state_zero(&state);
    return before_data;
}

static int case_dispose_key_item(void) {
    enum key_result loaded = KEY_OK;
    struct key_state state;
    int before_data;
    int before_issued;
    int before_disposed;
    g_step = "restore";
    g_evidence = "injected_api";
    expect(bind_prepared(1) == 0);
    load_restore_fault(&loaded);
    fixture_inject_order_clear();
    fixture_inject_arm_copy(FIXTURE_COPY_ABSENT);
    fixture_inject_fail_on_bracket(-1, FIXTURE_FAULT_NONE);
    key_state_init(&state);
    snapshot(&before_data, &before_issued, &before_disposed);
    loaded = key_item_load(&state);
    keep_order(g_side_buf, sizeof g_side_buf);
    g_side_order = g_side_buf;
    expect(loaded == KEY_ABSENT);
    expect(state.derived_valid == 0);
    expect(strcmp(g_side_buf, k_copy_miss) == 0);
    expect(fixture_inject_native_security_calls() == 0);
    expect(fixture_inject_unconfigured_calls() == 0);
    expect(fixture_inject_issued_objects() - before_issued == 0);
    expect(fixture_inject_disposed_objects() - before_disposed == 0);
    g_reenter = "entered";
    g_load = "unavailable";
    g_result = "refused";
    g_verdict = "expected_refusal";
    key_state_zero(&state);
    fill_observe();
    return 0;
}

static int capture_parent(char *out_text, size_t out_cap, char *err_text, size_t err_cap, int *status) {
    int out_pipe[2] = {-1, -1};
    int err_pipe[2] = {-1, -1};
    int saved_out = -1;
    int saved_err = -1;
    ssize_t count;
    int failed = 0;
    if (pipe(out_pipe) != 0) {
        return -1;
    }
    if (pipe(err_pipe) != 0) {
        close(out_pipe[0]);
        close(out_pipe[1]);
        return -1;
    }
    saved_out = dup(STDOUT_FILENO);
    saved_err = dup(STDERR_FILENO);
    if (saved_out < 0 || saved_err < 0 || dup2(out_pipe[1], STDOUT_FILENO) < 0 || dup2(err_pipe[1], STDERR_FILENO) < 0) {
        failed = 1;
    } else {
        close(out_pipe[1]);
        close(err_pipe[1]);
        out_pipe[1] = -1;
        err_pipe[1] = -1;
        *status = parent_direct_lookup();
        fflush(stdout);
        fflush(stderr);
    }
    if (saved_out >= 0 && dup2(saved_out, STDOUT_FILENO) < 0) {
        failed = 1;
    }
    if (saved_err >= 0 && dup2(saved_err, STDERR_FILENO) < 0) {
        failed = 1;
    }
    if (saved_out >= 0) {
        close(saved_out);
    }
    if (saved_err >= 0) {
        close(saved_err);
    }
    if (out_pipe[1] >= 0) {
        close(out_pipe[1]);
    }
    if (err_pipe[1] >= 0) {
        close(err_pipe[1]);
    }
    if (failed) {
        close(out_pipe[0]);
        close(err_pipe[0]);
        return -1;
    }
    count = read(out_pipe[0], out_text, out_cap - 1);
    if (count < 0) {
        return -1;
    }
    out_text[count] = '\0';
    if (read(out_pipe[0], &(char){0}, 1) != 0) {
        return -1;
    }
    count = read(err_pipe[0], err_text, err_cap - 1);
    if (count < 0) {
        return -1;
    }
    err_text[count] = '\0';
    if (read(err_pipe[0], &(char){0}, 1) != 0) {
        return -1;
    }
    close(out_pipe[0]);
    close(err_pipe[0]);
    return 0;
}

static int case_dispose_parent(void) {
    char out_text[128];
    char err_text[128];
    int status = 0;
    int before_issued;
    int before_disposed;
    int before_data;
    g_step = "restore";
    fixture_inject_set_prior_ui(1);
    fixture_inject_arm_bind();
    fixture_inject_arm_copy(FIXTURE_COPY_PRESENT);
    fixture_inject_fail_on_bracket(2, FIXTURE_FAULT_UI_RESTORE);
    snapshot(&before_data, &before_issued, &before_disposed);
    if (capture_parent(out_text, sizeof out_text, err_text, sizeof err_text, &status) != 0) {
        fail();
    }
    keep_order(g_order_buf, sizeof g_order_buf);
    g_order = g_order_buf;
    expect(status == 1);
    expect(strcmp(out_text, "result=unavailable\nkeychain_calls=1\n") == 0);
    expect(strcmp(err_text, "store_refused\n") == 0);
    expect(strcmp(g_order_buf,
                  "ui_get,ui_set_disable,ui_get_readback,sec_open,sec_path,ui_set_restore,ui_get_readback,ui_get,"
                  "ui_set_disable,ui_get_readback,sec_path,sec_copy,sec_item_keychain,sec_path,ui_set_restore") == 0);
    expect(strstr(out_text, "fixture-synthetic") == NULL);
    expect(strstr(err_text, "fixture-synthetic") == NULL);
    finish_counts(before_data, before_issued, before_disposed);
    expect(g_issued == 1 && g_disposed == 1);
    expect(strstr(g_order_buf, "sec_copy") != NULL);
    expect(strstr(g_order_buf, "sec_add") == NULL);
    g_result = "refused";
    g_verdict = "expected_refusal";
    g_load = "unavailable";
    fill_observe();
    return 0;
}

static const uint8_t k_add_bytes[] = {'f', 'i', 'x', 't', 'u', 'r', 'e', '-', 'a', 'd', 'd', '-', 'v', 'a', 'l', 'u', 'e'};
static const uint8_t k_pub_bytes[] = {'f', 'i', 'x', 't', 'u', 'r', 'e', '-', 'f', 'i', 'l', 'e'};

static int case_add(int claims, int copy_kind, int add_kind, int fs, int pause, const char *order, int want_fn,
                    OSStatus want_status, const char *step, const char *verdict, const char *evidence) {
    OSStatus status = errSecSuccess;
    int invoked = 0;
    int rc;
    int before_data;
    int before_issued;
    int before_disposed;
    g_step = step;
    g_evidence = evidence;
    g_absence = claims ? "ignored" : "na";
    expect(bind_prepared(1) == 0);
    fixture_inject_order_clear();
    fixture_inject_arm_copy(copy_kind);
    fixture_inject_arm_add(add_kind);
    if (fs != FIXTURE_FS_NONE) {
        fixture_inject_fail_fs(fs);
    }
    if (pause != FIXTURE_PAUSE_NONE) {
        fixture_inject_set_pause(pause, g_ready_fd, g_hold_fd);
    }
    snapshot(&before_data, &before_issued, &before_disposed);
    rc = fixture_store_add_new(k_add_bytes, sizeof k_add_bytes, claims, &status, &invoked);
    keep_order(g_order_buf, sizeof g_order_buf);
    g_order = g_order_buf;
    expect(rc == want_fn);
    if (want_fn == 0) {
        expect(status == want_status);
    }
    if (order != NULL) {
        expect(strcmp(g_order_buf, order) == 0);
    }
    g_result = (rc != 0 || status != errSecSuccess) ? "refused" : "ok";
    g_verdict = verdict;
    g_add = (strstr(g_order_buf, "sec_add") != NULL) ? "called" : "not_called";
    finish_counts(before_data, before_issued, before_disposed);
    fill_observe();
    return 0;
}

static int case_lock_hold(const char *step, const char *verdict) {
    return case_add(1, FIXTURE_COPY_ABSENT, FIXTURE_ADD_FAIL, FIXTURE_FS_NONE, FIXTURE_PAUSE_HOLDING_LOCK,
                    "lock_acquired,lock_released", -1, errSecParam, step, verdict, "lock_contention");
}

static int case_lock_try(void) {
    return case_add(1, FIXTURE_COPY_ABSENT, FIXTURE_ADD_FAIL, FIXTURE_FS_NONE, FIXTURE_PAUSE_NONE, "lock_busy", -1,
                    errSecParam, "lock_contention", "expected_refusal", "lock_contention");
}

static int case_restart_first(void) {
    g_step = "pause_before_add";
    g_evidence = "process_restart";
    /* Returning here means the owner released the hold. The child was supposed
       to be terminated after the durable marker and before Add. */
    case_add(1, FIXTURE_COPY_ABSENT, FIXTURE_ADD_FAIL, FIXTURE_FS_NONE, FIXTURE_PAUSE_BEFORE_ADD, NULL, 0, errSecSuccess,
             "pause_before_add", "test_failure", "process_restart");
    fail();
    g_verdict = "test_failure";
    return 0;
}

static int case_readable(void) {
    struct key_state state;
    enum key_result loaded;
    int before_data;
    int before_issued;
    int before_disposed;
    g_step = "existing_key";
    g_evidence = "injected_api";
    expect(bind_prepared(1) == 0);
    fixture_inject_order_clear();
    fixture_inject_arm_copy(FIXTURE_COPY_PRESENT);
    key_state_init(&state);
    snapshot(&before_data, &before_issued, &before_disposed);
    loaded = key_item_load(&state);
    keep_order(g_side_buf, sizeof g_side_buf);
    g_side_order = g_side_buf;
    expect(loaded == KEY_OK);
    expect(state.derived_valid == 1);
    expect(strcmp(g_side_buf, k_copy_hit) == 0);
    key_state_zero(&state);
    expect(state.derived_valid == 0);
    fixture_inject_order_clear();
    fixture_inject_arm_copy(FIXTURE_COPY_PRESENT);
    fixture_inject_arm_add(FIXTURE_ADD_FAIL);
    {
        OSStatus status = errSecSuccess;
        int invoked = 0;
        int rc = fixture_store_add_new(k_add_bytes, sizeof k_add_bytes, 1, &status, &invoked);
        keep_order(g_order_buf, sizeof g_order_buf);
        g_order = g_order_buf;
        expect(rc == 0);
        expect(status == errSecDuplicateItem);
        expect(strstr(g_order_buf, "sec_add") == NULL);
        expect(strstr(g_order_buf, "sec_copy") != NULL);
        expect(strstr(g_order_buf, "marker_create") == NULL);
    }
    g_load = "accepted";
    g_add = "not_called";
    g_absence = "ignored";
    g_result = "refused";
    g_verdict = "pass";
    finish_counts(before_data, before_issued, before_disposed);
    fill_observe();
    expect(strcmp(g_marker, "present") == 0);
    return 0;
}

static int case_publish(int fs, const char *step) {
    int rc;
    int before_data;
    int before_issued;
    int before_disposed;
    g_step = step;
    g_evidence = "injected_fs";
    expect(bind_prepared(1) == 0);
    fixture_inject_order_clear();
    fixture_inject_fail_fs(fs);
    snapshot(&before_data, &before_issued, &before_disposed);
    rc = fixture_store_publish_ciphertext(k_pub_bytes, sizeof k_pub_bytes);
    keep_order(g_order_buf, sizeof g_order_buf);
    g_order = g_order_buf;
    expect(rc != 0);
    expect(strstr(g_order_buf, "publish_create") != NULL);
    expect(strstr(g_order_buf, "sec_add") == NULL);
    if (fs == FIXTURE_FS_PUBLISH_WRITE) {
        expect(strstr(g_order_buf, "publish_write_partial") != NULL);
    } else if (fs == FIXTURE_FS_PUBLISH_FSYNC) {
        expect(strstr(g_order_buf, "publish_fsync_fail") != NULL);
    } else {
        expect(strstr(g_order_buf, "publish_fsync") != NULL);
        expect(strstr(g_order_buf, "publish_dir_fsync_fail") != NULL);
    }
    g_result = "refused";
    g_verdict = "expected_refusal";
    finish_counts(before_data, before_issued, before_disposed);
    expect(g_data_ops == 0);
    fill_observe();
    expect(strcmp(g_publication, "retained") == 0);
    expect(strcmp(g_marker, "present") == 0);
    return 0;
}

static int emit(const char *case_name) {
    const char *verdict = g_bad ? "test_failure" : g_verdict;
    const char *order = g_order != NULL ? g_order : "";
    int rc = g_bad ? 1 : 0;
    if (strchr(order, '/') != NULL || strstr(order, "fixture-synthetic") != NULL) {
        order = "rejected";
        verdict = "test_failure";
        rc = 1;
    }
    printf("case=%s arch=%s source=%s step=%s order=%s side_order=%s result=%s native_security_calls=%d "
           "forbidden_native_calls=%d unconfigured=%d data_ops=%d marker=%s publication=%s directory=%s prior=%s "
           "reenter=%s load=%s add=%s absence_claim=%s evidence=%s issued=%d disposed=%d verdict=%s\n",
           case_name, FIXTURE_ARCH, FIXTURE_SOURCE, g_step, order[0] != '\0' ? order : "none", g_side_order, g_result,
           g_native, g_native, g_unconfigured, g_data_ops, g_marker, g_publication, g_directory, g_prior, g_reenter,
           g_load, g_add, g_absence, g_evidence, g_issued, g_disposed, verdict);
    return rc;
}

int main(int argc, char **argv) {
    const char *name;
    int ready;
    int hold;
    if (argc != 4) {
        fprintf(stderr, "usage: fixture-worker case ready-fd hold-fd\n");
        return 2;
    }
    name = argv[1];
    ready = parse_fd(argv[2]);
    hold = parse_fd(argv[3]);
    if (ready == -2 || hold == -2) {
        return 2;
    }
    g_ready_fd = ready;
    g_hold_fd = hold;
    fixture_inject_reset();
    g_step = name;
    if (strcmp(name, "ui-prior-enabled") == 0) {
        g_step = "none";
        case_bind_prior(1);
        expect(strcmp(g_prior, "enabled") == 0);
    } else if (strcmp(name, "ui-prior-disabled") == 0) {
        g_step = "none";
        case_bind_prior(0);
        expect(strcmp(g_prior, "disabled") == 0);
    } else if (strcmp(name, "ui-fail-get") == 0) {
        case_setup_fault(FIXTURE_FAULT_UI_GET, k_setup_fail_get, "ui_get");
    } else if (strcmp(name, "ui-fail-disable") == 0) {
        case_setup_fault(FIXTURE_FAULT_UI_DISABLE, k_setup_fail_disable, "ui_disable");
    } else if (strcmp(name, "ui-fail-readback") == 0) {
        case_setup_fault(FIXTURE_FAULT_UI_READBACK, k_setup_fail_readback, "ui_readback");
    } else if (strcmp(name, "ui-fail-readback-mismatch") == 0) {
        case_setup_fault(FIXTURE_FAULT_UI_READBACK_MISMATCH, k_setup_fail_readback, "ui_readback_mismatch");
    } else if (strcmp(name, "ui-fail-operation") == 0) {
        case_open_fault();
    } else if (strcmp(name, "bind-foreign-path") == 0) {
        case_foreign_path();
    } else if (strcmp(name, "copy-foreign-store") == 0) {
        case_foreign_store();
    } else if (strcmp(name, "dispose-key-item") == 0) {
        case_dispose_key_item();
    } else if (strcmp(name, "dispose-parent") == 0) {
        case_dispose_parent();
    } else if (strcmp(name, "lock-hold") == 0 || strcmp(name, "lock-reuse") == 0) {
        case_lock_hold(strcmp(name, "lock-hold") == 0 ? "lock_hold" : "lock_reuse", "pass");
        expect(strcmp(g_marker, "absent") == 0);
        expect(strcmp(g_add, "not_called") == 0);
    } else if (strcmp(name, "lock-try") == 0) {
        case_lock_try();
        expect(strcmp(g_marker, "absent") == 0);
        expect(strcmp(g_add, "not_called") == 0);
    } else if (strcmp(name, "ciphertext-missing-key") == 0) {
        case_add(1, FIXTURE_COPY_ABSENT, FIXTURE_ADD_FAIL, FIXTURE_FS_NONE, FIXTURE_PAUSE_NONE,
                 "lock_acquired,ui_get,ui_set_disable,ui_get_readback,sec_path,sec_path,sec_copy,ui_set_restore,ui_get_readback,"
                 "lock_released",
                 -1, errSecParam, "ciphertext_present", "expected_refusal", "injected_api");
        expect(strcmp(g_marker, "absent") == 0);
        expect(strcmp(g_directory, "occupied") == 0);
        expect(strcmp(g_add, "not_called") == 0);
    } else if (strcmp(name, "add-fail") == 0) {
        case_add(1, FIXTURE_COPY_ABSENT, FIXTURE_ADD_FAIL, FIXTURE_FS_NONE, FIXTURE_PAUSE_NONE,
                 "lock_acquired,ui_get,ui_set_disable,ui_get_readback,sec_path,sec_path,sec_copy,marker_create,marker_fsync,dir_fsync,"
                 "sec_add,ui_set_restore,ui_get_readback,lock_released",
                 0, errSecAuthFailed, "add", "expected_refusal", "injected_api");
        expect(strcmp(g_marker, "present") == 0);
        expect(strcmp(g_add, "called") == 0);
        expect(strcmp(g_publication, "none") == 0);
    } else if (strcmp(name, "readable-consumed-marker") == 0) {
        case_readable();
    } else if (strcmp(name, "publish-partial") == 0) {
        case_publish(FIXTURE_FS_PUBLISH_WRITE, "publish_write");
    } else if (strcmp(name, "publish-fsync") == 0) {
        case_publish(FIXTURE_FS_PUBLISH_FSYNC, "publish_fsync");
    } else if (strcmp(name, "publish-dir-fsync") == 0) {
        case_publish(FIXTURE_FS_PUBLISH_DIR_FSYNC, "publish_dir_fsync");
    } else if (strcmp(name, "marker-partial-write") == 0) {
        case_add(1, FIXTURE_COPY_ABSENT, FIXTURE_ADD_FAIL, FIXTURE_FS_MARKER_WRITE, FIXTURE_PAUSE_NONE,
                 "lock_acquired,ui_get,ui_set_disable,ui_get_readback,sec_path,sec_path,sec_copy,marker_create,marker_write_partial,"
                 "ui_set_restore,ui_get_readback,lock_released",
                 -1, errSecParam, "marker_write", "expected_refusal", "injected_fs");
        expect(strcmp(g_marker, "partial") == 0);
        expect(strcmp(g_add, "not_called") == 0);
    } else if (strcmp(name, "marker-fsync-fail") == 0) {
        case_add(1, FIXTURE_COPY_ABSENT, FIXTURE_ADD_FAIL, FIXTURE_FS_MARKER_FSYNC, FIXTURE_PAUSE_NONE,
                 "lock_acquired,ui_get,ui_set_disable,ui_get_readback,sec_path,sec_path,sec_copy,marker_create,marker_fsync_fail,"
                 "ui_set_restore,ui_get_readback,lock_released",
                 -1, errSecParam, "marker_fsync", "expected_refusal", "injected_fs");
        expect(strcmp(g_marker, "present") == 0);
        expect(strcmp(g_add, "not_called") == 0);
    } else if (strcmp(name, "marker-dir-fsync-fail") == 0) {
        case_add(1, FIXTURE_COPY_ABSENT, FIXTURE_ADD_FAIL, FIXTURE_FS_MARKER_DIR_FSYNC, FIXTURE_PAUSE_NONE,
                 "lock_acquired,ui_get,ui_set_disable,ui_get_readback,sec_path,sec_path,sec_copy,marker_create,marker_fsync,"
                 "dir_fsync_fail,ui_set_restore,ui_get_readback,lock_released",
                 -1, errSecParam, "marker_dir_fsync", "expected_refusal", "injected_fs");
        expect(strcmp(g_marker, "present") == 0);
        expect(strcmp(g_add, "not_called") == 0);
    } else if (strcmp(name, "restart-first") == 0) {
        case_restart_first();
    } else if (strcmp(name, "restart-second") == 0) {
        case_add(1, FIXTURE_COPY_ABSENT, FIXTURE_ADD_FAIL, FIXTURE_FS_NONE, FIXTURE_PAUSE_NONE,
                 "lock_acquired,ui_get,ui_set_disable,ui_get_readback,sec_path,sec_path,sec_copy,ui_set_restore,ui_get_readback,"
                 "lock_released",
                 -1, errSecParam, "restart_second", "expected_refusal", "process_restart");
        expect(strcmp(g_marker, "present") == 0);
        expect(strcmp(g_add, "not_called") == 0);
        expect(strstr(g_order_buf, "marker_create") == NULL);
    } else {
        g_verdict = "test_failure";
        fail();
    }
    return emit(name);
}
