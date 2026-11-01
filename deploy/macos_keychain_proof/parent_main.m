/* Compiled with -fno-objc-arc and -DOS_OBJECT_USE_OBJC=0. XPC retains stay manual.
   Reply state is heap-owned. It stays allocated until process exit so a late
   callback, including one blocked in Security validation, sees the closed flag
   and cannot write through the stack result. The waiter does not join that queue. */

#include "auth.h"
#include "bundle_manifest.h"
#include "exact_helper.h"
#include "fixture_store.h"
#include "parent_pin.h"
#include "protocol.h"
#include "signing.h"
#include "v10_crypt.h"

#include <CoreFoundation/CoreFoundation.h>
#include <Security/Security.h>
#include <dispatch/dispatch.h>
#include <os/lock.h>
#include <xpc/xpc.h>

#include <mach-o/dyld.h>

#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

enum {
    OP_AVAILABILITY = 1,
    OP_SEAL = 2,
    OP_OPEN = 3,
    OP_NEGATIVE = 4,
    OP_DROP = 5
};

struct reply_box {
    char result[64];
    int64_t calls;
    uint8_t *value;
    size_t value_len;
};

struct reply_owner {
    os_unfair_lock lock;
    dispatch_semaphore_t settled;
    int closed;
    int done;
    int op_kind;
    char result[64];
    int64_t calls;
    uint8_t *value;
    size_t value_len;
    char helper_requirement[768];
};

static void usage(void) {
    fprintf(stderr, "usage: parent check-helper|availability|seal|open|framing-unknown|framing-oversize|drop|direct-lookup [sealed-run]\n");
}

static void emit(const char *result, long long calls) {
    printf("result=%s\nkeychain_calls=%lld\n", result, calls);
    fflush(stdout);
}

static void release_box(struct reply_box *box) {
    if (box == NULL) {
        return;
    }
    mnemion_zero(box->value, box->value_len);
    free(box->value);
    box->value = NULL;
    box->value_len = 0;
}

static int bundle_root(char *buffer, size_t capacity) {
    char executable[4096];
    uint32_t size = sizeof executable;
    char *marker;
    if (_NSGetExecutablePath(executable, &size) != 0) {
        return -1;
    }
    marker = strstr(executable, "/Contents/MacOS/");
    if (marker == NULL) {
        return -1;
    }
    *marker = '\0';
    if (strlen(executable) + 1 > capacity) {
        return -1;
    }
    memcpy(buffer, executable, strlen(executable) + 1);
    return 0;
}

static int verify_helper(const char *bundle, char *helper_requirement, size_t requirement_cap) {
    char helper[4096];
    char digest[65];
    char error[256];
    char cdhash[160];
    char identifier[256];
    char designated[1024];
    int length;
    length = snprintf(helper, sizeof helper, "%s/Contents/XPCServices/MnemionCredentialHelper.xpc", bundle);
    if (length < 0 || (size_t)length >= sizeof helper) {
        return -1;
    }
    if (auth_caller_pin_shape_ok() != 0 || auth_exact_helper_pin_shape_ok() != 0 ||
        auth_build_helper_requirement(helper_requirement, requirement_cap) != 0) {
        return -1;
    }
    /* Manifest, cdhash, identifier, and designated requirement are sealed
       into this parent. A resource file beside the helper is not the pin. */
    if (bundle_manifest_digest(helper, digest, sizeof digest, error, sizeof error) != 0) {
        return -1;
    }
    if (strcmp(digest, MNEMION_HELPER_MANIFEST_SHA256) != 0) {
        return -1;
    }
    if (auth_check_bundle(helper, helper_requirement) != 0) {
        return -1;
    }
    if (signing_describe(helper, cdhash, sizeof cdhash, identifier, sizeof identifier,
                         designated, sizeof designated) != 0) {
        return -1;
    }
    if (strcmp(cdhash, MNEMION_HELPER_CDHASH) != 0 ||
        strcmp(identifier, MNEMION_HELPER_IDENTIFIER) != 0 ||
        strcmp(identifier, MNEMION_SEALED_HELPER_IDENTIFIER) != 0 ||
        strcmp(designated, MNEMION_HELPER_DESIGNATED) != 0) {
        return -1;
    }
    return 0;
}

static int known_failure(const char *result, int op_kind) {
    if (strcmp(result, "bad_frame") == 0 || strcmp(result, "unauthorized") == 0 ||
        strcmp(result, "busy") == 0 || strcmp(result, "timeout") == 0 ||
        strcmp(result, "missing_key") == 0 || strcmp(result, "denied") == 0 ||
        strcmp(result, "locked") == 0 || strcmp(result, "unavailable") == 0) {
        return 0;
    }
    if ((op_kind == OP_SEAL || op_kind == OP_OPEN) && strcmp(result, "rejected") == 0) {
        return 0;
    }
    return -1;
}

static int parent_schema(xpc_object_t event, int op_kind, char *result, int64_t *calls,
                         uint8_t **value_out, size_t *value_len) {
    __block int count = 0;
    __block int unknown = 0;
    const char *text;
    xpc_object_t calls_obj;
    xpc_object_t raw;
    size_t length = 0;
    const void *data = NULL;
    uint8_t *copied;
    int expect;
    *value_out = NULL;
    *value_len = 0;
    if (event == NULL || xpc_get_type(event) != XPC_TYPE_DICTIONARY) {
        return -1;
    }
    xpc_dictionary_apply(event, ^bool(const char *key, xpc_object_t item) {
        (void)item;
        count++;
        if (strcmp(key, "result") != 0 && strcmp(key, "keychain_calls") != 0 && strcmp(key, "value") != 0) {
            unknown = 1;
            return false;
        }
        return true;
    });
    text = xpc_dictionary_get_string(event, "result");
    calls_obj = xpc_dictionary_get_value(event, "keychain_calls");
    raw = xpc_dictionary_get_value(event, "value");
    if (text == NULL || calls_obj == NULL || unknown) {
        return -1;
    }
    if (strlen(text) == 0 || strlen(text) >= 64 || strchr(text, '\n') != NULL || strchr(text, '\r') != NULL) {
        return -1;
    }
    if (xpc_get_type(calls_obj) != XPC_TYPE_INT64) {
        return -1;
    }
    *calls = xpc_int64_get_value(calls_obj);
    if (*calls < 0) {
        return -1;
    }
    if (raw != NULL) {
        if (xpc_get_type(raw) != XPC_TYPE_DATA) {
            return -1;
        }
        data = xpc_dictionary_get_data(event, "value", &length);
        if (data == NULL) {
            return -1;
        }
    }
    expect = raw == NULL ? 2 : 3;
    if (count != expect) {
        return -1;
    }
    if (strcmp(text, "ok") == 0) {
        if (op_kind == OP_AVAILABILITY) {
            if (raw != NULL) {
                return -1;
            }
        } else if (op_kind == OP_SEAL) {
            if (data == NULL || v10_ciphertext_bounds((const uint8_t *)data, length) != 0) {
                return -1;
            }
        } else if (op_kind == OP_OPEN) {
            if (data == NULL || length == 0 || length > MNEMION_MAX_VALUE) {
                return -1;
            }
        } else {
            return -1;
        }
    } else {
        if (raw != NULL || known_failure(text, op_kind) != 0) {
            return -1;
        }
    }
    if (data != NULL) {
        copied = malloc(length);
        if (copied == NULL) {
            return -1;
        }
        memcpy(copied, data, length);
        *value_out = copied;
        *value_len = length;
    }
    memcpy(result, text, strlen(text) + 1);
    return 0;
}

static void parent_settle(struct reply_owner *owner, const char *result, int64_t calls,
                          uint8_t *value, size_t value_len) {
    int won = 0;
    os_unfair_lock_lock(&owner->lock);
    if (!owner->closed && !owner->done && result != NULL && strlen(result) < sizeof owner->result) {
        owner->done = 1;
        memcpy(owner->result, result, strlen(result) + 1);
        owner->calls = calls;
        owner->value = value;
        owner->value_len = value_len;
        won = 1;
    }
    os_unfair_lock_unlock(&owner->lock);
    if (won) {
        dispatch_semaphore_signal(owner->settled);
        return;
    }
    mnemion_zero(value, value_len);
    free(value);
}

static void parent_on_event(struct reply_owner *owner, xpc_object_t event) {
    if (event == XPC_ERROR_CONNECTION_INVALID || event == XPC_ERROR_CONNECTION_INTERRUPTED) {
        parent_settle(owner, "unreachable", -1, NULL, 0);
    }
}

static void parent_on_reply(struct reply_owner *owner, xpc_connection_t connection, xpc_object_t event) {
    int ignore;
    char result[64];
    int64_t calls = -1;
    uint8_t *value = NULL;
    size_t value_len = 0;
    os_unfair_lock_lock(&owner->lock);
    ignore = owner->closed || owner->done;
    os_unfair_lock_unlock(&owner->lock);
    if (ignore) {
        return;
    }
    if (event == XPC_ERROR_CONNECTION_INVALID || event == XPC_ERROR_CONNECTION_INTERRUPTED ||
        xpc_get_type(event) == XPC_TYPE_ERROR) {
        parent_settle(owner, "unreachable", -1, NULL, 0);
        return;
    }
    if (auth_check_xpc_sender(event, connection, owner->helper_requirement) != 0) {
        parent_settle(owner, "helper_untrusted", -1, NULL, 0);
        return;
    }
    if (parent_schema(event, owner->op_kind, result, &calls, &value, &value_len) != 0) {
        mnemion_zero(value, value_len);
        free(value);
        parent_settle(owner, "bad_reply", -1, NULL, 0);
        return;
    }
    parent_settle(owner, result, calls, value, value_len);
}

static int roundtrip(const char *requirement, xpc_object_t message, int timeout_ms, int op_kind, struct reply_box *box) {
    struct reply_owner *owner = calloc(1, sizeof *owner);
    xpc_connection_t connection = NULL;
    dispatch_queue_t callbacks = NULL;
    memset(box, 0, sizeof *box);
    if (owner == NULL || requirement == NULL) {
        free(owner);
        memcpy(box->result, "internal", 9);
        box->calls = -1;
        return 1;
    }
    if (strlen(requirement) >= sizeof owner->helper_requirement) {
        free(owner);
        memcpy(box->result, "internal", 9);
        box->calls = -1;
        return 1;
    }
    owner->lock = OS_UNFAIR_LOCK_INIT;
    owner->op_kind = op_kind;
    memcpy(owner->helper_requirement, requirement, strlen(requirement) + 1);
    owner->settled = dispatch_semaphore_create(0);
    connection = xpc_connection_create(MNEMION_HELPER_SERVICE, NULL);
    callbacks = dispatch_queue_create("com.perseusxr.mnemion-studio.proof.reply", DISPATCH_QUEUE_SERIAL);
    if (owner->settled == NULL || connection == NULL || callbacks == NULL) {
        if (connection != NULL) {
            xpc_release(connection);
        }
        if (callbacks != NULL) {
            dispatch_release(callbacks);
        }
        if (owner->settled != NULL) {
            dispatch_release(owner->settled);
        }
        free(owner);
        memcpy(box->result, "unreachable", 12);
        box->calls = -1;
        return 1;
    }
    xpc_connection_set_target_queue(connection, callbacks);
    xpc_connection_set_event_handler(connection, ^(xpc_object_t event) {
        parent_on_event(owner, event);
    });
    xpc_connection_resume(connection);
    if (message != NULL) {
        xpc_connection_send_message_with_reply(connection, message, callbacks, ^(xpc_object_t reply) {
            parent_on_reply(owner, connection, reply);
        });
    } else {
        xpc_connection_cancel(connection);
    }
    if (dispatch_semaphore_wait(owner->settled, dispatch_time(DISPATCH_TIME_NOW, (int64_t)timeout_ms * NSEC_PER_MSEC)) != 0) {
        parent_settle(owner, "timeout", -1, NULL, 0);
        xpc_connection_cancel(connection);
    }
    /* The semaphore says the deadline expired or a reply won. It does not mean
       the callback queue is idle. Joining it would wait behind Security
       validation. Copy under the lock instead. owner, connection, and
       callbacks stay allocated so that in-flight callback can still run. */
    os_unfair_lock_lock(&owner->lock);
    owner->closed = 1;
    if (owner->result[0] == '\0') {
        memcpy(owner->result, "unreachable", 12);
        owner->calls = -1;
    }
    memcpy(box->result, owner->result, sizeof box->result);
    box->calls = owner->calls;
    box->value = owner->value;
    box->value_len = owner->value_len;
    owner->value = NULL;
    owner->value_len = 0;
    os_unfair_lock_unlock(&owner->lock);
    xpc_connection_cancel(connection);
    return strcmp(box->result, "ok") == 0 ? 0 : 1;
}

static int read_bounded(const char *path, uint8_t *buffer, size_t capacity, size_t *length, size_t minimum) {
    int fd = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    size_t filled = 0;
    if (fd < 0) {
        return -1;
    }
    while (filled < capacity) {
        ssize_t count = read(fd, buffer + filled, capacity - filled);
        if (count < 0) {
            close(fd);
            return -1;
        }
        if (count == 0) {
            break;
        }
        filled += (size_t)count;
    }
    if (read(fd, &(char){0}, 1) == 1) {
        close(fd);
        mnemion_zero(buffer, capacity);
        return -1;
    }
    close(fd);
    if (filled < minimum || filled > capacity) {
        mnemion_zero(buffer, capacity);
        return -1;
    }
    *length = filled;
    return 0;
}

static int write_new(const char *path, const uint8_t *bytes, size_t length) {
    int fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    size_t filled = 0;
    if (fd < 0 || length == 0) {
        if (fd >= 0) {
            close(fd);
            unlink(path);
        }
        return -1;
    }
    while (filled < length) {
        ssize_t count = write(fd, bytes + filled, length - filled);
        if (count <= 0) {
            close(fd);
            unlink(path);
            return -1;
        }
        filled += (size_t)count;
    }
    if (fsync(fd) != 0 || close(fd) != 0) {
        unlink(path);
        return -1;
    }
    return 0;
}

/* Proof fixture only. Binds the sealed run, not a caller-selected store.
   This command is not a product feature and not native acceptance. */
static int direct_lookup(void) {
    CFDataRef found = NULL;
    OSStatus status = errSecParam;
    int invoked = 0;
    const char *name = "unavailable";
    if (fixture_store_runtime_allowed() != 0 || fixture_store_bind() != 0) {
        fprintf(stderr, "store_refused\n");
        printf("result=unavailable\nkeychain_calls=0\n");
        return 1;
    }
    if (fixture_store_copy_matching(&found, &status, &invoked) != 0) {
        if (found != NULL) {
            CFRelease(found);
        }
        fprintf(stderr, "store_refused\n");
        printf("result=unavailable\nkeychain_calls=%d\n", invoked);
        return 1;
    }
    fprintf(stderr, "direct_lookup=interaction_bracket\n");
    if (status == errSecSuccess) {
        /* The password bytes are released with the process. They are not printed. */
        name = "ok";
    } else if (status == errSecItemNotFound) {
        name = "missing_key";
    } else if (status == errSecUserCanceled || status == errSecAuthFailed) {
        name = "denied";
    } else if (status == errSecInteractionNotAllowed || status == errSecNotAvailable) {
        name = "locked";
    }
    if (found != NULL) {
        CFRelease(found);
    }
    printf("result=%s\nkeychain_calls=%d\n", name, invoked);
    return strcmp(name, "ok") == 0 ? 0 : 1;
}

static int finish_transfer(struct reply_box *box, xpc_object_t message, const char *output, int as_ciphertext) {
    int status = strcmp(box->result, "ok") == 0 ? 0 : 1;
    if (status == 0) {
        int bounds_ok = box->value != NULL && box->value_len > 0 &&
                        (as_ciphertext ? v10_ciphertext_bounds(box->value, box->value_len) == 0
                                       : box->value_len <= MNEMION_MAX_VALUE);
        if (!bounds_ok || write_new(output, box->value, box->value_len) != 0) {
            memcpy(box->result, "internal", 9);
            status = 1;
        }
    }
    emit(box->result, box->calls);
    release_box(box);
    xpc_release(message);
    return status;
}

int main(int argc, char **argv) {
    char bundle[4096];
    char helper_requirement[768];
    struct reply_box box;
    xpc_object_t message;
    const char *command;
    int status;
    if (auth_caller_pin_shape_ok() != 0 || auth_exact_helper_pin_shape_ok() != 0) {
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
    if (argc < 2) {
        usage();
        return 2;
    }
    command = argv[1];
    if (strcmp(command, "direct-lookup") == 0) {
        if (argc == 3 && fixture_store_argument_matches_seal(argv[2]) != 0) {
            fprintf(stderr, "store_refused\n");
            printf("result=unavailable\nkeychain_calls=0\n");
            return 1;
        }
        if (argc != 2 && argc != 3) {
            usage();
            return 2;
        }
        return direct_lookup();
    }
    if (bundle_root(bundle, sizeof bundle) != 0 ||
        verify_helper(bundle, helper_requirement, sizeof helper_requirement) != 0) {
        emit("helper_untrusted", -1);
        return 4;
    }
    if (strcmp(command, "check-helper") == 0 && argc == 2) {
        emit("ok", 0);
        return 0;
    }
    memset(&box, 0, sizeof box);
    if (strcmp(command, "drop") == 0 && argc == 2) {
        status = roundtrip(helper_requirement, NULL, MNEMION_CHECK_TIMEOUT_MS, OP_DROP, &box);
        emit(box.result[0] ? box.result : "unreachable", box.calls);
        release_box(&box);
        return status == 0 ? 1 : status;
    }
    message = xpc_dictionary_create(NULL, NULL, 0);
    if (message == NULL) {
        return 1;
    }
    if (strcmp(command, "availability") == 0 && argc == 2) {
        xpc_dictionary_set_string(message, "op", "availability");
        roundtrip(helper_requirement, message, MNEMION_CHECK_TIMEOUT_MS, OP_AVAILABILITY, &box);
        emit(box.result, box.calls);
        status = strcmp(box.result, "ok") == 0 ? 0 : 1;
        release_box(&box);
        xpc_release(message);
        return status;
    }
    if (strcmp(command, "framing-unknown") == 0 && argc == 2) {
        xpc_dictionary_set_string(message, "op", "no-such");
        roundtrip(helper_requirement, message, MNEMION_CHECK_TIMEOUT_MS, OP_NEGATIVE, &box);
        emit(box.result, box.calls);
        release_box(&box);
        xpc_release(message);
        return 1;
    }
    if (strcmp(command, "framing-oversize") == 0 && argc == 2) {
        uint8_t *oversized = calloc(MNEMION_MAX_VALUE + 1, 1);
        if (oversized == NULL) {
            xpc_release(message);
            return 1;
        }
        memset(oversized, 'a', MNEMION_MAX_VALUE + 1);
        xpc_dictionary_set_string(message, "op", "seal");
        xpc_dictionary_set_data(message, "value", oversized, MNEMION_MAX_VALUE + 1);
        free(oversized);
        roundtrip(helper_requirement, message, MNEMION_CHECK_TIMEOUT_MS, OP_NEGATIVE, &box);
        emit(box.result, box.calls);
        release_box(&box);
        xpc_release(message);
        return 1;
    }
    if (strcmp(command, "seal") == 0 && (argc == 4 || (argc == 5 && strcmp(argv[2], "--empty-profile") == 0))) {
        /* --empty-profile does not name a store and is not evidence the directory is empty. */
        int empty = argc == 5;
        const char *input = argv[empty ? 3 : 2];
        const char *output = argv[empty ? 4 : 3];
        uint8_t plaintext[MNEMION_MAX_VALUE];
        size_t length = 0;
        if (read_bounded(input, plaintext, sizeof plaintext, &length, 1) != 0) {
            mnemion_zero(plaintext, sizeof plaintext);
            xpc_release(message);
            return 1;
        }
        xpc_dictionary_set_string(message, "op", "seal");
        xpc_dictionary_set_data(message, "value", plaintext, length);
        if (empty) {
            xpc_dictionary_set_bool(message, "empty_profile", true);
        }
        mnemion_zero(plaintext, sizeof plaintext);
        roundtrip(helper_requirement, message, MNEMION_OPERATION_TIMEOUT_MS, OP_SEAL, &box);
        return finish_transfer(&box, message, output, 1);
    }
    if (strcmp(command, "open") == 0 && argc == 4) {
        uint8_t ciphertext[MNEMION_MAX_CIPHERTEXT];
        size_t length = 0;
        if (read_bounded(argv[2], ciphertext, sizeof ciphertext, &length, 19) != 0) {
            xpc_release(message);
            return 1;
        }
        xpc_dictionary_set_string(message, "op", "open");
        xpc_dictionary_set_data(message, "value", ciphertext, length);
        mnemion_zero(ciphertext, sizeof ciphertext);
        roundtrip(helper_requirement, message, MNEMION_OPERATION_TIMEOUT_MS, OP_OPEN, &box);
        return finish_transfer(&box, message, argv[3], 0);
    }
    xpc_release(message);
    usage();
    return 2;
}
