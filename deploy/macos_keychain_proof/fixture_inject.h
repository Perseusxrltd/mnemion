#ifndef MNEMION_FIXTURE_INJECT_H
#define MNEMION_FIXTURE_INJECT_H

#include <CoreFoundation/CoreFoundation.h>
#include <Security/Security.h>

#include <stddef.h>
#include <stdint.h>

/* Test-only prototypes. The ordinary helper and the compile-only lane do not
   define MNEMION_FIXTURE_INJECT, do not link fixture_inject.c, and do not
   take an environment or XPC switch onto this backend. Including this header
   does not redirect those builds. */

enum {
    FIXTURE_FAULT_NONE = 0,
    FIXTURE_FAULT_UI_GET = 1,
    FIXTURE_FAULT_UI_DISABLE = 2,
    FIXTURE_FAULT_UI_READBACK = 3,
    FIXTURE_FAULT_UI_READBACK_MISMATCH = 4,
    FIXTURE_FAULT_UI_RESTORE = 5,
    FIXTURE_FAULT_UI_RESTORE_READBACK = 6,
    FIXTURE_FAULT_UI_RESTORE_MISMATCH = 7,
    FIXTURE_FAULT_OPEN = 8,
    FIXTURE_FAULT_PATH_FOREIGN = 9
};

enum {
    FIXTURE_COPY_ABSENT = 0,
    FIXTURE_COPY_PRESENT = 1,
    FIXTURE_COPY_FOREIGN = 2,
    FIXTURE_COPY_DENIED = 3
};

enum {
    FIXTURE_ADD_FAIL = 0,
    FIXTURE_ADD_OK = 1
};

enum {
    FIXTURE_FS_NONE = 0,
    FIXTURE_FS_MARKER_WRITE = 1,
    FIXTURE_FS_MARKER_FSYNC = 2,
    FIXTURE_FS_MARKER_DIR_FSYNC = 3,
    FIXTURE_FS_PUBLISH_WRITE = 4,
    FIXTURE_FS_PUBLISH_FSYNC = 5,
    FIXTURE_FS_PUBLISH_DIR_FSYNC = 6
};

enum {
    FIXTURE_PAUSE_NONE = 0,
    FIXTURE_PAUSE_BEFORE_ADD = 1,
    FIXTURE_PAUSE_HOLDING_LOCK = 2
};

enum {
    FIXTURE_MARKER_ABSENT = 0,
    FIXTURE_MARKER_PRESENT = 1,
    FIXTURE_MARKER_PARTIAL = 2
};

enum {
    FIXTURE_PUB_NONE = 0,
    FIXTURE_PUB_RETAINED = 1
};

enum {
    FIXTURE_DIR_EMPTY = 0,
    FIXTURE_DIR_OCCUPIED = 1
};

void fixture_inject_reset(void);
void fixture_inject_set_prior_ui(int allowed);
void fixture_inject_fail_on_bracket(int bracket_1based, int fault);
void fixture_inject_arm_bind(void);
void fixture_inject_arm_copy(int copy_kind);
void fixture_inject_arm_add(int add_kind);
void fixture_inject_fail_fs(int site);
void fixture_inject_set_pause(int pause_kind, int ready_fd, int hold_fd);
void fixture_inject_order_clear(void);
void fixture_inject_note_bracket(void);
void fixture_inject_trace(const char *token);

OSStatus fixture_inject_ui_get(Boolean *allowed);
OSStatus fixture_inject_ui_set(Boolean allowed);
OSStatus fixture_inject_open(const char *path, CFTypeRef *out);
OSStatus fixture_inject_path(CFTypeRef keychain, char *buffer, UInt32 capacity, UInt32 *length);
OSStatus fixture_inject_item_keychain(CFTypeRef item, CFTypeRef *out);
CFTypeID fixture_inject_item_type_id(void);
OSStatus fixture_inject_copy(CFDictionaryRef query, CFTypeRef *found);
OSStatus fixture_inject_add(CFDictionaryRef query, CFTypeRef *result);
int fixture_inject_random(uint8_t *buffer, size_t length);
int fixture_inject_before_write(int site, int fd, const void *bytes, size_t length, size_t *accepted);
int fixture_inject_before_fsync(int site, int fd);
int fixture_inject_checkpoint_before_add(void);
int fixture_inject_checkpoint_holding_lock(void);

int fixture_inject_native_security_calls(void);
int fixture_inject_unconfigured_calls(void);
int fixture_inject_data_operations(void);
int fixture_inject_query_rejects(void);
int fixture_inject_observed_prior(void);
int fixture_inject_issued_objects(void);
int fixture_inject_disposed_objects(void);
const char *fixture_inject_order(void);
CFDataRef fixture_inject_copy_data(CFDataRef source);

/* Reads the sealed run through the directory file descriptor. Categories only. */
int fixture_observe_run(int *marker, int *publication, int *directory);

#endif
