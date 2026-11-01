/* Compiled with -fno-objc-arc and -DOS_OBJECT_USE_OBJC=0. XPC retains stay manual. */

#include "auth.h"
#include "fixture_store.h"
#include "fixture_store_syntax.h"
#include "key_item.h"
#include "protocol.h"
#include "v10_crypt.h"

#include <dispatch/dispatch.h>
#include <os/lock.h>
#include <xpc/xpc.h>

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static struct key_state g_key;
static dispatch_queue_t g_control;
static dispatch_queue_t g_work;
static dispatch_queue_t g_deadline_queue;
static dispatch_source_t g_idle;
static dispatch_source_t g_deadline;
static uint64_t g_timer_generation;
static os_unfair_lock g_lock = OS_UNFAIR_LOCK_INIT;
static int g_connections;
static int g_admitted;
static int g_replied;
static uint64_t g_generation;
static uint64_t g_deadline_generation;
static xpc_object_t g_reply;
static xpc_connection_t g_peer;
static char g_parent_requirement[768];

struct job {
    char op[32];
    uint8_t *value;
    size_t value_len;
    int empty_profile;
    uint64_t generation;
};

static void arm_idle(void) {
    dispatch_source_set_timer(g_idle,
                              dispatch_time(DISPATCH_TIME_NOW, (int64_t)MNEMION_HELPER_IDLE_SECONDS * NSEC_PER_SEC),
                              DISPATCH_TIME_FOREVER, NSEC_PER_SEC);
}

static void cancel_owned_deadline(void) {
    if (g_deadline != NULL) {
        dispatch_source_cancel(g_deadline);
        dispatch_release(g_deadline);
        g_deadline = NULL;
    }
    g_timer_generation = 0;
}

static void on_deadline(uint64_t generation);

static void install_deadline(uint64_t generation, dispatch_time_t when) {
    dispatch_source_t source;
    int live;
    os_unfair_lock_lock(&g_lock);
    live = g_admitted && !g_replied && g_generation == generation && g_deadline_generation == generation;
    os_unfair_lock_unlock(&g_lock);
    if (!live) {
        return;
    }
    /* Replace whatever source is installed. Callers run this only for the
       request that currently owns admission, and only on g_deadline_queue. */
    cancel_owned_deadline();
    source = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, g_deadline_queue);
    if (source == NULL) {
        on_deadline(generation);
        return;
    }
    g_deadline = source;
    g_timer_generation = generation;
    dispatch_source_set_event_handler(source, ^{
        on_deadline(generation);
    });
    dispatch_source_set_timer(source, when, DISPATCH_TIME_FOREVER, 50 * NSEC_PER_MSEC);
    dispatch_resume(source);
}

static void arm_deadline(uint64_t generation, int timeout_ms) {
    dispatch_time_t when = dispatch_time(DISPATCH_TIME_NOW, (int64_t)timeout_ms * NSEC_PER_MSEC);
    dispatch_async(g_deadline_queue, ^{
        install_deadline(generation, when);
    });
}

static void disarm_deadline(uint64_t generation) {
    dispatch_async(g_deadline_queue, ^{
        if (g_timer_generation != generation) {
            return;
        }
        cancel_owned_deadline();
    });
}

static int64_t call_count(void) {
    return (int64_t)atomic_load_explicit(&g_key.keychain_calls, memory_order_relaxed);
}

static void send_now(xpc_connection_t peer, xpc_object_t event, const char *result) {
    xpc_object_t reply = xpc_dictionary_create_reply(event);
    if (reply == NULL) {
        return;
    }
    xpc_dictionary_set_string(reply, "result", result);
    xpc_dictionary_set_int64(reply, "keychain_calls", call_count());
    xpc_connection_send_message(peer, reply);
    xpc_release(reply);
}

static int allowed_key(const char *key) {
    /* Service, account, and store path are not request fields.
       empty_profile is accepted and is not a store or ciphertext proof. */
    return strcmp(key, "op") == 0 || strcmp(key, "value") == 0 || strcmp(key, "empty_profile") == 0;
}

static int frame_ok(xpc_object_t event, const char **op, const uint8_t **value, size_t *value_len, int *empty_profile) {
    __block int extra = 0;
    const char *operation;
    size_t length = 0;
    const uint8_t *data = NULL;
    *op = NULL;
    *value = NULL;
    *value_len = 0;
    *empty_profile = 0;
    xpc_dictionary_apply(event, ^bool(const char *key, xpc_object_t item) {
        (void)item;
        if (!allowed_key(key)) {
            extra = 1;
            return false;
        }
        return true;
    });
    if (extra) {
        return -1;
    }
    operation = xpc_dictionary_get_string(event, "op");
    if (operation == NULL) {
        return -1;
    }
    if (xpc_dictionary_get_value(event, "value") != NULL) {
        if (xpc_get_type(xpc_dictionary_get_value(event, "value")) != XPC_TYPE_DATA) {
            return -1;
        }
        data = xpc_dictionary_get_data(event, "value", &length);
        if (data == NULL || length > MNEMION_MAX_CIPHERTEXT) {
            return -1;
        }
    }
    if (xpc_dictionary_get_value(event, "empty_profile") != NULL) {
        if (xpc_get_type(xpc_dictionary_get_value(event, "empty_profile")) != XPC_TYPE_BOOL ||
            strcmp(operation, "seal") != 0) {
            return -1;
        }
        *empty_profile = xpc_dictionary_get_bool(event, "empty_profile") ? 1 : 0;
    }
    if (strcmp(operation, "availability") == 0) {
        if (data != NULL) {
            return -1;
        }
    } else if (strcmp(operation, "seal") == 0) {
        if (data == NULL || length == 0 || length > MNEMION_MAX_VALUE) {
            return -1;
        }
    } else if (strcmp(operation, "open") == 0) {
        if (data == NULL || length < 19 || length > MNEMION_MAX_CIPHERTEXT) {
            return -1;
        }
    } else {
        return -1;
    }
    *op = operation;
    *value = data;
    *value_len = length;
    return 0;
}

static const char *result_name(enum key_result result) {
    switch (result) {
    case KEY_OK:
        return "ok";
    case KEY_ABSENT:
        return "missing_key";
    case KEY_DENIED:
        return "denied";
    case KEY_LOCKED:
        return "locked";
    case KEY_UNAVAILABLE:
        return "unavailable";
    }
    return "internal";
}

static int payload_acceptable(const char *op, const uint8_t *value, size_t value_len) {
    if (strcmp(op, "seal") == 0) {
        return v10_utf8(value, value_len) == 0 && v10_seal_bounds(value_len) == 0;
    }
    if (strcmp(op, "open") == 0) {
        return v10_ciphertext_bounds(value, value_len) == 0;
    }
    return 1;
}

static enum key_result ensure_key(int allow_create, int caller_claims_absent) {
    enum key_result result;
    if (g_key.derived_valid) {
        return KEY_OK;
    }
    result = key_item_load(&g_key);
    if (result == KEY_OK) {
        return KEY_OK;
    }
    /* allow_create only starts the one-time transaction. The claim is not
       evidence that the ciphertext directory is empty or that the key is absent. */
    if (result == KEY_ABSENT && allow_create) {
        return key_item_create_empty(&g_key, caller_claims_absent);
    }
    key_state_zero(&g_key);
    return result;
}

static void publish_reply(uint64_t generation, const char *result, const void *value, size_t value_len) {
    xpc_object_t reply = NULL;
    xpc_connection_t peer = NULL;
    os_unfair_lock_lock(&g_lock);
    if (g_admitted && !g_replied && g_generation == generation && g_reply != NULL && g_peer != NULL) {
        reply = g_reply;
        peer = g_peer;
        g_reply = NULL;
        g_peer = NULL;
        g_replied = 1;
        g_admitted = 0;
        g_deadline_generation = 0;
    }
    os_unfair_lock_unlock(&g_lock);
    if (reply == NULL) {
        return;
    }
    disarm_deadline(generation);
    xpc_dictionary_set_string(reply, "result", result);
    xpc_dictionary_set_int64(reply, "keychain_calls", call_count());
    if (strcmp(result, "ok") == 0 && value != NULL && value_len > 0) {
        xpc_dictionary_set_data(reply, "value", value, value_len);
    }
    xpc_connection_send_message(peer, reply);
    xpc_release(reply);
    xpc_release(peer);
    arm_idle();
}

static void on_deadline(uint64_t generation) {
    xpc_object_t reply = NULL;
    xpc_connection_t peer = NULL;
    int64_t calls;
    os_unfair_lock_lock(&g_lock);
    calls = call_count();
    if (g_admitted && !g_replied && g_reply != NULL && g_peer != NULL &&
        g_generation == generation && g_deadline_generation == generation) {
        reply = g_reply;
        peer = g_peer;
        g_reply = NULL;
        g_peer = NULL;
        g_replied = 1;
        g_admitted = 0;
        g_deadline_generation = 0;
    }
    os_unfair_lock_unlock(&g_lock);
    if (reply == NULL) {
        return;
    }
    xpc_dictionary_set_string(reply, "result", "timeout");
    xpc_dictionary_set_int64(reply, "keychain_calls", calls);
    xpc_connection_send_message(peer, reply);
    xpc_connection_send_barrier(peer, ^{
        _exit(2);
    });
    xpc_release(reply);
    xpc_release(peer);
}

static void perform(struct job *job) {
    uint8_t output[MNEMION_MAX_CIPHERTEXT];
    size_t output_len = 0;
    const char *name = "internal";
    const void *payload = NULL;
    size_t payload_len = 0;
    enum key_result loaded = KEY_UNAVAILABLE;
    memset(output, 0, sizeof output);
    if (strcmp(job->op, "availability") == 0) {
        if (g_key.derived_valid) {
            name = "ok";
        } else {
            loaded = key_item_load(&g_key);
            if (loaded != KEY_OK) {
                key_state_zero(&g_key);
            }
            name = result_name(loaded);
        }
    } else if (strcmp(job->op, "seal") == 0) {
        loaded = ensure_key(1, job->empty_profile);
        if (loaded != KEY_OK) {
            name = result_name(loaded);
        } else if (v10_seal(g_key.derived, job->value, job->value_len, output, sizeof output, &output_len) != 0 ||
                   output_len == 0 || v10_ciphertext_bounds(output, output_len) != 0) {
            name = "rejected";
        } else if (fixture_store_publish_ciphertext(output, output_len) != 0) {
            name = "unavailable";
        } else {
            name = "ok";
            payload = output;
            payload_len = output_len;
        }
    } else if (strcmp(job->op, "open") == 0) {
        loaded = ensure_key(0, job->empty_profile);
        if (loaded != KEY_OK) {
            name = result_name(loaded);
        } else if (v10_open(g_key.derived, job->value, job->value_len, output, sizeof output, &output_len) != 0 ||
                   output_len == 0 || output_len > MNEMION_MAX_VALUE) {
            name = "rejected";
        } else {
            name = "ok";
            payload = output;
            payload_len = output_len;
        }
    }
    publish_reply(job->generation, name, payload, payload_len);
    mnemion_zero(output, sizeof output);
    if (job->value != NULL) {
        mnemion_zero(job->value, job->value_len);
        free(job->value);
    }
    free(job);
}

static void discard_job(struct job *job) {
    if (job == NULL) {
        return;
    }
    if (job->value != NULL) {
        mnemion_zero(job->value, job->value_len);
        free(job->value);
    }
    free(job);
}

static int admit_job(xpc_connection_t peer, xpc_object_t reply, struct job *job, int timeout_ms) {
    int admitted = 0;
    os_unfair_lock_lock(&g_lock);
    if (!g_admitted && g_reply == NULL) {
        g_admitted = 1;
        g_replied = 0;
        g_generation++;
        g_deadline_generation = g_generation;
        g_reply = reply;
        g_peer = peer;
        xpc_retain(g_reply);
        xpc_retain(g_peer);
        job->generation = g_generation;
        admitted = 1;
    }
    os_unfair_lock_unlock(&g_lock);
    if (!admitted) {
        return -1;
    }
    arm_deadline(job->generation, timeout_ms);
    dispatch_async(g_work, ^{
        perform(job);
    });
    return 0;
}

static int make_job(const char *op, const uint8_t *value, size_t value_len, int empty_profile, struct job **out) {
    struct job *job = calloc(1, sizeof *job);
    if (job == NULL) {
        return -1;
    }
    if (op == NULL || strlen(op) >= sizeof job->op) {
        free(job);
        return -1;
    }
    memcpy(job->op, op, strlen(op) + 1);
    job->empty_profile = empty_profile;
    if (value_len > 0) {
        job->value = malloc(value_len);
        if (job->value == NULL) {
            free(job);
            return -1;
        }
        memcpy(job->value, value, value_len);
        job->value_len = value_len;
    }
    *out = job;
    return 0;
}

static void handle_event(xpc_connection_t peer, xpc_object_t event) {
    const char *op = NULL;
    const uint8_t *value = NULL;
    size_t value_len = 0;
    int empty_profile = 0;
    int timeout_ms;
    struct job *job = NULL;
    xpc_object_t reply;
    if (event == XPC_ERROR_CONNECTION_INVALID) {
        g_connections--;
        if (g_connections <= 0) {
            key_state_zero(&g_key);
            _exit(0);
        }
        return;
    }
    if (xpc_get_type(event) != XPC_TYPE_DICTIONARY) {
        return;
    }
    if (frame_ok(event, &op, &value, &value_len, &empty_profile) != 0 ||
        payload_acceptable(op, value, value_len) == 0) {
        send_now(peer, event, "bad_frame");
        return;
    }
    if (auth_check_xpc_sender(event, peer, g_parent_requirement) != 0) {
        send_now(peer, event, "unauthorized");
        return;
    }
    if (make_job(op, value, value_len, empty_profile, &job) != 0) {
        send_now(peer, event, "internal");
        return;
    }
    reply = xpc_dictionary_create_reply(event);
    if (reply == NULL) {
        discard_job(job);
        return;
    }
    /* Idle moves only after the sender is authenticated. */
    arm_idle();
    timeout_ms = strcmp(op, "availability") == 0 ? MNEMION_HELPER_CHECK_DEADLINE_MS
                                                  : MNEMION_HELPER_OPERATION_DEADLINE_MS;
    if (admit_job(peer, reply, job, timeout_ms) != 0) {
        xpc_dictionary_set_string(reply, "result", "busy");
        xpc_dictionary_set_int64(reply, "keychain_calls", call_count());
        xpc_connection_send_message(peer, reply);
        xpc_release(reply);
        discard_job(job);
        return;
    }
    xpc_release(reply);
}

static void new_peer(xpc_connection_t peer) {
    dispatch_sync(g_control, ^{
        g_connections++;
    });
    xpc_connection_set_target_queue(peer, g_control);
    xpc_connection_set_event_handler(peer, ^(xpc_object_t event) {
        handle_event(peer, event);
    });
    xpc_connection_resume(peer);
}

int main(int argc, char **argv) {
    if (auth_caller_pin_shape_ok() != 0) {
        fprintf(stderr, "pin_rejected\n");
        return 1;
    }
    if (auth_pins_compile_only()) {
        fprintf(stderr, "compile_only_pins\n");
        return 3;
    }
    if (fixture_store_runtime_allowed() != 0) {
        fprintf(stderr, "store_config_rejected\n");
        return 1;
    }
    /* Normal launchd startup has no extra argument. The sealed header is the
       run. Extra argv is refused. Environment and XPC fields are not read. */
    if (fixture_syntax_helper_launch(argc, NULL, NULL) != FIXTURE_SYNTAX_OK || fixture_store_bind() != 0) {
        fprintf(stderr, "store_refused\n");
        return 1;
    }
    (void)argv;
    key_state_init(&g_key);
    if (auth_build_parent_requirement(g_parent_requirement, sizeof g_parent_requirement) != 0) {
        return 1;
    }
    g_control = dispatch_queue_create("com.perseusxr.mnemion-studio.credential-helper.control", DISPATCH_QUEUE_SERIAL);
    g_work = dispatch_queue_create("com.perseusxr.mnemion-studio.credential-helper.work", DISPATCH_QUEUE_SERIAL);
    g_deadline_queue = dispatch_queue_create("com.perseusxr.mnemion-studio.credential-helper.deadline", DISPATCH_QUEUE_SERIAL);
    g_idle = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, g_control);
    if (g_control == NULL || g_work == NULL || g_deadline_queue == NULL || g_idle == NULL) {
        return 1;
    }
    dispatch_source_set_event_handler(g_idle, ^{
        int busy;
        os_unfair_lock_lock(&g_lock);
        busy = g_admitted;
        os_unfair_lock_unlock(&g_lock);
        if (busy) {
            return;
        }
        key_state_zero(&g_key);
        _exit(0);
    });
    arm_idle();
    dispatch_resume(g_idle);
    xpc_main(new_peer);
    return 0;
}
