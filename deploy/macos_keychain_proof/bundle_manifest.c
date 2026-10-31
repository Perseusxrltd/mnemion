#include "bundle_manifest.h"

#include <CommonCrypto/CommonDigest.h>

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

enum { k_max_entries = 256, k_max_path = 768 };

struct bundle_entry {
    char kind;
    char path[k_max_path];
    unsigned char sha[CC_SHA256_DIGEST_LENGTH];
};

static void set_error(char *error, size_t error_cap, const char *text) {
    if (error != NULL && error_cap > 0) {
        snprintf(error, error_cap, "%s", text);
    }
}

static int allowed_path(const char *path) {
    const unsigned char *cursor = (const unsigned char *)path;
    if (path[0] == '\0' || path[0] == '/') {
        return -1;
    }
    for (; *cursor != '\0'; cursor++) {
        unsigned char byte = *cursor;
        int ok = (byte >= 'A' && byte <= 'Z') || (byte >= 'a' && byte <= 'z') ||
                 (byte >= '0' && byte <= '9') || byte == '.' || byte == '_' ||
                 byte == '-' || byte == '/';
        if (!ok) {
            return -1;
        }
    }
    if (strstr(path, "..") != NULL || strstr(path, "//") != NULL) {
        return -1;
    }
    return 0;
}

static int hash_file(const char *path, unsigned char sha[CC_SHA256_DIGEST_LENGTH]) {
    unsigned char buffer[4096];
    CC_SHA256_CTX context;
    int fd = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) {
        return -1;
    }
    CC_SHA256_Init(&context);
    for (;;) {
        ssize_t count = read(fd, buffer, sizeof buffer);
        if (count < 0) {
            close(fd);
            return -1;
        }
        if (count == 0) {
            break;
        }
        CC_SHA256_Update(&context, buffer, (CC_LONG)count);
    }
    close(fd);
    CC_SHA256_Final(sha, &context);
    return 0;
}

static int collect(const char *root, const char *relative, struct bundle_entry *entries, size_t *count) {
    char directory[k_max_path];
    DIR *handle;
    struct dirent *item;
    int length;
    if (relative[0] == '\0') {
        length = snprintf(directory, sizeof directory, "%s", root);
    } else {
        length = snprintf(directory, sizeof directory, "%s/%s", root, relative);
    }
    if (length < 0 || (size_t)length >= sizeof directory) {
        return -1;
    }
    handle = opendir(directory);
    if (handle == NULL) {
        return -1;
    }
    while ((item = readdir(handle)) != NULL) {
        char child_rel[k_max_path];
        char child_abs[k_max_path];
        struct stat info;
        int rel_length;
        int abs_length;
        if (strcmp(item->d_name, ".") == 0 || strcmp(item->d_name, "..") == 0) {
            continue;
        }
        if (relative[0] == '\0') {
            rel_length = snprintf(child_rel, sizeof child_rel, "%s", item->d_name);
        } else {
            rel_length = snprintf(child_rel, sizeof child_rel, "%s/%s", relative, item->d_name);
        }
        abs_length = snprintf(child_abs, sizeof child_abs, "%s/%s", directory, item->d_name);
        if (rel_length < 0 || abs_length < 0 ||
            (size_t)rel_length >= sizeof child_rel || (size_t)abs_length >= sizeof child_abs ||
            allowed_path(child_rel) != 0) {
            closedir(handle);
            return -1;
        }
        if (lstat(child_abs, &info) != 0 || S_ISLNK(info.st_mode)) {
            closedir(handle);
            return -1;
        }
        if (*count >= k_max_entries) {
            closedir(handle);
            return -1;
        }
        memset(&entries[*count], 0, sizeof entries[*count]);
        memcpy(entries[*count].path, child_rel, (size_t)rel_length + 1);
        if (S_ISDIR(info.st_mode)) {
            entries[*count].kind = 'd';
            (*count)++;
            if (collect(root, child_rel, entries, count) != 0) {
                closedir(handle);
                return -1;
            }
        } else if (S_ISREG(info.st_mode)) {
            entries[*count].kind = 'f';
            if (hash_file(child_abs, entries[*count].sha) != 0) {
                closedir(handle);
                return -1;
            }
            (*count)++;
        } else {
            closedir(handle);
            return -1;
        }
    }
    closedir(handle);
    return 0;
}

static int compare_entries(const void *left, const void *right) {
    const struct bundle_entry *a = left;
    const struct bundle_entry *b = right;
    return strcmp(a->path, b->path);
}

static int load_entries(const char *root, struct bundle_entry *entries, size_t *count) {
    *count = 0;
    if (collect(root, "", entries, count) != 0) {
        return -1;
    }
    qsort(entries, *count, sizeof entries[0], compare_entries);
    return 0;
}

enum { k_manifest_cap = 262144 };

static int append_text(char *text, size_t cap, size_t *used, const char *piece) {
    size_t length = strlen(piece);
    if (text == NULL || used == NULL || piece == NULL || *used >= cap || length >= cap - *used) {
        return -1;
    }
    memcpy(text + *used, piece, length);
    *used += length;
    text[*used] = '\0';
    return 0;
}

static int render_entries(const struct bundle_entry *entries, size_t count, char **out, size_t *out_len) {
    char *text;
    size_t used = 0;
    size_t index;
    text = malloc(k_manifest_cap);
    if (text == NULL) {
        return -1;
    }
    text[0] = '\0';
    if (append_text(text, k_manifest_cap, &used, "mnemion-helper-files v1\n") != 0) {
        free(text);
        return -1;
    }
    for (index = 0; index < count; index++) {
        char line[k_max_path + 80];
        int written;
        if (entries[index].kind == 'd') {
            written = snprintf(line, sizeof line, "dir %s\n", entries[index].path);
        } else if (entries[index].kind == 'f') {
            char hex[CC_SHA256_DIGEST_LENGTH * 2 + 1];
            size_t byte;
            for (byte = 0; byte < CC_SHA256_DIGEST_LENGTH; byte++) {
                snprintf(hex + byte * 2, 3, "%02x", entries[index].sha[byte]);
            }
            written = snprintf(line, sizeof line, "file %s %s\n", hex, entries[index].path);
        } else {
            free(text);
            return -1;
        }
        if (written < 0 || (size_t)written >= sizeof line ||
            append_text(text, k_manifest_cap, &used, line) != 0) {
            free(text);
            return -1;
        }
    }
    *out = text;
    *out_len = used;
    return 0;
}

static int render_root(const char *root, char **out, size_t *out_len) {
    struct bundle_entry entries[k_max_entries];
    size_t count = 0;
    if (root == NULL || out == NULL || out_len == NULL || load_entries(root, entries, &count) != 0) {
        return -1;
    }
    return render_entries(entries, count, out, out_len);
}

static int write_all(int fd, const char *bytes, size_t length) {
    size_t filled = 0;
    while (filled < length) {
        ssize_t count = write(fd, bytes + filled, length - filled);
        if (count <= 0) {
            return -1;
        }
        filled += (size_t)count;
    }
    return 0;
}

/* One descriptor stays open for the whole read. A short read or a read
   error fails closed. The path is not closed and opened again. */
static int read_kept(const char *path, char **out, size_t *out_len) {
    int fd = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    struct stat info;
    char *buffer;
    size_t filled = 0;
    char extra;
    ssize_t extra_count;
    if (fd < 0) {
        return -1;
    }
    if (fstat(fd, &info) != 0 || !S_ISREG(info.st_mode) || info.st_size <= 0 ||
        (unsigned long long)info.st_size > k_manifest_cap) {
        close(fd);
        return -1;
    }
    buffer = malloc((size_t)info.st_size);
    if (buffer == NULL) {
        close(fd);
        return -1;
    }
    while (filled < (size_t)info.st_size) {
        ssize_t count = read(fd, buffer + filled, (size_t)info.st_size - filled);
        if (count <= 0) {
            close(fd);
            free(buffer);
            return -1;
        }
        filled += (size_t)count;
    }
    extra_count = read(fd, &extra, 1);
    if (close(fd) != 0 || extra_count != 0) {
        free(buffer);
        return -1;
    }
    *out = buffer;
    *out_len = filled;
    return 0;
}

int bundle_manifest_write(const char *root, const char *destination, char *error, size_t error_cap) {
    char *text = NULL;
    size_t length = 0;
    int fd;
    if (destination == NULL || render_root(root, &text, &length) != 0) {
        free(text);
        set_error(error, error_cap, "helper bundle walk failed");
        return -1;
    }
    fd = open(destination, O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC, 0644);
    if (fd < 0 || write_all(fd, text, length) != 0 || fsync(fd) != 0) {
        if (fd >= 0) {
            close(fd);
        }
        free(text);
        set_error(error, error_cap, "helper manifest write failed");
        return -1;
    }
    if (close(fd) != 0) {
        free(text);
        set_error(error, error_cap, "helper manifest close failed");
        return -1;
    }
    free(text);
    return 0;
}

int bundle_manifest_check(const char *root, const char *manifest_path, char *error, size_t error_cap) {
    char *live = NULL;
    char *expected = NULL;
    size_t live_len = 0;
    size_t expected_len = 0;
    int different;
    if (render_root(root, &live, &live_len) != 0) {
        set_error(error, error_cap, "helper bundle walk failed");
        return -1;
    }
    if (read_kept(manifest_path, &expected, &expected_len) != 0) {
        free(live);
        set_error(error, error_cap, "helper manifest read failed");
        return -1;
    }
    different = live_len != expected_len || memcmp(live, expected, live_len) != 0;
    free(live);
    free(expected);
    if (different) {
        set_error(error, error_cap, "helper bundle bytes differ from the frozen manifest");
        return -1;
    }
    return 0;
}

int bundle_manifest_digest(const char *root, char *hex, size_t hex_cap, char *error, size_t error_cap) {
    char *text = NULL;
    size_t length = 0;
    unsigned char sha[CC_SHA256_DIGEST_LENGTH];
    size_t index;
    if (hex == NULL || hex_cap < CC_SHA256_DIGEST_LENGTH * 2 + 1) {
        set_error(error, error_cap, "helper manifest digest buffer is short");
        return -1;
    }
    if (render_root(root, &text, &length) != 0 || length == 0 || length > k_manifest_cap) {
        free(text);
        set_error(error, error_cap, "helper bundle walk failed");
        return -1;
    }
    CC_SHA256(text, (CC_LONG)length, sha);
    free(text);
    for (index = 0; index < CC_SHA256_DIGEST_LENGTH; index++) {
        snprintf(hex + index * 2, 3, "%02x", sha[index]);
    }
    hex[CC_SHA256_DIGEST_LENGTH * 2] = '\0';
    return 0;
}

int bundle_trees_equal(const char *left, const char *right, char *error, size_t error_cap) {
    char *left_text = NULL;
    char *right_text = NULL;
    size_t left_len = 0;
    size_t right_len = 0;
    int different;
    if (render_root(left, &left_text, &left_len) != 0 || render_root(right, &right_text, &right_len) != 0) {
        free(left_text);
        free(right_text);
        set_error(error, error_cap, "helper bundle walk failed");
        return -1;
    }
    different = left_len != right_len || memcmp(left_text, right_text, left_len) != 0;
    free(left_text);
    free(right_text);
    if (different) {
        set_error(error, error_cap, "helper trees differ");
        return -1;
    }
    return 0;
}
