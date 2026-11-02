#include "real_store_names.h"

#include <CommonCrypto/CommonDigest.h>
#include <CoreFoundation/CoreFoundation.h>
#include <Security/Security.h>

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

/* Creates, imports into, locks, and deletes two explicit private stores.
   It does not set the default store, the search list, or trust settings.
   A changed search list is a failure and is not repaired. */

enum { k_path_max = 1024, k_list_max = 32, k_secret = 32, k_der_max = 8192, k_p12_max = 32768 };

static int g_calls = 0;

struct list_snap {
    int count;
    int default_status;
    char paths[k_list_max][k_path_max];
    char default_path[k_path_max];
};

struct secrets {
    char signing[k_secret + 1];
    char data[k_secret + 1];
    char pkcs[k_secret + 1];
};

static void zero_bytes(void *pointer, size_t size) {
    volatile unsigned char *bytes = pointer;
    size_t index;
    if (pointer == NULL) {
        return;
    }
    for (index = 0; index < size; index++) {
        bytes[index] = 0;
    }
}

static void zero_secrets(struct secrets *values) {
    zero_bytes(values, sizeof *values);
}

static int write_all(int fd, const char *bytes, size_t length) {
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

static void diagnose(int dirfd, const char *op, int status) {
    char line[96];
    int fd;
    int written;
    if (dirfd < 0 || op == NULL) {
        return;
    }
    written = snprintf(line, sizeof line, "op=%s status=%d\n", op, status);
    if (written < 0 || (size_t)written >= sizeof line) {
        return;
    }
    fd = openat(dirfd, "diagnostic.txt", O_WRONLY | O_CREAT | O_APPEND | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) {
        return;
    }
    if (fchmod(fd, 0600) != 0 || write_all(fd, line, (size_t)written) != 0) {
        close(fd);
        return;
    }
    close(fd);
}

static int hex_text(const char *text, size_t expect) {
    size_t index;
    int varied = 0;
    if (text == NULL || strlen(text) != expect) {
        return 0;
    }
    for (index = 0; index < expect; index++) {
        char character = text[index];
        int digit = (character >= '0' && character <= '9') || (character >= 'a' && character <= 'f');
        if (!digit) {
            return 0;
        }
        if (character != text[0]) {
            varied = 1;
        }
    }
    return varied;
}

static void digest_hex(const unsigned char *digest, size_t count, char *out) {
    static const char digits[] = "0123456789abcdef";
    size_t index;
    for (index = 0; index < count; index++) {
        out[index * 2] = digits[digest[index] >> 4];
        out[index * 2 + 1] = digits[digest[index] & 15];
    }
    out[count * 2] = '\0';
}

static int hash_der(const unsigned char *bytes, size_t length, char *sha1, size_t sha1_cap, char *sha256, size_t sha256_cap) {
    unsigned char sha1_raw[CC_SHA1_DIGEST_LENGTH];
    unsigned char sha256_raw[CC_SHA256_DIGEST_LENGTH];
    if (bytes == NULL || length == 0 || sha1_cap < 41 || sha256_cap < 65) {
        return -1;
    }
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    CC_SHA1(bytes, (CC_LONG)length, sha1_raw);
#pragma clang diagnostic pop
    CC_SHA256(bytes, (CC_LONG)length, sha256_raw);
    digest_hex(sha1_raw, sizeof sha1_raw, sha1);
    digest_hex(sha256_raw, sizeof sha256_raw, sha256);
    return 0;
}

static int path_prefix(const char *prefix, const char *path) {
    size_t length = strlen(prefix);
    if (strncmp(prefix, path, length) != 0) {
        return 0;
    }
    return path[length] == '\0' || path[length] == '/';
}

static int walk_run(const char *path) {
    size_t length;
    size_t cursor = 1;
    int fd;
    char cwd[1024];
    if (path == NULL) {
        return -1;
    }
    length = strlen(path);
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
    if (fixture_syntax_run_path(path) != FIXTURE_SYNTAX_OK) {
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
        struct stat st;
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
    close(fd);
    return 0;
}

static int join_name(const char *run, const char *base, char *out, size_t cap) {
    int written;
    if (fixture_syntax_basename(base) != FIXTURE_SYNTAX_OK) {
        return -1;
    }
    written = snprintf(out, cap, "%s/%s", run, base);
    if (written < 0 || (size_t)written >= cap) {
        return -1;
    }
    return 0;
}

static int expect_absent(int dirfd, const char *name) {
    struct stat st;
    if (fstatat(dirfd, name, &st, AT_SYMLINK_NOFOLLOW) == 0) {
        return -1;
    }
    return errno == ENOENT ? 0 : -1;
}

static int read_secret(int dirfd, const char *name, char *out) {
    int fd;
    struct stat st;
    char buffer[k_secret];
    size_t filled = 0;
    fd = openat(dirfd, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) {
        return -1;
    }
    if (fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || S_ISLNK(st.st_mode) || st.st_uid != geteuid() ||
        (st.st_mode & 07777) != 0600 || st.st_size != k_secret) {
        close(fd);
        return -1;
    }
    while (filled < k_secret) {
        ssize_t count = read(fd, buffer + filled, k_secret - filled);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count <= 0) {
            zero_bytes(buffer, sizeof buffer);
            close(fd);
            return -1;
        }
        filled += (size_t)count;
    }
    close(fd);
    memcpy(out, buffer, k_secret);
    out[k_secret] = '\0';
    zero_bytes(buffer, sizeof buffer);
    if (!hex_text(out, k_secret)) {
        zero_bytes(out, k_secret + 1);
        return -1;
    }
    return 0;
}

static OSStatus kc_get_ui(Boolean *value) {
    g_calls++;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    return SecKeychainGetUserInteractionAllowed(value);
#pragma clang diagnostic pop
}

static OSStatus kc_set_ui(Boolean value) {
    g_calls++;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    return SecKeychainSetUserInteractionAllowed(value);
#pragma clang diagnostic pop
}

static int ui_enter(Boolean *prior, int *changed) {
    Boolean readback = true;
    *changed = 0;
    if (kc_get_ui(prior) != errSecSuccess) {
        return -1;
    }
    if (kc_set_ui(false) != errSecSuccess) {
        return -1;
    }
    *changed = 1;
    if (kc_get_ui(&readback) != errSecSuccess || readback != false) {
        return -1;
    }
    return 0;
}

static int ui_leave(Boolean prior) {
    Boolean readback = !prior;
    if (kc_set_ui(prior) != errSecSuccess) {
        return -1;
    }
    if (kc_get_ui(&readback) != errSecSuccess || readback != prior) {
        return -1;
    }
    return 0;
}

static int copy_path(SecKeychainRef keychain, char *out, size_t cap) {
    char buffer[k_path_max];
    UInt32 length = sizeof buffer;
    OSStatus status;
    g_calls++;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    status = SecKeychainGetPath(keychain, &length, buffer);
#pragma clang diagnostic pop
    if (status != errSecSuccess || length == 0 || length >= sizeof buffer) {
        return -1;
    }
    buffer[sizeof buffer - 1] = '\0';
    if (strlen(buffer) != (size_t)length || strlen(buffer) + 1 > cap) {
        return -1;
    }
    memcpy(out, buffer, strlen(buffer) + 1);
    return 0;
}

static int snapshot(struct list_snap *snap) {
    SecKeychainRef fallback = NULL;
    CFArrayRef list = NULL;
    CFIndex count;
    CFIndex index;
    OSStatus status;
    memset(snap, 0, sizeof *snap);
    g_calls++;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    status = SecKeychainCopyDefault(&fallback);
#pragma clang diagnostic pop
    snap->default_status = (int)status;
    if (status == errSecSuccess) {
        if (fallback == NULL || copy_path(fallback, snap->default_path, sizeof snap->default_path) != 0) {
            if (fallback != NULL) {
                CFRelease(fallback);
            }
            return -1;
        }
        CFRelease(fallback);
    } else if (fallback != NULL) {
        CFRelease(fallback);
    }
    g_calls++;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    status = SecKeychainCopySearchList(&list);
#pragma clang diagnostic pop
    if (status != errSecSuccess || list == NULL) {
        if (list != NULL) {
            CFRelease(list);
        }
        return -1;
    }
    count = CFArrayGetCount(list);
    if (count < 0 || count > k_list_max) {
        CFRelease(list);
        return -1;
    }
    snap->count = (int)count;
    for (index = 0; index < count; index++) {
        SecKeychainRef item = (SecKeychainRef)CFArrayGetValueAtIndex(list, index);
        if (item == NULL || copy_path(item, snap->paths[index], k_path_max) != 0) {
            CFRelease(list);
            return -1;
        }
    }
    CFRelease(list);
    for (index = 1; index < snap->count; index++) {
        char saved[k_path_max];
        CFIndex cursor = index;
        memcpy(saved, snap->paths[index], sizeof saved);
        while (cursor > 0 && strcmp(snap->paths[cursor - 1], saved) > 0) {
            memcpy(snap->paths[cursor], snap->paths[cursor - 1], k_path_max);
            cursor--;
        }
        memcpy(snap->paths[cursor], saved, sizeof saved);
    }
    return 0;
}

static int snaps_equal(const struct list_snap *before, const struct list_snap *after, int *default_same) {
    int index;
    *default_same = before->default_status == after->default_status &&
                    (before->default_status != (int)errSecSuccess || strcmp(before->default_path, after->default_path) == 0);
    if (before->count != after->count) {
        return 0;
    }
    for (index = 0; index < before->count; index++) {
        if (strcmp(before->paths[index], after->paths[index]) != 0) {
            return 0;
        }
    }
    return 1;
}

static int owned_directory(int fd, struct stat *st) {
    if (fstat(fd, st) != 0 || !S_ISDIR(st->st_mode) || S_ISLNK(st->st_mode)) {
        return -1;
    }
    if (st->st_uid != geteuid() || (st->st_mode & 07777) != 0700) {
        return -1;
    }
    return 0;
}

static OSStatus create_store(const char *path, const char *password, SecKeychainRef *out) {
    g_calls++;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    return SecKeychainCreate(path, (UInt32)strlen(password), password, false, NULL, out);
#pragma clang diagnostic pop
}

static OSStatus open_store(const char *path, SecKeychainRef *out) {
    g_calls++;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    return SecKeychainOpen(path, out);
#pragma clang diagnostic pop
}

static OSStatus unlock_store(SecKeychainRef keychain, const char *password) {
    g_calls++;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    return SecKeychainUnlock(keychain, (UInt32)strlen(password), password, true);
#pragma clang diagnostic pop
}

static OSStatus lock_store(SecKeychainRef keychain) {
    g_calls++;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    return SecKeychainLock(keychain);
#pragma clang diagnostic pop
}

static OSStatus delete_store(SecKeychainRef keychain) {
    g_calls++;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    return SecKeychainDelete(keychain);
#pragma clang diagnostic pop
}

static int measure_created(int dirfd, const char *name, const char *full, SecKeychainRef keychain, struct stat *st) {
    char reported[k_path_max];
    int fd;
    if (copy_path(keychain, reported, sizeof reported) != 0 || strcmp(reported, full) != 0) {
        return -1;
    }
    fd = openat(dirfd, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) {
        return -1;
    }
    if (fstat(fd, st) != 0 || !S_ISREG(st->st_mode) || S_ISLNK(st->st_mode) || st->st_uid != geteuid()) {
        close(fd);
        return -1;
    }
    if ((st->st_mode & 07777) != 0600) {
        if (fchmod(fd, 0600) != 0 || fstat(fd, st) != 0 || (st->st_mode & 07777) != 0600) {
            close(fd);
            return -1;
        }
    }
    close(fd);
    return 0;
}

static int safe_name(const char *name) {
    size_t index;
    size_t length = strlen(name);
    if (length == 0 || length > 64 || strcmp(name, ".") == 0 || strcmp(name, "..") == 0) {
        return 0;
    }
    for (index = 0; index < length; index++) {
        char character = name[index];
        int ok = (character >= 'A' && character <= 'Z') || (character >= 'a' && character <= 'z') ||
                 (character >= '0' && character <= '9') || character == '.' || character == '_' || character == '-';
        if (!ok) {
            return 0;
        }
    }
    return 1;
}

static int expected_name(const char *name) {
    return strcmp(name, REAL_STORE_DATA_BASENAME) == 0 || strcmp(name, REAL_STORE_SIGNING_BASENAME) == 0 ||
           strcmp(name, REAL_STORE_RECORD_BASENAME) == 0 || strcmp(name, REAL_STORE_LOCK_BASENAME) == 0 ||
           strcmp(name, REAL_STORE_CIPHERTEXT_BASENAME) == 0 || strcmp(name, "include") == 0 ||
           strcmp(name, "signing.pass") == 0 || strcmp(name, "data.pass") == 0;
}

static int record_symlink(int dirfd, const char *name, const struct stat *st) {
    char line[256];
    int fd;
    int written;
    if (!safe_name(name)) {
        return -1;
    }
    written = snprintf(line, sizeof line, "lnk %llu %llu %s\n", (unsigned long long)st->st_dev, (unsigned long long)st->st_ino,
                       name);
    if (written < 0 || (size_t)written >= sizeof line) {
        return -1;
    }
    fd = openat(dirfd, "companions.txt", O_WRONLY | O_CREAT | O_APPEND | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0 || fchmod(fd, 0600) != 0 || write_all(fd, line, (size_t)written) != 0) {
        if (fd >= 0) {
            close(fd);
        }
        return -1;
    }
    close(fd);
    return 0;
}

static int scan_companions(int dirfd, int *symlinks) {
    int fd;
    DIR *dir;
    struct dirent *ent;
    *symlinks = 0;
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
        if (fstatat(dirfd, ent->d_name, &st, AT_SYMLINK_NOFOLLOW) != 0) {
            closedir(dir);
            return -1;
        }
        if (expected_name(ent->d_name)) {
            errno = 0;
            continue;
        }
        if (S_ISLNK(st.st_mode) && safe_name(ent->d_name)) {
            if (record_symlink(dirfd, ent->d_name, &st) != 0) {
                closedir(dir);
                return -1;
            }
            *symlinks += 1;
        } else {
            /* An unexpected regular file is the same refusal as a fifo or an unsafe link. */
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

static int write_measure(int dirfd, const struct stat *run_st, const struct stat *store_st, int symlinks) {
    char body[512];
    int fd;
    int written;
    written = snprintf(body, sizeof body,
                       "basename_contract=pass\nget_path_match=yes\nsigning_path_match=yes\nregular=yes\nmode=0600\n"
                       "store_device=%llu\nstore_inode=%llu\nrun_device=%llu\nrun_inode=%llu\ncompanion_symlinks=%d\n",
                       (unsigned long long)store_st->st_dev, (unsigned long long)store_st->st_ino,
                       (unsigned long long)run_st->st_dev, (unsigned long long)run_st->st_ino, symlinks);
    if (written < 0 || (size_t)written >= sizeof body) {
        return -1;
    }
    fd = openat(dirfd, "store-measure.txt", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0 || fchmod(fd, 0600) != 0 || write_all(fd, body, (size_t)written) != 0 || fsync(fd) != 0) {
        if (fd >= 0) {
            close(fd);
        }
        return -1;
    }
    close(fd);
    return 0;
}

static void emit_count(void) {
    printf("instrumented_security_calls=%d\n", g_calls);
}

static int finish_create(const char *category, const char *search, const char *fallback, const char *basename, int code) {
    printf("result=%s\n", category);
    emit_count();
    printf("search_list_equal=%s\n", search);
    printf("default_equal=%s\n", fallback);
    printf("basename_contract=%s\n", basename);
    return code;
}

static int cmd_create(const char *run) {
    struct secrets secrets;
    struct list_snap *before = NULL;
    struct list_snap *after = NULL;
    SecKeychainRef signing = NULL;
    SecKeychainRef data = NULL;
    struct stat run_st;
    struct stat store_st;
    struct stat signing_st;
    char signing_path[k_path_max];
    char data_path[k_path_max];
    Boolean prior = true;
    int changed = 0;
    int dirfd = -1;
    int default_same = 0;
    int symlinks = 0;
    int code = 1;
    const char *category = "store_create_refused";
    const char *search = "not_run";
    const char *fallback = "not_run";
    const char *basename = "not_run";
    memset(&secrets, 0, sizeof secrets);
    if (walk_run(run) != 0 || join_name(run, REAL_STORE_SIGNING_BASENAME, signing_path, sizeof signing_path) != 0 ||
        join_name(run, REAL_STORE_DATA_BASENAME, data_path, sizeof data_path) != 0) {
        category = "path_rejected";
        goto done;
    }
    dirfd = open(run, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (dirfd < 0 || owned_directory(dirfd, &run_st) != 0) {
        category = "path_rejected";
        goto done;
    }
    if (expect_absent(dirfd, REAL_STORE_SIGNING_BASENAME) != 0 || expect_absent(dirfd, REAL_STORE_DATA_BASENAME) != 0) {
        goto done;
    }
    if (read_secret(dirfd, "signing.pass", secrets.signing) != 0 || read_secret(dirfd, "data.pass", secrets.data) != 0) {
        goto done;
    }
    before = calloc(1, sizeof *before);
    after = calloc(1, sizeof *after);
    if (before == NULL || after == NULL) {
        category = "unsupported";
        goto done;
    }
    if (ui_enter(&prior, &changed) != 0) {
        category = "interaction_bracket";
        goto restore;
    }
    if (snapshot(before) != 0) {
        category = "search_list_unreadable";
        goto restore;
    }
    if (create_store(signing_path, secrets.signing, &signing) != errSecSuccess || signing == NULL ||
        create_store(data_path, secrets.data, &data) != errSecSuccess || data == NULL) {
        diagnose(dirfd, "create", -1);
        goto restore;
    }
    if (measure_created(dirfd, REAL_STORE_SIGNING_BASENAME, signing_path, signing, &signing_st) != 0 ||
        measure_created(dirfd, REAL_STORE_DATA_BASENAME, data_path, data, &store_st) != 0) {
        basename = "fail";
        category = "store_basename_contract";
        diagnose(dirfd, "measure", -1);
        goto restore;
    }
    basename = "pass";
    if (lock_store(signing) != errSecSuccess || lock_store(data) != errSecSuccess) {
        category = "lock_refused";
        goto restore;
    }
    if (snapshot(after) != 0) {
        category = "search_list_unreadable";
        goto restore;
    }
    if (!snaps_equal(before, after, &default_same)) {
        search = "no";
        fallback = default_same ? "yes" : "no";
        category = "search_list_changed";
        goto restore;
    }
    search = "yes";
    if (!default_same) {
        fallback = "no";
        category = "default_store_changed";
        goto restore;
    }
    fallback = "yes";
    if (expect_absent(dirfd, "companions.txt") != 0 || expect_absent(dirfd, "store-measure.txt") != 0 ||
        scan_companions(dirfd, &symlinks) != 0) {
        category = "companion_unexpected";
        goto restore;
    }
    if (write_measure(dirfd, &run_st, &store_st, symlinks) != 0) {
        category = "store_basename_contract";
        basename = "fail";
        goto restore;
    }
    category = "ok";
    code = 0;
restore:
    if (changed && ui_leave(prior) != 0) {
        category = "interaction_bracket";
        code = 1;
    }
done:
    if (signing != NULL) {
        CFRelease(signing);
    }
    if (data != NULL) {
        CFRelease(data);
    }
    if (before != NULL) {
        zero_bytes(before, sizeof *before);
        free(before);
    }
    if (after != NULL) {
        zero_bytes(after, sizeof *after);
        free(after);
    }
    zero_secrets(&secrets);
    if (dirfd >= 0) {
        close(dirfd);
    }
    return finish_create(category, search, fallback, basename, code);
}

static int open_owned(int dirfd, const char *run, const char *name, const char *password, SecKeychainRef *out) {
    char path[k_path_max];
    char reported[k_path_max];
    struct stat st;
    int fd;
    OSStatus status;
    *out = NULL;
    if (join_name(run, name, path, sizeof path) != 0) {
        return -1;
    }
    fd = openat(dirfd, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0 || fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || S_ISLNK(st.st_mode) || st.st_uid != geteuid() ||
        (st.st_mode & 07777) != 0600) {
        if (fd >= 0) {
            close(fd);
        }
        return -1;
    }
    close(fd);
    status = open_store(path, out);
    if (status != errSecSuccess || *out == NULL) {
        return -1;
    }
    if (password != NULL && unlock_store(*out, password) != errSecSuccess) {
        return -1;
    }
    if (copy_path(*out, reported, sizeof reported) != 0 || strcmp(reported, path) != 0) {
        if (password != NULL) {
            lock_store(*out);
        }
        return -1;
    }
    return 0;
}

static int scope_key_to_codesign(SecKeychainItemRef item) {
    SecTrustedApplicationRef app = NULL;
    SecAccessRef access = NULL;
    CFArrayRef trusted = NULL;
    const void *value;
    OSStatus status;
    g_calls++;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    status = SecTrustedApplicationCreateFromPath("/usr/bin/codesign", &app);
#pragma clang diagnostic pop
    if (status != errSecSuccess || app == NULL) {
        return -1;
    }
    value = app;
    trusted = CFArrayCreate(NULL, &value, 1, &kCFTypeArrayCallBacks);
    if (trusted == NULL) {
        CFRelease(app);
        return -1;
    }
    g_calls++;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    status = SecAccessCreate(CFSTR("mnemion-fixture-codesign"), trusted, &access);
#pragma clang diagnostic pop
    CFRelease(trusted);
    CFRelease(app);
    if (status != errSecSuccess || access == NULL) {
        return -1;
    }
    g_calls++;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    status = SecKeychainItemSetAccess(item, access);
#pragma clang diagnostic pop
    CFRelease(access);
    return status == errSecSuccess ? 0 : -1;
}

static int read_bounded(int dirfd, const char *name, unsigned char **out, size_t *out_len, size_t cap) {
    int fd;
    struct stat st;
    unsigned char *buffer;
    size_t filled = 0;
    fd = openat(dirfd, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) {
        return -1;
    }
    if (fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || st.st_uid != geteuid() || (st.st_mode & 07777) != 0600 ||
        st.st_size <= 0 || (size_t)st.st_size > cap) {
        close(fd);
        return -1;
    }
    buffer = malloc((size_t)st.st_size);
    if (buffer == NULL) {
        close(fd);
        return -1;
    }
    while (filled < (size_t)st.st_size) {
        ssize_t count = read(fd, buffer + filled, (size_t)st.st_size - filled);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count <= 0) {
            zero_bytes(buffer, (size_t)st.st_size);
            free(buffer);
            close(fd);
            return -1;
        }
        filled += (size_t)count;
    }
    close(fd);
    *out = buffer;
    *out_len = filled;
    return 0;
}

static int unlink_name(int dirfd, const char *name) {
    struct stat st;
    if (fstatat(dirfd, name, &st, AT_SYMLINK_NOFOLLOW) != 0) {
        return errno == ENOENT ? 0 : -1;
    }
    if (S_ISLNK(st.st_mode) || !S_ISREG(st.st_mode)) {
        return -1;
    }
    return unlinkat(dirfd, name, 0) == 0 ? 0 : -1;
}

static int cmd_import(const char *run) {
    struct secrets secrets;
    SecKeychainRef signing = NULL;
    CFDataRef pkcs = NULL;
    CFStringRef passphrase = NULL;
    CFDictionaryRef options = NULL;
    CFArrayRef items = NULL;
    SecIdentityRef identity = NULL;
    SecCertificateRef imported = NULL;
    SecKeyRef private_key = NULL;
    unsigned char *p12 = NULL;
    unsigned char *der = NULL;
    size_t p12_len = 0;
    size_t der_len = 0;
    char file_sha1[41];
    char file_sha256[65];
    char leaf_sha1[41];
    char leaf_sha256[65];
    Boolean prior = true;
    int changed = 0;
    int dirfd = -1;
    int code = 1;
    const char *category = "import_refused";
    const void *keys[2];
    const void *values[2];
    CFIndex count;
    OSStatus status;
    memset(&secrets, 0, sizeof secrets);
    file_sha1[0] = '\0';
    leaf_sha1[0] = '\0';
    if (walk_run(run) != 0) {
        category = "path_rejected";
        goto done;
    }
    dirfd = open(run, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (dirfd < 0) {
        category = "path_rejected";
        goto done;
    }
    if (read_secret(dirfd, "signing.pass", secrets.signing) != 0 || read_secret(dirfd, "pkcs.pass", secrets.pkcs) != 0 ||
        read_bounded(dirfd, "leaf.p12", &p12, &p12_len, k_p12_max) != 0 ||
        read_bounded(dirfd, "leaf.cer", &der, &der_len, k_der_max) != 0) {
        category = "identity_refused";
        goto done;
    }
    if (hash_der(der, der_len, file_sha1, sizeof file_sha1, file_sha256, sizeof file_sha256) != 0) {
        category = "identity_refused";
        goto done;
    }
    if (ui_enter(&prior, &changed) != 0) {
        category = "interaction_bracket";
        goto done;
    }
    if (open_owned(dirfd, run, REAL_STORE_SIGNING_BASENAME, secrets.signing, &signing) != 0) {
        category = "import_refused";
        goto restore;
    }
    pkcs = CFDataCreate(NULL, p12, (CFIndex)p12_len);
    passphrase = CFStringCreateWithBytes(NULL, (const UInt8 *)secrets.pkcs, k_secret, kCFStringEncodingUTF8, false);
    if (pkcs == NULL || passphrase == NULL) {
        category = "unsupported";
        goto restore;
    }
    keys[0] = kSecImportExportPassphrase;
    keys[1] = kSecImportExportKeychain;
    values[0] = passphrase;
    values[1] = signing;
    options = CFDictionaryCreate(NULL, keys, values, 2, &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    if (options == NULL) {
        category = "unsupported";
        goto restore;
    }
    g_calls++;
    status = SecPKCS12Import(pkcs, options, &items);
    if (status == errSecInteractionNotAllowed || status == errSecUserCanceled || status == errSecAuthFailed) {
        diagnose(dirfd, "import", (int)status);
        category = "import_refused";
        goto restore;
    }
    if (status != errSecSuccess || items == NULL) {
        diagnose(dirfd, "import", (int)status);
        goto restore;
    }
    count = CFArrayGetCount(items);
    if (count != 1) {
        goto restore;
    }
    {
        CFDictionaryRef row = CFArrayGetValueAtIndex(items, 0);
        if (row == NULL || CFGetTypeID(row) != CFDictionaryGetTypeID()) {
            goto restore;
        }
        identity = (SecIdentityRef)CFDictionaryGetValue(row, kSecImportItemIdentity);
        if (identity == NULL || CFGetTypeID(identity) != SecIdentityGetTypeID()) {
            identity = NULL;
            goto restore;
        }
        CFRetain(identity);
    }
    if (SecIdentityCopyCertificate(identity, &imported) != errSecSuccess || imported == NULL) {
        goto restore;
    }
    {
        CFDataRef live = SecCertificateCopyData(imported);
        const UInt8 *bytes;
        CFIndex length;
        if (live == NULL) {
            goto restore;
        }
        bytes = CFDataGetBytePtr(live);
        length = CFDataGetLength(live);
        if (bytes == NULL || length <= 0 ||
            hash_der(bytes, (size_t)length, leaf_sha1, sizeof leaf_sha1, leaf_sha256, sizeof leaf_sha256) != 0) {
            CFRelease(live);
            goto restore;
        }
        CFRelease(live);
    }
    if (strcmp(file_sha1, leaf_sha1) != 0 || strcmp(file_sha256, leaf_sha256) != 0 || !hex_text(leaf_sha1, 40) ||
        !hex_text(leaf_sha256, 64)) {
        category = "identity_refused";
        goto restore;
    }
    if (SecIdentityCopyPrivateKey(identity, &private_key) != errSecSuccess || private_key == NULL ||
        scope_key_to_codesign((SecKeychainItemRef)private_key) != 0) {
        category = "import_refused";
        goto restore;
    }
    if (lock_store(signing) != errSecSuccess) {
        category = "lock_refused";
        goto restore;
    }
    category = "ok";
    code = 0;
restore:
    if (changed && ui_leave(prior) != 0) {
        category = "interaction_bracket";
        code = 1;
    }
done:
    if (dirfd >= 0) {
        unlink_name(dirfd, "leaf.key");
        unlink_name(dirfd, "leaf.cer");
        unlink_name(dirfd, "leaf.p12");
        unlink_name(dirfd, "leaf.cnf");
        unlink_name(dirfd, "pkcs.pass");
    }
    if (private_key != NULL) {
        CFRelease(private_key);
    }
    if (imported != NULL) {
        CFRelease(imported);
    }
    if (identity != NULL) {
        CFRelease(identity);
    }
    if (items != NULL) {
        CFRelease(items);
    }
    if (options != NULL) {
        CFRelease(options);
    }
    if (passphrase != NULL) {
        CFRelease(passphrase);
    }
    if (pkcs != NULL) {
        CFRelease(pkcs);
    }
    if (signing != NULL) {
        CFRelease(signing);
    }
    zero_bytes(p12, p12_len);
    zero_bytes(der, der_len);
    free(p12);
    free(der);
    zero_bytes(file_sha1, sizeof file_sha1);
    zero_bytes(file_sha256, sizeof file_sha256);
    zero_secrets(&secrets);
    printf("result=%s\n", category);
    emit_count();
    if (code == 0) {
        printf("leaf_sha1=%s\n", leaf_sha1);
        printf("leaf_sha256=%s\n", leaf_sha256);
        printf("acl_scope=codesign\n");
    }
    zero_bytes(leaf_sha1, sizeof leaf_sha1);
    zero_bytes(leaf_sha256, sizeof leaf_sha256);
    if (dirfd >= 0) {
        close(dirfd);
    }
    return code;
}

static int cmd_lock_state(const char *run, const char *name, const char *pass_name, int unlock) {
    struct secrets secrets;
    SecKeychainRef store = NULL;
    Boolean prior = true;
    int changed = 0;
    int dirfd = -1;
    int code = 1;
    const char *category = "lock_refused";
    memset(&secrets, 0, sizeof secrets);
    if (walk_run(run) != 0) {
        category = "path_rejected";
        goto done;
    }
    dirfd = open(run, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (dirfd < 0 || read_secret(dirfd, pass_name, secrets.signing) != 0) {
        category = "path_rejected";
        goto done;
    }
    if (ui_enter(&prior, &changed) != 0) {
        category = "interaction_bracket";
        goto done;
    }
    if (open_owned(dirfd, run, name, unlock ? secrets.signing : NULL, &store) != 0) {
        goto restore;
    }
    if (!unlock && unlock_store(store, secrets.signing) != errSecSuccess) {
        goto restore;
    }
    if (!unlock && lock_store(store) != errSecSuccess) {
        goto restore;
    }
    category = "ok";
    code = 0;
restore:
    if (changed && ui_leave(prior) != 0) {
        category = "interaction_bracket";
        code = 1;
    }
done:
    if (store != NULL) {
        CFRelease(store);
    }
    zero_secrets(&secrets);
    if (dirfd >= 0) {
        close(dirfd);
    }
    printf("result=%s\n", category);
    emit_count();
    return code;
}

static int delete_one(int dirfd, const char *run, const char *name, const char *password) {
    SecKeychainRef store = NULL;
    char path[k_path_max];
    struct stat st;
    OSStatus status;
    int fd;
    if (fstatat(dirfd, name, &st, AT_SYMLINK_NOFOLLOW) != 0) {
        return errno == ENOENT ? 0 : -1;
    }
    if (S_ISLNK(st.st_mode) || !S_ISREG(st.st_mode)) {
        return -1;
    }
    if (join_name(run, name, path, sizeof path) != 0) {
        return -1;
    }
    fd = openat(dirfd, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) {
        return -1;
    }
    close(fd);
    status = open_store(path, &store);
    if (status != errSecSuccess || store == NULL) {
        diagnose(dirfd, "delete-open", (int)status);
        return -1;
    }
    if (unlock_store(store, password) != errSecSuccess || delete_store(store) != errSecSuccess) {
        CFRelease(store);
        return -1;
    }
    CFRelease(store);
    return 0;
}

static int cmd_delete(const char *run) {
    struct secrets secrets;
    Boolean prior = true;
    int changed = 0;
    int dirfd = -1;
    int code = 1;
    const char *category = "cleanup_incomplete";
    memset(&secrets, 0, sizeof secrets);
    if (walk_run(run) != 0) {
        category = "path_rejected";
        goto done;
    }
    dirfd = open(run, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (dirfd < 0 || read_secret(dirfd, "signing.pass", secrets.signing) != 0 ||
        read_secret(dirfd, "data.pass", secrets.data) != 0) {
        goto done;
    }
    if (ui_enter(&prior, &changed) != 0) {
        category = "interaction_bracket";
        goto done;
    }
    if (delete_one(dirfd, run, REAL_STORE_SIGNING_BASENAME, secrets.signing) != 0 ||
        delete_one(dirfd, run, REAL_STORE_DATA_BASENAME, secrets.data) != 0) {
        goto restore;
    }
    category = "ok";
    code = 0;
restore:
    if (changed && ui_leave(prior) != 0) {
        category = "interaction_bracket";
        code = 1;
    }
done:
    if (dirfd >= 0 && code == 0) {
        unlink_name(dirfd, "signing.pass");
        unlink_name(dirfd, "data.pass");
    }
    zero_secrets(&secrets);
    if (dirfd >= 0) {
        close(dirfd);
    }
    printf("result=%s\n", category);
    emit_count();
    return code;
}

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: real-store-provision command run-directory\n");
        return 2;
    }
    umask(077);
    if (strcmp(argv[1], "create-stores") == 0) {
        return cmd_create(argv[2]);
    }
    if (strcmp(argv[1], "import-identity") == 0) {
        return cmd_import(argv[2]);
    }
    if (strcmp(argv[1], "unlock-signing") == 0) {
        return cmd_lock_state(argv[2], REAL_STORE_SIGNING_BASENAME, "signing.pass", 1);
    }
    if (strcmp(argv[1], "lock-signing") == 0) {
        return cmd_lock_state(argv[2], REAL_STORE_SIGNING_BASENAME, "signing.pass", 0);
    }
    if (strcmp(argv[1], "unlock-data") == 0) {
        return cmd_lock_state(argv[2], REAL_STORE_DATA_BASENAME, "data.pass", 1);
    }
    if (strcmp(argv[1], "lock-data") == 0) {
        return cmd_lock_state(argv[2], REAL_STORE_DATA_BASENAME, "data.pass", 0);
    }
    if (strcmp(argv[1], "delete-owned") == 0) {
        return cmd_delete(argv[2]);
    }
    fprintf(stderr, "usage: real-store-provision command run-directory\n");
    return 2;
}
