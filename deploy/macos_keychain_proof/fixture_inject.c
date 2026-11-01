#include "fixture_inject.h"

#if !defined(MNEMION_FIXTURE_INJECT)
#error "fixture_inject.c is the fake Security boundary and is not part of the helper"
#endif

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Every Security entry point the fixture can reach is implemented here.
   An unconfigured call is counted and failed. None of these functions call
   SecItem, SecKeychain, or SecRandom. */

static int g_prior = 1;
static int g_allowed = 1;
static int g_observed_prior = -1;
static int g_fault = FIXTURE_FAULT_NONE;
static int g_fault_bracket = -1;
static int g_bracket = 0;
static int g_gets = 0;
static int g_sets = 0;
static int g_allow_ui = 0;
static int g_allow_open = 0;
static int g_allow_path = 0;
static int g_allow_item = 0;
static int g_allow_copy = 0;
static int g_allow_add = 0;
static int g_copy_kind = FIXTURE_COPY_ABSENT;
static int g_add_kind = FIXTURE_ADD_FAIL;
static int g_fs = FIXTURE_FS_NONE;
static int g_fs_used = 0;
static int g_pause = FIXTURE_PAUSE_NONE;
static int g_ready_fd = -1;
static int g_hold_fd = -1;
static int g_native = 0;
static int g_unconfigured = 0;
static int g_data_ops = 0;
static int g_query_rejects = 0;
static int g_issued = 0;
static int g_disposed = 0;
static int g_order_truncated = 0;
static CFTypeRef g_opened = NULL;
static CFAllocatorRef g_allocator = NULL;
static char g_open_path[1024];
static char g_order[1600];

static const uint8_t k_synthetic[] = {'f', 'i', 'x', 't', 'u', 'r', 'e', '-', 's', 'y', 'n', 't', 'h', 'e',
                                      't', 'i', 'c', '-', '0', '0', '0', '0', '0', '0'};

static void *alloc_cb(CFIndex size, CFOptionFlags hint, void *info) {
    (void)hint;
    (void)info;
    if (size <= 0) {
        return NULL;
    }
    return malloc((size_t)size);
}

static void *realloc_cb(void *ptr, CFIndex size, CFOptionFlags hint, void *info) {
    (void)hint;
    (void)info;
    if (size <= 0) {
        return NULL;
    }
    return realloc(ptr, (size_t)size);
}

static void free_cb(void *ptr, void *info) {
    size_t *header;
    size_t length;
    (void)info;
    if (ptr == NULL) {
        return;
    }
    header = ((size_t *)ptr) - 1;
    length = header[0];
    memset(ptr, 0, length);
    free(header);
    g_disposed++;
}

static void ensure_allocator(void) {
    CFAllocatorContext context;
    if (g_allocator != NULL) {
        return;
    }
    memset(&context, 0, sizeof context);
    context.version = 0;
    context.allocate = alloc_cb;
    context.reallocate = realloc_cb;
    context.deallocate = free_cb;
    g_allocator = CFAllocatorCreate(kCFAllocatorDefault, &context);
}

void fixture_inject_trace(const char *token) {
    size_t length;
    size_t index;
    if (token == NULL || token[0] == '\0') {
        return;
    }
    length = strlen(token);
    for (index = 0; index < length; index++) {
        char character = token[index];
        int ok = (character >= 'a' && character <= 'z') || (character >= '0' && character <= '9') || character == '_';
        if (!ok) {
            return;
        }
    }
    if (g_order_truncated) {
        return;
    }
    if (g_order[0] != '\0' && strlen(g_order) + 1 + length + 12 >= sizeof g_order) {
        if (strlen(g_order) + 11 < sizeof g_order) {
            memcpy(g_order + strlen(g_order), ",truncated", 11);
        }
        g_order_truncated = 1;
        return;
    }
    if (g_order[0] != '\0') {
        memcpy(g_order + strlen(g_order), ",", 2);
    }
    memcpy(g_order + strlen(g_order), token, length + 1);
}

static void reject_unconfigured(const char *token) {
    g_unconfigured++;
    fixture_inject_trace("unconfigured");
    fixture_inject_trace(token);
}

void fixture_inject_reset(void) {
    g_prior = 1;
    g_allowed = 1;
    g_observed_prior = -1;
    g_fault = FIXTURE_FAULT_NONE;
    g_fault_bracket = -1;
    g_bracket = 0;
    g_gets = 0;
    g_sets = 0;
    g_allow_ui = 0;
    g_allow_open = 0;
    g_allow_path = 0;
    g_allow_item = 0;
    g_allow_copy = 0;
    g_allow_add = 0;
    g_copy_kind = FIXTURE_COPY_ABSENT;
    g_add_kind = FIXTURE_ADD_FAIL;
    g_fs = FIXTURE_FS_NONE;
    g_fs_used = 0;
    g_pause = FIXTURE_PAUSE_NONE;
    if (g_ready_fd >= 0) {
        close(g_ready_fd);
    }
    if (g_hold_fd >= 0) {
        close(g_hold_fd);
    }
    g_ready_fd = -1;
    g_hold_fd = -1;
    g_native = 0;
    g_unconfigured = 0;
    g_data_ops = 0;
    g_query_rejects = 0;
    g_issued = 0;
    g_disposed = 0;
    g_order_truncated = 0;
    g_opened = NULL;
    g_open_path[0] = '\0';
    g_order[0] = '\0';
}

void fixture_inject_set_prior_ui(int allowed) {
    g_prior = allowed ? 1 : 0;
    g_allowed = g_prior;
}

void fixture_inject_fail_on_bracket(int bracket_1based, int fault) {
    g_fault_bracket = bracket_1based;
    g_fault = fault;
}

void fixture_inject_arm_bind(void) {
    g_allow_ui = 1;
    g_allow_open = 1;
    g_allow_path = 1;
}

void fixture_inject_arm_copy(int copy_kind) {
    g_allow_ui = 1;
    g_allow_copy = 1;
    g_allow_item = 1;
    g_allow_path = 1;
    g_copy_kind = copy_kind;
}

void fixture_inject_arm_add(int add_kind) {
    g_allow_add = 1;
    g_add_kind = add_kind;
}

void fixture_inject_fail_fs(int site) {
    g_fs = site;
    g_fs_used = 0;
}

void fixture_inject_set_pause(int pause_kind, int ready_fd, int hold_fd) {
    g_pause = pause_kind;
    g_ready_fd = ready_fd;
    g_hold_fd = hold_fd;
}

void fixture_inject_order_clear(void) {
    g_order[0] = '\0';
    g_order_truncated = 0;
}

void fixture_inject_note_bracket(void) {
    g_bracket++;
    g_gets = 0;
    g_sets = 0;
}

static int fault_here(int fault) {
    return g_fault == fault && g_bracket == g_fault_bracket;
}

OSStatus fixture_inject_ui_get(Boolean *allowed) {
    int ordinal;
    if (allowed == NULL) {
        return errSecParam;
    }
    if (!g_allow_ui) {
        reject_unconfigured("ui_get");
        return errSecParam;
    }
    ordinal = g_gets++;
    fixture_inject_trace(ordinal == 0 ? "ui_get" : "ui_get_readback");
    if (ordinal == 0) {
        g_observed_prior = g_allowed ? 1 : 0;
        if (fault_here(FIXTURE_FAULT_UI_GET)) {
            return errSecParam;
        }
        *allowed = g_allowed ? 1 : 0;
        return errSecSuccess;
    }
    if (ordinal == 1 && (fault_here(FIXTURE_FAULT_UI_READBACK) || fault_here(FIXTURE_FAULT_UI_READBACK_MISMATCH))) {
        if (g_fault == FIXTURE_FAULT_UI_READBACK) {
            return errSecParam;
        }
        *allowed = 1;
        return errSecSuccess;
    }
    if (ordinal >= 2 && (fault_here(FIXTURE_FAULT_UI_RESTORE_READBACK) || fault_here(FIXTURE_FAULT_UI_RESTORE_MISMATCH))) {
        if (g_fault == FIXTURE_FAULT_UI_RESTORE_READBACK) {
            return errSecParam;
        }
        *allowed = g_prior ? 0 : 1;
        return errSecSuccess;
    }
    *allowed = g_allowed ? 1 : 0;
    return errSecSuccess;
}

OSStatus fixture_inject_ui_set(Boolean allowed) {
    int ordinal;
    if (!g_allow_ui) {
        reject_unconfigured("ui_set");
        return errSecParam;
    }
    ordinal = g_sets++;
    fixture_inject_trace(ordinal == 0 ? "ui_set_disable" : "ui_set_restore");
    if (ordinal == 0 && fault_here(FIXTURE_FAULT_UI_DISABLE)) {
        return errSecParam;
    }
    if (ordinal >= 1 && fault_here(FIXTURE_FAULT_UI_RESTORE)) {
        return errSecParam;
    }
    g_allowed = allowed ? 1 : 0;
    return errSecSuccess;
}

OSStatus fixture_inject_open(const char *path, CFTypeRef *out) {
    CFStringRef object;
    if (out == NULL) {
        return errSecParam;
    }
    *out = NULL;
    g_data_ops++;
    fixture_inject_trace("sec_open");
    if (!g_allow_open || path == NULL || path[0] == '\0') {
        reject_unconfigured("sec_open");
        return errSecParam;
    }
    if (fault_here(FIXTURE_FAULT_OPEN)) {
        return errSecInteractionNotAllowed;
    }
    object = CFStringCreateWithCString(kCFAllocatorDefault, path, kCFStringEncodingUTF8);
    if (object == NULL) {
        return errSecParam;
    }
    if (strlen(path) >= sizeof g_open_path) {
        CFRelease(object);
        return errSecParam;
    }
    memcpy(g_open_path, path, strlen(path) + 1);
    g_opened = object;
    *out = object;
    return errSecSuccess;
}

static OSStatus write_path(const char *text, char *buffer, UInt32 capacity, UInt32 *length) {
    size_t text_len;
    if (text == NULL || buffer == NULL || length == NULL || capacity < 2) {
        return errSecParam;
    }
    text_len = strlen(text);
    if (text_len + 1 > (size_t)capacity) {
        return errSecParam;
    }
    memcpy(buffer, text, text_len + 1);
    *length = (UInt32)text_len;
    return errSecSuccess;
}

OSStatus fixture_inject_path(CFTypeRef keychain, char *buffer, UInt32 capacity, UInt32 *length) {
    char scratch[1024];
    fixture_inject_trace("sec_path");
    if (!g_allow_path) {
        reject_unconfigured("sec_path");
        return errSecParam;
    }
    if (fault_here(FIXTURE_FAULT_PATH_FOREIGN)) {
        return write_path("/fixture-foreign-store", buffer, capacity, length);
    }
    if (keychain == NULL || CFGetTypeID(keychain) != CFStringGetTypeID()) {
        return errSecParam;
    }
    if (!CFStringGetCString((CFStringRef)keychain, scratch, (CFIndex)sizeof scratch, kCFStringEncodingUTF8)) {
        return errSecParam;
    }
    return write_path(scratch, buffer, capacity, length);
}

OSStatus fixture_inject_item_keychain(CFTypeRef item, CFTypeRef *out) {
    const uint8_t *tag;
    CFStringRef chain;
    const char *text;
    fixture_inject_trace("sec_item_keychain");
    if (out == NULL) {
        return errSecParam;
    }
    *out = NULL;
    if (!g_allow_item) {
        reject_unconfigured("sec_item_keychain");
        return errSecParam;
    }
    if (item == NULL || CFGetTypeID(item) != CFDataGetTypeID() || CFDataGetLength((CFDataRef)item) != 1) {
        return errSecParam;
    }
    tag = CFDataGetBytePtr((CFDataRef)item);
    if (tag == NULL) {
        return errSecParam;
    }
    if (tag[0] == 1) {
        text = g_open_path;
    } else if (tag[0] == 2) {
        text = "/fixture-foreign-store";
    } else {
        return errSecParam;
    }
    chain = CFStringCreateWithCString(kCFAllocatorDefault, text, kCFStringEncodingUTF8);
    if (chain == NULL) {
        return errSecParam;
    }
    *out = chain;
    return errSecSuccess;
}

CFTypeID fixture_inject_item_type_id(void) {
    return CFDataGetTypeID();
}

static int query_shape(CFDictionaryRef query, int add_destination) {
    CFTypeRef klass;
    CFTypeRef list_value;
    CFArrayRef list;
    if (query == NULL || CFGetTypeID(query) != CFDictionaryGetTypeID()) {
        return -1;
    }
    klass = CFDictionaryGetValue(query, kSecClass);
    if (klass != kSecClassGenericPassword) {
        return -1;
    }
    list_value = CFDictionaryGetValue(query, kSecMatchSearchList);
    if (list_value == NULL || CFGetTypeID(list_value) != CFArrayGetTypeID()) {
        return -1;
    }
    list = (CFArrayRef)list_value;
    if (CFArrayGetCount(list) != 1) {
        return -1;
    }
    if (!add_destination) {
        if (CFDictionaryGetValue(query, kSecMatchLimit) != kSecMatchLimitOne ||
            CFDictionaryGetValue(query, kSecReturnData) != kCFBooleanTrue ||
            CFDictionaryGetValue(query, kSecReturnRef) != kCFBooleanTrue) {
            return -1;
        }
        return 0;
    }
    {
        CFTypeRef destination = CFDictionaryGetValue(query, kSecUseKeychain);
        CFTypeRef value = CFDictionaryGetValue(query, kSecValueData);
        if (destination == NULL || g_opened == NULL || destination != g_opened) {
            return -1;
        }
        if (value == NULL || CFGetTypeID(value) != CFDataGetTypeID() || CFDataGetLength((CFDataRef)value) <= 0) {
            return -1;
        }
        if (CFDictionaryGetValue(query, kSecAttrAccessible) != kSecAttrAccessibleWhenUnlocked) {
            return -1;
        }
    }
    return 0;
}

static CFTypeRef make_found(int foreign) {
    CFMutableDictionaryRef dict;
    CFDataRef payload;
    CFDataRef item;
    uint8_t tag = foreign ? 2 : 1;
    payload = CFDataCreate(kCFAllocatorDefault, k_synthetic, (CFIndex)sizeof k_synthetic);
    item = CFDataCreate(kCFAllocatorDefault, &tag, 1);
    dict = CFDictionaryCreateMutable(kCFAllocatorDefault, 0, &kCFTypeDictionaryKeyCallBacks,
                                     &kCFTypeDictionaryValueCallBacks);
    if (payload == NULL || item == NULL || dict == NULL) {
        if (payload != NULL) {
            CFRelease(payload);
        }
        if (item != NULL) {
            CFRelease(item);
        }
        if (dict != NULL) {
            CFRelease(dict);
        }
        return NULL;
    }
    CFDictionarySetValue(dict, kSecValueData, payload);
    CFDictionarySetValue(dict, kSecValueRef, item);
    CFRelease(payload);
    CFRelease(item);
    return dict;
}

OSStatus fixture_inject_copy(CFDictionaryRef query, CFTypeRef *found) {
    g_data_ops++;
    fixture_inject_trace("sec_copy");
    if (found == NULL) {
        return errSecParam;
    }
    *found = NULL;
    if (!g_allow_copy) {
        reject_unconfigured("sec_copy");
        return errSecParam;
    }
    if (query_shape(query, 0) != 0) {
        g_query_rejects++;
        fixture_inject_trace("query_rejected");
        return errSecParam;
    }
    if (g_copy_kind == FIXTURE_COPY_ABSENT) {
        return errSecItemNotFound;
    }
    if (g_copy_kind == FIXTURE_COPY_DENIED) {
        return errSecAuthFailed;
    }
    *found = make_found(g_copy_kind == FIXTURE_COPY_FOREIGN);
    if (*found == NULL) {
        return errSecParam;
    }
    return errSecSuccess;
}

OSStatus fixture_inject_add(CFDictionaryRef query, CFTypeRef *result) {
    g_data_ops++;
    fixture_inject_trace("sec_add");
    if (result != NULL) {
        *result = NULL;
    }
    if (!g_allow_add) {
        reject_unconfigured("sec_add");
        return errSecParam;
    }
    if (query_shape(query, 1) != 0) {
        g_query_rejects++;
        fixture_inject_trace("query_rejected");
        return errSecParam;
    }
    if (g_add_kind == FIXTURE_ADD_OK) {
        return errSecSuccess;
    }
    return errSecAuthFailed;
}

int fixture_inject_random(uint8_t *buffer, size_t length) {
    (void)buffer;
    (void)length;
    reject_unconfigured("sec_random");
    return -1;
}

int fixture_inject_before_write(int site, int fd, const void *bytes, size_t length, size_t *accepted) {
    ssize_t wrote;
    if (accepted != NULL) {
        *accepted = 0;
    }
    if (g_fs != site || (site != FIXTURE_FS_MARKER_WRITE && site != FIXTURE_FS_PUBLISH_WRITE) || g_fs_used) {
        return 0;
    }
    g_fs_used = 1;
    if (fd < 0 || bytes == NULL || length == 0) {
        return -1;
    }
    do {
        wrote = write(fd, bytes, 1);
    } while (wrote < 0 && errno == EINTR);
    if (wrote != 1) {
        return -1;
    }
    if (accepted != NULL) {
        *accepted = 1;
    }
    return 1;
}

int fixture_inject_before_fsync(int site, int fd) {
    (void)fd;
    if (g_fs != site || g_fs_used) {
        return 0;
    }
    if (site != FIXTURE_FS_MARKER_FSYNC && site != FIXTURE_FS_MARKER_DIR_FSYNC && site != FIXTURE_FS_PUBLISH_FSYNC &&
        site != FIXTURE_FS_PUBLISH_DIR_FSYNC) {
        return 0;
    }
    g_fs_used = 1;
    return -1;
}

static int pause_block(void) {
    char line[1800];
    int written;
    size_t offset = 0;
    char byte = 0;
    ssize_t count;
    if (g_ready_fd >= 0) {
        written = snprintf(line, sizeof line, "ready order=%s\n", g_order);
        if (written < 0 || (size_t)written >= sizeof line) {
            return -1;
        }
        while (offset < (size_t)written) {
            ssize_t piece = write(g_ready_fd, line + offset, (size_t)written - offset);
            if (piece < 0 && errno == EINTR) {
                continue;
            }
            if (piece <= 0) {
                return -1;
            }
            offset += (size_t)piece;
        }
        close(g_ready_fd);
        g_ready_fd = -1;
    }
    if (g_hold_fd < 0) {
        return -1;
    }
    do {
        count = read(g_hold_fd, &byte, 1);
    } while (count < 0 && errno == EINTR);
    if (count <= 0) {
        return -1;
    }
    return 0;
}

int fixture_inject_checkpoint_before_add(void) {
    if (g_pause != FIXTURE_PAUSE_BEFORE_ADD) {
        return 0;
    }
    return pause_block();
}

int fixture_inject_checkpoint_holding_lock(void) {
    if (g_pause != FIXTURE_PAUSE_HOLDING_LOCK) {
        return 0;
    }
    return pause_block();
}

int fixture_inject_native_security_calls(void) {
    return g_native;
}

int fixture_inject_unconfigured_calls(void) {
    return g_unconfigured;
}

int fixture_inject_data_operations(void) {
    return g_data_ops;
}

int fixture_inject_query_rejects(void) {
    return g_query_rejects;
}

int fixture_inject_observed_prior(void) {
    return g_observed_prior;
}

int fixture_inject_issued_objects(void) {
    return g_issued;
}

int fixture_inject_disposed_objects(void) {
    return g_disposed;
}

const char *fixture_inject_order(void) {
    return g_order;
}

CFDataRef fixture_inject_copy_data(CFDataRef source) {
    CFIndex length;
    const uint8_t *bytes;
    size_t *header;
    uint8_t *payload;
    CFDataRef data;
    if (source == NULL || CFGetTypeID(source) != CFDataGetTypeID()) {
        return NULL;
    }
    length = CFDataGetLength(source);
    bytes = CFDataGetBytePtr(source);
    if (bytes == NULL || length <= 0 || length > 128) {
        return NULL;
    }
    ensure_allocator();
    if (g_allocator == NULL) {
        return NULL;
    }
    header = malloc(sizeof(size_t) + (size_t)length);
    if (header == NULL) {
        return NULL;
    }
    header[0] = (size_t)length;
    payload = (uint8_t *)(header + 1);
    memcpy(payload, bytes, (size_t)length);
    data = CFDataCreateWithBytesNoCopy(kCFAllocatorDefault, payload, length, g_allocator);
    if (data == NULL) {
        return NULL;
    }
    g_issued++;
    return data;
}
