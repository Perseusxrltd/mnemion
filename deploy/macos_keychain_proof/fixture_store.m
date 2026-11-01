#include "fixture_store.h"

#include "fixture_store_config.h"
#include "fixture_store_syntax.h"
#include "protocol.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

/* SecKeychainRef is deprecated because Apple prefers the data-protection
   keychain. That is the real profile this lane must not use. The explicit
   file store has no replacement, so only these calls ignore that warning. */

enum {
    FIXTURE_PATH_MAX = 1024,
    FIXTURE_RECORD_MAX = 512,
    FIXTURE_SECRET_MAX = 128
};

struct fixture_bound {
    int bound;
    int run_fd;
    SecKeychainRef keychain;
    uid_t euid;
    dev_t run_dev;
    ino_t run_ino;
    dev_t store_dev;
    ino_t store_ino;
    char run_dir[FIXTURE_PATH_MAX];
    char store_path[FIXTURE_PATH_MAX];
    char record_path[FIXTURE_PATH_MAX];
    char nonce[33];
    char service[160];
    char account[160];
};

static struct fixture_bound g_store = {.run_fd = -1};

int fixture_store_runtime_allowed(void) {
    int syntax = fixture_syntax_config(
        MNEMION_FIXTURE_STORE_CLASS, MNEMION_FIXTURE_STORE_METADATA, MNEMION_FIXTURE_SERVICE_PREFIX,
        MNEMION_FIXTURE_ACCOUNT_PREFIX, MNEMION_FIXTURE_STORE_BASENAME, MNEMION_FIXTURE_RECORD_BASENAME,
        MNEMION_KEYCHAIN_SERVICE, MNEMION_KEYCHAIN_ACCOUNT);
    if (syntax != FIXTURE_SYNTAX_OK) {
        return -1;
    }
    if (fixture_syntax_names(MNEMION_FIXTURE_SERVICE_PREFIX, MNEMION_FIXTURE_ACCOUNT_PREFIX, MNEMION_FIXTURE_NONCE,
                             MNEMION_FIXTURE_SERVICE, MNEMION_FIXTURE_ACCOUNT, MNEMION_KEYCHAIN_SERVICE,
                             MNEMION_KEYCHAIN_ACCOUNT) != FIXTURE_SYNTAX_OK ||
        fixture_syntax_run_path(MNEMION_FIXTURE_RUN_DIRECTORY) != FIXTURE_SYNTAX_OK) {
        return -1;
    }
    return 0;
}

int fixture_store_create_permitted(int directories_ok, int ciphertext_empty, int marker_absent, int key_state,
                                   int caller_claims_absent) {
    return fixture_syntax_creation(directories_ok, ciphertext_empty, marker_absent, key_state,
                                   caller_claims_absent) == FIXTURE_CREATE_ONCE
               ? 1
               : 0;
}

int fixture_store_argument_matches_seal(const char *path) {
    return fixture_syntax_direct_binding(1, path, MNEMION_FIXTURE_RUN_DIRECTORY) == FIXTURE_SYNTAX_OK ? 0 : -1;
}

static OSStatus keychain_open(const char *path, SecKeychainRef *out) {
    OSStatus status;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    status = SecKeychainOpen(path, out);
#pragma clang diagnostic pop
    return status;
}

static OSStatus keychain_path(SecKeychainRef keychain, char *buffer, UInt32 capacity, UInt32 *length) {
    OSStatus status;
    *length = capacity;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    status = SecKeychainGetPath(keychain, length, buffer);
#pragma clang diagnostic pop
    return status;
}

static OSStatus item_keychain(SecKeychainItemRef item, SecKeychainRef *out) {
    OSStatus status;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    status = SecKeychainItemCopyKeychain(item, out);
#pragma clang diagnostic pop
    return status;
}

/* Process-local file-Keychain UI. These two calls are the only ones that
   suppress the deprecation warning for the interaction setting. The setting
   is not the default keychain and it is not the search list. */
static pthread_mutex_t g_ui_mu = PTHREAD_MUTEX_INITIALIZER;

static int ui_get(Boolean *allowed) {
    OSStatus status;
    if (allowed == NULL) {
        return -1;
    }
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    status = SecKeychainGetUserInteractionAllowed(allowed);
#pragma clang diagnostic pop
    return status == errSecSuccess ? 0 : -1;
}

static int ui_set(Boolean allowed) {
    OSStatus status;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    status = SecKeychainSetUserInteractionAllowed(allowed);
#pragma clang diagnostic pop
    return status == errSecSuccess ? 0 : -1;
}

static int ui_restore(Boolean prior) {
    Boolean readback = 0;
    int set_ok = ui_set(prior) == 0;
    int read_ok = 0;
    int read_allowed = 0;
    if (set_ok && ui_get(&readback) == 0) {
        read_ok = 1;
        read_allowed = readback ? 1 : 0;
    }
    return fixture_syntax_ui_restore(prior ? 1 : 0, set_ok, read_ok, read_allowed) == FIXTURE_UI_READY ? 0 : -1;
}

static int ui_enter(Boolean *prior_out) {
    Boolean prior = 0;
    Boolean readback = 1;
    int set_ok = 0;
    int read_ok = 0;
    int read_allowed = 1;
    int operate = 0;
    if (prior_out == NULL || pthread_mutex_lock(&g_ui_mu) != 0) {
        return -1;
    }
    if (ui_get(&prior) != 0) {
        if (pthread_mutex_unlock(&g_ui_mu) != 0) {
            return -1;
        }
        return -1;
    }
    set_ok = ui_set(0) == 0;
    if (set_ok && ui_get(&readback) == 0) {
        read_ok = 1;
        read_allowed = readback ? 1 : 0;
    }
    if (fixture_syntax_ui_setup(1, set_ok, read_ok, read_allowed, &operate) != FIXTURE_UI_READY || !operate) {
        (void)ui_restore(prior);
        if (pthread_mutex_unlock(&g_ui_mu) != 0) {
            return -1;
        }
        return -1;
    }
    *prior_out = prior;
    return 0;
}

static int ui_leave(Boolean prior) {
    int restored = ui_restore(prior);
    if (pthread_mutex_unlock(&g_ui_mu) != 0) {
        return -1;
    }
    return restored;
}

static int finish_ui(Boolean prior, int op_result) {
    if (ui_leave(prior) != 0) {
        return -1;
    }
    return op_result;
}

static int component_symlinks(const char *absolute) {
    char scratch[FIXTURE_PATH_MAX];
    size_t length;
    size_t index;
    struct stat st;
    if (absolute == NULL) {
        return -1;
    }
    length = strlen(absolute);
    if (length < 2 || length >= sizeof scratch) {
        return -1;
    }
    memcpy(scratch, absolute, length + 1);
    for (index = 1; index < length; index++) {
        if (scratch[index] != '/') {
            continue;
        }
        scratch[index] = '\0';
        if (lstat(scratch, &st) != 0 || S_ISLNK(st.st_mode)) {
            return -1;
        }
        scratch[index] = '/';
    }
    if (lstat(scratch, &st) != 0 || S_ISLNK(st.st_mode)) {
        return -1;
    }
    return 0;
}

static int owned_directory(int fd, dev_t *device, ino_t *inode) {
    struct stat st;
    if (fd < 0 || fstat(fd, &st) != 0) {
        return -1;
    }
    if (!S_ISDIR(st.st_mode) || S_ISLNK(st.st_mode)) {
        return -1;
    }
    if (st.st_uid != geteuid() || (st.st_mode & 07777) != 0700) {
        return -1;
    }
    *device = st.st_dev;
    *inode = st.st_ino;
    return 0;
}

static int read_exact(int fd, char *buffer, size_t capacity, size_t *length) {
    size_t filled = 0;
    while (filled + 1 < capacity) {
        ssize_t count = read(fd, buffer + filled, capacity - 1 - filled);
        if (count < 0) {
            return -1;
        }
        if (count == 0) {
            break;
        }
        filled += (size_t)count;
    }
    if (read(fd, &(char){0}, 1) != 0) {
        return -1;
    }
    buffer[filled] = '\0';
    if (filled == 0 || memchr(buffer, '\0', filled) != NULL) {
        return -1;
    }
    *length = filled;
    return 0;
}

static int line_value(const char *line, const char *key, char *out, size_t out_cap) {
    size_t key_len = strlen(key);
    size_t value_len;
    if (strncmp(line, key, key_len) != 0 || line[key_len] != '=') {
        return -1;
    }
    value_len = strlen(line + key_len + 1);
    if (value_len + 1 > out_cap || value_len == 0) {
        return -1;
    }
    memcpy(out, line + key_len + 1, value_len + 1);
    return 0;
}

static int parse_record(const char *text, char *nonce, size_t nonce_cap, char *service, size_t service_cap,
                        char *account, size_t account_cap) {
    const char *line_start = text;
    int line_index = 0;
    char lines[3][192];
    while (line_index < 3) {
        const char *break_at = strchr(line_start, '\n');
        size_t line_len;
        if (break_at == NULL) {
            return -1;
        }
        line_len = (size_t)(break_at - line_start);
        if (line_len == 0 || line_len >= sizeof lines[0] || memchr(line_start, '\r', line_len) != NULL) {
            return -1;
        }
        memcpy(lines[line_index], line_start, line_len);
        lines[line_index][line_len] = '\0';
        line_index++;
        line_start = break_at + 1;
    }
    if (line_start[0] != '\0' || line_index != 3) {
        return -1;
    }
    if (line_value(lines[0], "nonce", nonce, nonce_cap) != 0 ||
        line_value(lines[1], "service", service, service_cap) != 0 ||
        line_value(lines[2], "account", account, account_cap) != 0) {
        return -1;
    }
    return fixture_syntax_names(MNEMION_FIXTURE_SERVICE_PREFIX, MNEMION_FIXTURE_ACCOUNT_PREFIX, nonce, service,
                                account, MNEMION_KEYCHAIN_SERVICE, MNEMION_KEYCHAIN_ACCOUNT) == FIXTURE_SYNTAX_OK
               ? 0
               : -1;
}

static int read_record_text(int run_fd, char *text, size_t text_cap) {
    int fd;
    struct stat st;
    size_t length = 0;
    fd = openat(run_fd, MNEMION_FIXTURE_RECORD_BASENAME, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) {
        return -1;
    }
    if (fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || st.st_uid != geteuid() ||
        (st.st_mode & 07777) != 0600 || st.st_size <= 0 || st.st_size >= (off_t)text_cap) {
        close(fd);
        return -1;
    }
    if (read_exact(fd, text, text_cap, &length) != 0) {
        close(fd);
        return -1;
    }
    close(fd);
    return 0;
}

static int load_record(int run_fd) {
    char text[FIXTURE_RECORD_MAX];
    char nonce[33];
    char service[160];
    char account[160];
    int parsed;
    if (read_record_text(run_fd, text, sizeof text) != 0) {
        return -1;
    }
    parsed = parse_record(text, nonce, sizeof nonce, service, sizeof service, account, sizeof account);
    memset(text, 0, sizeof text);
    if (parsed != 0) {
        return -1;
    }
    memcpy(g_store.nonce, nonce, sizeof g_store.nonce);
    memcpy(g_store.service, service, strlen(service) + 1);
    memcpy(g_store.account, account, strlen(account) + 1);
    return 0;
}

static int record_unchanged(void) {
    char text[FIXTURE_RECORD_MAX];
    char nonce[33];
    char service[160];
    char account[160];
    int parsed;
    if (read_record_text(g_store.run_fd, text, sizeof text) != 0) {
        return -1;
    }
    parsed = parse_record(text, nonce, sizeof nonce, service, sizeof service, account, sizeof account);
    memset(text, 0, sizeof text);
    if (parsed != 0 || strcmp(nonce, g_store.nonce) != 0 || strcmp(service, g_store.service) != 0 ||
        strcmp(account, g_store.account) != 0) {
        return -1;
    }
    return 0;
}

static int store_file_identity(int fd, dev_t *device, ino_t *inode) {
    struct stat st;
    if (fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || S_ISLNK(st.st_mode)) {
        return -1;
    }
    if (st.st_uid != geteuid() || (st.st_mode & 07777) != 0600) {
        return -1;
    }
    *device = st.st_dev;
    *inode = st.st_ino;
    return 0;
}

static int ref_path_matches(SecKeychainRef keychain) {
    char path[FIXTURE_PATH_MAX];
    UInt32 length = 0;
    OSStatus status = keychain_path(keychain, path, sizeof path, &length);
    if (status != errSecSuccess || length != strlen(g_store.store_path)) {
        return -1;
    }
    if (strcmp(path, g_store.store_path) != 0) {
        return -1;
    }
    return 0;
}

static int identities_match(const char *run_directory, dev_t run_dev, ino_t run_ino, dev_t store_dev, ino_t store_ino) {
    if (g_store.nonce[0] == '\0' || g_store.service[0] == '\0' || g_store.account[0] == '\0') {
        return -1;
    }
    return fixture_syntax_sealed_match(
               MNEMION_FIXTURE_RUN_DIRECTORY, run_directory, MNEMION_FIXTURE_NONCE, g_store.nonce,
               MNEMION_FIXTURE_SERVICE, g_store.service, MNEMION_FIXTURE_ACCOUNT, g_store.account,
               (unsigned long long)MNEMION_FIXTURE_EUID, (unsigned long long)geteuid(),
               (unsigned long long)MNEMION_FIXTURE_RUN_DEVICE, (unsigned long long)run_dev,
               (unsigned long long)MNEMION_FIXTURE_RUN_INODE, (unsigned long long)run_ino,
               (unsigned long long)MNEMION_FIXTURE_STORE_DEVICE, (unsigned long long)store_dev,
               (unsigned long long)MNEMION_FIXTURE_STORE_INODE, (unsigned long long)store_ino, MNEMION_KEYCHAIN_SERVICE,
               MNEMION_KEYCHAIN_ACCOUNT) == FIXTURE_SYNTAX_OK
               ? 0
               : -1;
}

int fixture_store_bind(void) {
    const char *run_directory = MNEMION_FIXTURE_RUN_DIRECTORY;
    int run_fd = -1;
    int store_fd = -1;
    dev_t run_dev = 0;
    ino_t run_ino = 0;
    dev_t store_dev = 0;
    ino_t store_ino = 0;
    SecKeychainRef keychain = NULL;
    OSStatus status;
    struct stat after;
    Boolean prior = 0;
    int opened_ok = 0;
    /* An allowed flag, from the environment or a request, cannot admit a path. */
    if (fixture_syntax_request_boolean(1, run_directory) != FIXTURE_SYNTAX_REQUEST) {
        return -1;
    }
    if (fixture_store_runtime_allowed() != 0 || g_store.bound) {
        return -1;
    }
    if (fixture_syntax_run_path(run_directory) != FIXTURE_SYNTAX_OK || component_symlinks(run_directory) != 0) {
        return -1;
    }
    run_fd = open(run_directory, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (owned_directory(run_fd, &run_dev, &run_ino) != 0) {
        if (run_fd >= 0) {
            close(run_fd);
        }
        return -1;
    }
    if (fixture_syntax_join(run_directory, MNEMION_FIXTURE_STORE_BASENAME, g_store.store_path,
                            sizeof g_store.store_path) != 0 ||
        fixture_syntax_join(run_directory, MNEMION_FIXTURE_RECORD_BASENAME, g_store.record_path,
                            sizeof g_store.record_path) != 0) {
        close(run_fd);
        g_store.store_path[0] = '\0';
        g_store.record_path[0] = '\0';
        return -1;
    }
    if (component_symlinks(g_store.store_path) != 0 || load_record(run_fd) != 0) {
        close(run_fd);
        memset(&g_store, 0, sizeof g_store);
        g_store.run_fd = -1;
        return -1;
    }
    /* The file must already exist. SecKeychainOpen is not treated as create,
       and SecKeychainCreate is not called. A missing file refuses first. */
    store_fd = openat(run_fd, MNEMION_FIXTURE_STORE_BASENAME, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (store_file_identity(store_fd, &store_dev, &store_ino) != 0 ||
        identities_match(run_directory, run_dev, run_ino, store_dev, store_ino) != 0) {
        if (store_fd >= 0) {
            close(store_fd);
        }
        close(run_fd);
        memset(&g_store, 0, sizeof g_store);
        g_store.run_fd = -1;
        return -1;
    }
    if (ui_enter(&prior) != 0) {
        close(store_fd);
        close(run_fd);
        memset(&g_store, 0, sizeof g_store);
        g_store.run_fd = -1;
        return -1;
    }
    status = keychain_open(g_store.store_path, &keychain);
    if (status == errSecSuccess && keychain != NULL && fstat(store_fd, &after) == 0 && after.st_dev == store_dev &&
        after.st_ino == store_ino && ref_path_matches(keychain) == 0) {
        opened_ok = 1;
    }
    if (finish_ui(prior, opened_ok ? 0 : -1) != 0) {
        if (keychain != NULL) {
            CFRelease(keychain);
        }
        close(store_fd);
        close(run_fd);
        memset(&g_store, 0, sizeof g_store);
        g_store.run_fd = -1;
        return -1;
    }
    close(store_fd);
    memcpy(g_store.run_dir, run_directory, strlen(run_directory) + 1);
    g_store.run_fd = run_fd;
    g_store.keychain = keychain;
    g_store.euid = geteuid();
    g_store.run_dev = run_dev;
    g_store.run_ino = run_ino;
    g_store.store_dev = store_dev;
    g_store.store_ino = store_ino;
    g_store.bound = 1;
    return 0;
}

static int revalidate(void) {
    dev_t run_dev = 0;
    ino_t run_ino = 0;
    int store_fd;
    dev_t store_dev = 0;
    ino_t store_ino = 0;
    struct stat path_stat;
    if (!g_store.bound || g_store.keychain == NULL || g_store.euid != geteuid()) {
        return -1;
    }
    if (fixture_store_runtime_allowed() != 0) {
        return -1;
    }
    if (component_symlinks(g_store.run_dir) != 0 || component_symlinks(g_store.store_path) != 0) {
        return -1;
    }
    if (owned_directory(g_store.run_fd, &run_dev, &run_ino) != 0 || run_dev != g_store.run_dev ||
        run_ino != g_store.run_ino) {
        return -1;
    }
    store_fd = openat(g_store.run_fd, MNEMION_FIXTURE_STORE_BASENAME, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (store_file_identity(store_fd, &store_dev, &store_ino) != 0 || store_dev != g_store.store_dev ||
        store_ino != g_store.store_ino) {
        if (store_fd >= 0) {
            close(store_fd);
        }
        return -1;
    }
    close(store_fd);
    if (lstat(g_store.store_path, &path_stat) != 0 || !S_ISREG(path_stat.st_mode) ||
        path_stat.st_dev != g_store.store_dev || path_stat.st_ino != g_store.store_ino ||
        path_stat.st_uid != g_store.euid) {
        return -1;
    }
    /* Caller holds the file-Keychain interaction bracket. ref_path_matches
       uses SecKeychainGetPath and must not take the bracket again. */
    if (record_unchanged() != 0 || identities_match(g_store.run_dir, run_dev, run_ino, store_dev, store_ino) != 0 ||
        ref_path_matches(g_store.keychain) != 0) {
        return -1;
    }
    return 0;
}

static CFStringRef bound_string(const char *text) {
    return CFStringCreateWithCString(NULL, text, kCFStringEncodingUTF8);
}

static int install_names(CFMutableDictionaryRef query) {
    CFStringRef service = bound_string(g_store.service);
    CFStringRef account = bound_string(g_store.account);
    if (service == NULL || account == NULL) {
        if (service != NULL) {
            CFRelease(service);
        }
        if (account != NULL) {
            CFRelease(account);
        }
        return -1;
    }
    CFDictionarySetValue(query, kSecClass, kSecClassGenericPassword);
    CFDictionarySetValue(query, kSecAttrService, service);
    CFDictionarySetValue(query, kSecAttrAccount, account);
    CFRelease(service);
    CFRelease(account);
    return 0;
}

static int install_scope(CFMutableDictionaryRef query) {
    const void *values[1];
    CFArrayRef scope;
    /* One explicit store through kSecMatchSearchList. Not a deprecated search,
       and not a ProtectedCloudStorage service. */
    if (g_store.keychain == NULL ||
        fixture_syntax_explicit_list(1, 1, 0, strstr(g_store.service, "ProtectedCloudStorage") != NULL) !=
            FIXTURE_SYNTAX_OK ||
        fixture_syntax_scope_count(1) != FIXTURE_SYNTAX_OK) {
        return -1;
    }
    values[0] = g_store.keychain;
    scope = CFArrayCreate(NULL, values, 1, &kCFTypeArrayCallBacks);
    if (scope == NULL || CFArrayGetCount(scope) != 1) {
        if (scope != NULL) {
            CFRelease(scope);
        }
        return -1;
    }
    CFDictionarySetValue(query, kSecMatchSearchList, scope);
    CFRelease(scope);
    if (CFDictionaryGetValue(query, kSecMatchSearchList) == NULL) {
        return -1;
    }
    return 0;
}

static int install_destination(CFMutableDictionaryRef query) {
    if (g_store.keychain == NULL) {
        return -1;
    }
    CFDictionarySetValue(query, kSecUseKeychain, g_store.keychain);
    return CFDictionaryGetValue(query, kSecUseKeychain) == g_store.keychain ? 0 : -1;
}

static int item_is_this_store(CFTypeRef found) {
    CFDictionaryRef dict;
    SecKeychainItemRef item;
    SecKeychainRef chain = NULL;
    int matches;
    if (found == NULL || CFGetTypeID(found) != CFDictionaryGetTypeID()) {
        return -1;
    }
    dict = (CFDictionaryRef)found;
    item = (SecKeychainItemRef)CFDictionaryGetValue(dict, kSecValueRef);
    if (item == NULL) {
        return -1;
    }
    {
        CFTypeID item_type;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
        item_type = SecKeychainItemGetTypeID();
#pragma clang diagnostic pop
        if (CFGetTypeID(item) != item_type) {
            return -1;
        }
    }
    if (item_keychain(item, &chain) != errSecSuccess || chain == NULL) {
        return -1;
    }
    matches = ref_path_matches(chain);
    CFRelease(chain);
    return matches;
}

static CFDataRef copy_password(CFTypeRef found) {
    CFDataRef data;
    if (item_is_this_store(found) != 0) {
        return NULL;
    }
    data = (CFDataRef)CFDictionaryGetValue((CFDictionaryRef)found, kSecValueData);
    if (data == NULL || CFGetTypeID(data) != CFDataGetTypeID() || CFDataGetLength(data) <= 0) {
        return NULL;
    }
    return CFDataCreateCopy(NULL, data);
}

static int copy_matching_holding(CFDataRef *data_out, OSStatus *status_out, int *invoked) {
    CFMutableDictionaryRef query = NULL;
    CFTypeRef found = NULL;
    OSStatus status;
    if (data_out == NULL || status_out == NULL || invoked == NULL || revalidate() != 0) {
        return -1;
    }
    query = CFDictionaryCreateMutable(NULL, 0, &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    if (query == NULL || install_names(query) != 0 || install_scope(query) != 0) {
        if (query != NULL) {
            CFRelease(query);
        }
        return -1;
    }
    CFDictionarySetValue(query, kSecReturnData, kCFBooleanTrue);
    CFDictionarySetValue(query, kSecReturnRef, kCFBooleanTrue);
    CFDictionarySetValue(query, kSecMatchLimit, kSecMatchLimitOne);
    *invoked = 1;
    status = SecItemCopyMatching(query, &found);
    *status_out = status;
    CFRelease(query);
    if (status == errSecItemNotFound) {
        if (found != NULL) {
            CFRelease(found);
        }
        return 0;
    }
    if (status != errSecSuccess) {
        if (found != NULL) {
            CFRelease(found);
        }
        return 0;
    }
    *data_out = copy_password(found);
    if (found != NULL) {
        CFRelease(found);
    }
    if (*data_out == NULL) {
        /* A hit outside this store is not an absent fixture item and is not data. */
        *status_out = errSecParam;
        return -1;
    }
    return 0;
}

int fixture_store_copy_matching(CFDataRef *data_out, OSStatus *status_out, int *invoked) {
    Boolean prior = 0;
    int result;
    if (data_out != NULL) {
        *data_out = NULL;
    }
    if (status_out != NULL) {
        *status_out = errSecParam;
    }
    if (invoked != NULL) {
        *invoked = 0;
    }
    if (data_out == NULL || status_out == NULL || invoked == NULL || !g_store.bound) {
        return -1;
    }
    if (ui_enter(&prior) != 0) {
        return -1;
    }
    result = copy_matching_holding(data_out, status_out, invoked);
    return finish_ui(prior, result);
}

static int write_all(int fd, const void *bytes, size_t length) {
    const char *cursor = bytes;
    size_t filled = 0;
    if (fd < 0 || bytes == NULL || length == 0) {
        return -1;
    }
    while (filled < length) {
        ssize_t count = write(fd, cursor + filled, length - filled);
        if (count <= 0) {
            return -1;
        }
        filled += (size_t)count;
    }
    return 0;
}

static int scan_directory(int dirfd, int *empty_out, int *hostile_out) {
    int probe;
    DIR *dir;
    struct dirent *ent;
    int empty = 1;
    int hostile = 0;
    probe = dup(dirfd);
    if (probe < 0) {
        return -1;
    }
    dir = fdopendir(probe);
    if (dir == NULL) {
        close(probe);
        return -1;
    }
    errno = 0;
    while ((ent = readdir(dir)) != NULL) {
        struct stat st;
        if (strcmp(ent->d_name, ".") == 0 || strcmp(ent->d_name, "..") == 0) {
            continue;
        }
        empty = 0;
        if (fstatat(dirfd, ent->d_name, &st, AT_SYMLINK_NOFOLLOW) != 0 || S_ISLNK(st.st_mode)) {
            hostile = 1;
            break;
        }
    }
    if (errno != 0) {
        hostile = 1;
    }
    if (closedir(dir) != 0) {
        return -1;
    }
    if (empty_out != NULL) {
        *empty_out = empty;
    }
    if (hostile_out != NULL) {
        *hostile_out = hostile;
    }
    return hostile ? -1 : 0;
}

static int measure_ciphertext(int *empty_out) {
    int fd;
    struct stat st;
    int empty = 0;
    *empty_out = 0;
    fd = openat(g_store.run_fd, FIXTURE_FIXED_CIPHERTEXT_DIR, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0 || fstat(fd, &st) != 0 || !S_ISDIR(st.st_mode) || st.st_uid != geteuid() ||
        (st.st_mode & 07777) != 0700) {
        if (fd >= 0) {
            close(fd);
        }
        return -1;
    }
    if (scan_directory(fd, &empty, NULL) != 0) {
        close(fd);
        return -1;
    }
    if (close(fd) != 0) {
        return -1;
    }
    *empty_out = empty;
    return 0;
}

static int measure_marker(int *absent_out) {
    struct stat st;
    *absent_out = 0;
    if (fstatat(g_store.run_fd, FIXTURE_FIXED_MARKER_NAME, &st, AT_SYMLINK_NOFOLLOW) != 0) {
        if (errno == ENOENT) {
            *absent_out = 1;
            return 0;
        }
        return -1;
    }
    if (!S_ISREG(st.st_mode) || S_ISLNK(st.st_mode)) {
        return -1;
    }
    return 0;
}

static int acquire_fixture_lock(int *fd_out) {
    int fd;
    struct stat st;
    *fd_out = -1;
    fd = openat(g_store.run_fd, FIXTURE_FIXED_LOCK_NAME, O_RDWR | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0 || fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || st.st_uid != geteuid() ||
        (st.st_mode & 07777) != 0600) {
        if (fd >= 0) {
            close(fd);
        }
        return -1;
    }
    if (flock(fd, LOCK_EX | LOCK_NB) != 0) {
        close(fd);
        return -1;
    }
    *fd_out = fd;
    return 0;
}

static int release_fixture_lock(int fd) {
    int failed = 0;
    if (fd < 0) {
        return -1;
    }
    if (flock(fd, LOCK_UN) != 0) {
        failed = 1;
    }
    if (close(fd) != 0) {
        failed = 1;
    }
    return failed ? -1 : 0;
}

static int write_marker(void) {
    char body[2048];
    int written;
    int fd;
    struct stat st;
    /* A created marker is never removed. fixture_syntax_marker_survives(1) is refused. */
    if (fixture_syntax_marker_survives(0) != FIXTURE_SYNTAX_OK) {
        return -1;
    }
    written = snprintf(body, sizeof body,
                       "run=%s\nnonce=%s\neuid=%llu\nrun_dev=%llu\nrun_ino=%llu\nstore_dev=%llu\nstore_ino=%llu\n"
                       "service=%s\naccount=%s\n",
                       g_store.run_dir, g_store.nonce, (unsigned long long)g_store.euid,
                       (unsigned long long)g_store.run_dev, (unsigned long long)g_store.run_ino,
                       (unsigned long long)g_store.store_dev, (unsigned long long)g_store.store_ino, g_store.service,
                       g_store.account);
    if (written < 0 || (size_t)written >= sizeof body) {
        return -1;
    }
    fd = openat(g_store.run_fd, FIXTURE_FIXED_MARKER_NAME, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) {
        return -1;
    }
    if (fchmod(fd, 0600) != 0 || write_all(fd, body, (size_t)written) != 0 || fsync(fd) != 0 ||
        fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || st.st_uid != geteuid() || (st.st_mode & 07777) != 0600 ||
        fsync(g_store.run_fd) != 0) {
        close(fd);
        return -1;
    }
    if (close(fd) != 0) {
        return -1;
    }
    return 0;
}

static int add_holding(const uint8_t *secret, size_t secret_len, int caller_claims_absent, OSStatus *status_out,
                       int *invoked) {
    int directories_ok = 0;
    int ciphertext_empty = 0;
    int marker_absent = 0;
    CFDataRef probe = NULL;
    OSStatus probe_status = errSecParam;
    int probe_invoked = 0;
    int probe_result;
    int key_state = -1;
    int decision;
    CFMutableDictionaryRef query = NULL;
    CFDataRef payload = NULL;
    OSStatus status;
    if (revalidate() == 0 && measure_ciphertext(&ciphertext_empty) == 0 && measure_marker(&marker_absent) == 0) {
        directories_ok = 1;
    }
    if (!directories_ok) {
        return -1;
    }
    probe_result = copy_matching_holding(&probe, &probe_status, &probe_invoked);
    *invoked = probe_invoked;
    if (probe != NULL) {
        CFRelease(probe);
    }
    if (probe_result != 0) {
        return -1;
    }
    if (probe_status == errSecSuccess) {
        key_state = 1;
    } else if (probe_status == errSecItemNotFound) {
        key_state = 0;
    } else {
        *status_out = probe_status;
        return 0;
    }
    decision = fixture_syntax_creation(directories_ok, ciphertext_empty, marker_absent, key_state, caller_claims_absent);
    if (decision == FIXTURE_CREATE_READ_EXISTING) {
        *status_out = errSecDuplicateItem;
        return 0;
    }
    if (decision != FIXTURE_CREATE_ONCE ||
        !fixture_store_create_permitted(directories_ok, ciphertext_empty, marker_absent, key_state,
                                        caller_claims_absent)) {
        return -1;
    }
    if (write_marker() != 0) {
        return -1;
    }
    payload = CFDataCreate(NULL, secret, (CFIndex)secret_len);
    query = CFDictionaryCreateMutable(NULL, 0, &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    if (payload == NULL || query == NULL || install_names(query) != 0 || install_scope(query) != 0 ||
        install_destination(query) != 0) {
        if (query != NULL) {
            CFRelease(query);
        }
        if (payload != NULL) {
            CFRelease(payload);
        }
        return -1;
    }
    CFDictionarySetValue(query, kSecValueData, payload);
    CFDictionarySetValue(query, kSecAttrAccessible, kSecAttrAccessibleWhenUnlocked);
    *invoked = probe_invoked + 1;
    status = SecItemAdd(query, NULL);
    *status_out = status;
    CFRelease(query);
    CFRelease(payload);
    return 0;
}

int fixture_store_add_new(const uint8_t *secret, size_t secret_len, int caller_claims_absent, OSStatus *status_out,
                          int *invoked) {
    int lock_fd = -1;
    Boolean prior = 0;
    int result;
    if (status_out != NULL) {
        *status_out = errSecParam;
    }
    if (invoked != NULL) {
        *invoked = 0;
    }
    if (secret == NULL || secret_len == 0 || secret_len > FIXTURE_SECRET_MAX || status_out == NULL || invoked == NULL ||
        !g_store.bound) {
        return -1;
    }
    if (acquire_fixture_lock(&lock_fd) != 0) {
        return -1;
    }
    if (ui_enter(&prior) != 0) {
        if (release_fixture_lock(lock_fd) != 0) {
            return -1;
        }
        return -1;
    }
    result = add_holding(secret, secret_len, caller_claims_absent, status_out, invoked);
    result = finish_ui(prior, result);
    if (release_fixture_lock(lock_fd) != 0) {
        return -1;
    }
    return result;
}

static int publish_holding(const uint8_t *bytes, size_t length) {
    int dirfd;
    struct stat st;
    int index;
    if (revalidate() != 0) {
        return -1;
    }
    dirfd = openat(g_store.run_fd, FIXTURE_FIXED_CIPHERTEXT_DIR, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (dirfd < 0 || fstat(dirfd, &st) != 0 || !S_ISDIR(st.st_mode) || st.st_uid != geteuid() ||
        (st.st_mode & 07777) != 0700 || scan_directory(dirfd, NULL, NULL) != 0) {
        if (dirfd >= 0) {
            close(dirfd);
        }
        return -1;
    }
    for (index = 1; index <= 64; index++) {
        char name[32];
        int fd;
        int written = snprintf(name, sizeof name, "published-%04d", index);
        if (written < 0 || (size_t)written >= sizeof name) {
            close(dirfd);
            return -1;
        }
        fd = openat(dirfd, name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
        if (fd < 0) {
            if (errno == EEXIST) {
                continue;
            }
            close(dirfd);
            return -1;
        }
        if (fchmod(fd, 0600) != 0 || write_all(fd, bytes, length) != 0 || fsync(fd) != 0 || fsync(dirfd) != 0) {
            close(fd);
            close(dirfd);
            return -1;
        }
        if (close(fd) != 0) {
            close(dirfd);
            return -1;
        }
        if (close(dirfd) != 0) {
            return -1;
        }
        return 0;
    }
    close(dirfd);
    return -1;
}

int fixture_store_publish_ciphertext(const uint8_t *bytes, size_t length) {
    int lock_fd = -1;
    Boolean prior = 0;
    int result;
    if (bytes == NULL || length == 0 || length > MNEMION_MAX_CIPHERTEXT || !g_store.bound) {
        return -1;
    }
    if (acquire_fixture_lock(&lock_fd) != 0) {
        return -1;
    }
    if (ui_enter(&prior) != 0) {
        if (release_fixture_lock(lock_fd) != 0) {
            return -1;
        }
        return -1;
    }
    result = publish_holding(bytes, length);
    result = finish_ui(prior, result);
    if (release_fixture_lock(lock_fd) != 0) {
        return -1;
    }
    return result;
}
