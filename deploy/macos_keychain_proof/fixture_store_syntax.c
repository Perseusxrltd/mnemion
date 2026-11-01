#include "fixture_store_syntax.h"

#include <stdio.h>
#include <string.h>

static int blank(const char *text) {
    return text == NULL || text[0] == '\0';
}

static int unsubstituted(const char *text) {
    return text != NULL && strstr(text, "UNSUBSTITUTED") != NULL;
}

static int has_space_or_break(const char *text) {
    return text != NULL && (strchr(text, ' ') != NULL || strchr(text, '\n') != NULL ||
                            strchr(text, '\r') != NULL || strchr(text, '\t') != NULL);
}

static int forbidden_overlap(const char *value, const char *forbidden) {
    if (blank(value) || blank(forbidden)) {
        return 1;
    }
    if (strcmp(value, forbidden) == 0 || strstr(value, forbidden) != NULL) {
        return 1;
    }
    return 0;
}

static int protected_cloud_name(const char *value) {
    return value != NULL && strstr(value, "ProtectedCloudStorage") != NULL;
}

static int hex_nonce(const char *nonce) {
    unsigned long index;
    if (nonce == NULL || strlen(nonce) != 32) {
        return -1;
    }
    for (index = 0; index < 32; index++) {
        char character = nonce[index];
        int digit = (character >= '0' && character <= '9') || (character >= 'a' && character <= 'f');
        if (!digit) {
            return -1;
        }
    }
    return 0;
}

int fixture_syntax_basename(const char *basename) {
    if (blank(basename) || has_space_or_break(basename)) {
        return FIXTURE_SYNTAX_PATH;
    }
    if (strcmp(basename, ".") == 0 || strcmp(basename, "..") == 0) {
        return FIXTURE_SYNTAX_PATH;
    }
    if (strchr(basename, '/') != NULL || strchr(basename, '\\') != NULL) {
        return FIXTURE_SYNTAX_PATH;
    }
    if (strcmp(basename, "login.keychain") == 0 || strcmp(basename, "login.keychain-db") == 0) {
        return FIXTURE_SYNTAX_PATH;
    }
    if (strstr(basename, "Safe Storage") != NULL || strstr(basename, "Library") != NULL) {
        return FIXTURE_SYNTAX_REAL_PROFILE;
    }
    return FIXTURE_SYNTAX_OK;
}

int fixture_syntax_run_path(const char *run_directory) {
    const char *cursor;
    if (blank(run_directory) || has_space_or_break(run_directory)) {
        return FIXTURE_SYNTAX_PATH;
    }
    if (run_directory[0] != '/' || strlen(run_directory) < 2 || strlen(run_directory) > 900) {
        return FIXTURE_SYNTAX_PATH;
    }
    if (run_directory[strlen(run_directory) - 1] == '/') {
        return FIXTURE_SYNTAX_PATH;
    }
    if (strstr(run_directory, "//") != NULL || strstr(run_directory, "/./") != NULL ||
        strstr(run_directory, "/../") != NULL || strstr(run_directory, "\\") != NULL) {
        return FIXTURE_SYNTAX_PATH;
    }
    if (strncmp(run_directory, "/../", 4) == 0 || strcmp(run_directory, "/..") == 0) {
        return FIXTURE_SYNTAX_PATH;
    }
    cursor = strrchr(run_directory, '/');
    if (cursor == NULL || strcmp(cursor + 1, "..") == 0 || strcmp(cursor + 1, ".") == 0) {
        return FIXTURE_SYNTAX_PATH;
    }
    if (strstr(run_directory, "/Library/Keychains") != NULL ||
        strstr(run_directory, "login.keychain") != NULL) {
        return FIXTURE_SYNTAX_REAL_PROFILE;
    }
    return FIXTURE_SYNTAX_OK;
}

int fixture_syntax_join(const char *run_directory, const char *basename, char *out, size_t out_cap) {
    int written;
    if (out == NULL || out_cap == 0) {
        return -1;
    }
    out[0] = '\0';
    if (fixture_syntax_run_path(run_directory) != FIXTURE_SYNTAX_OK ||
        fixture_syntax_basename(basename) != FIXTURE_SYNTAX_OK) {
        return -1;
    }
    written = snprintf(out, out_cap, "%s/%s", run_directory, basename);
    if (written < 0 || (size_t)written >= out_cap) {
        out[0] = '\0';
        return -1;
    }
    return 0;
}

int fixture_syntax_scope_count(int count) {
    return count == 1 ? FIXTURE_SYNTAX_OK : FIXTURE_SYNTAX_SCOPE;
}

int fixture_syntax_request_boolean(int allowed, const char *path) {
    (void)allowed;
    (void)path;
    return FIXTURE_SYNTAX_REQUEST;
}

int fixture_syntax_config(const char *store_class, const char *metadata,
                          const char *service_prefix, const char *account_prefix,
                          const char *store_basename, const char *record_basename,
                          const char *forbidden_service, const char *forbidden_account) {
    if (blank(forbidden_service) || blank(forbidden_account)) {
        return FIXTURE_SYNTAX_MISSING;
    }
    if (blank(store_class) || blank(metadata) || blank(service_prefix) || blank(account_prefix) ||
        blank(store_basename) || blank(record_basename)) {
        return FIXTURE_SYNTAX_MISSING;
    }
    if (strcmp(store_class, "compile_only") == 0) {
        return FIXTURE_SYNTAX_COMPILE_ONLY;
    }
    if (strcmp(store_class, "fixture") != 0 || unsubstituted(store_class) || unsubstituted(metadata) ||
        strstr(metadata, "compile_only") != NULL) {
        return FIXTURE_SYNTAX_UNSUBSTITUTED;
    }
    if (unsubstituted(service_prefix) || unsubstituted(account_prefix) || unsubstituted(store_basename) ||
        unsubstituted(record_basename)) {
        return FIXTURE_SYNTAX_UNSUBSTITUTED;
    }
    if (protected_cloud_name(service_prefix) || protected_cloud_name(account_prefix) ||
        forbidden_overlap(service_prefix, forbidden_service) ||
        forbidden_overlap(service_prefix, forbidden_account) ||
        forbidden_overlap(account_prefix, forbidden_service) ||
        forbidden_overlap(account_prefix, forbidden_account)) {
        return FIXTURE_SYNTAX_REAL_PROFILE;
    }
    if (strcmp(service_prefix, FIXTURE_FIXED_SERVICE_PREFIX) != 0 ||
        strcmp(account_prefix, FIXTURE_FIXED_ACCOUNT_PREFIX) != 0 ||
        has_space_or_break(service_prefix) || has_space_or_break(account_prefix)) {
        return FIXTURE_SYNTAX_NAME;
    }
    if (fixture_syntax_basename(store_basename) != FIXTURE_SYNTAX_OK ||
        fixture_syntax_basename(record_basename) != FIXTURE_SYNTAX_OK ||
        strcmp(store_basename, FIXTURE_FIXED_STORE_BASENAME) != 0 ||
        strcmp(record_basename, FIXTURE_FIXED_RECORD_BASENAME) != 0) {
        return FIXTURE_SYNTAX_PATH;
    }
    return FIXTURE_SYNTAX_OK;
}

int fixture_syntax_names(const char *service_prefix, const char *account_prefix,
                         const char *nonce, const char *service, const char *account,
                         const char *forbidden_service, const char *forbidden_account) {
    char expect_service[128];
    char expect_account[128];
    int written;
    if (blank(service_prefix) || blank(account_prefix) || blank(service) || blank(account) ||
        blank(forbidden_service) || blank(forbidden_account)) {
        return FIXTURE_SYNTAX_MISSING;
    }
    if (hex_nonce(nonce) != 0) {
        return FIXTURE_SYNTAX_NONCE;
    }
    if (protected_cloud_name(service_prefix) || protected_cloud_name(account_prefix) ||
        protected_cloud_name(service) || protected_cloud_name(account) ||
        forbidden_overlap(service, forbidden_service) || forbidden_overlap(service, forbidden_account) ||
        forbidden_overlap(account, forbidden_service) || forbidden_overlap(account, forbidden_account)) {
        return FIXTURE_SYNTAX_REAL_PROFILE;
    }
    written = snprintf(expect_service, sizeof expect_service, "%s%s", service_prefix, nonce);
    if (written < 0 || (unsigned long)written >= sizeof expect_service) {
        return FIXTURE_SYNTAX_NAME;
    }
    written = snprintf(expect_account, sizeof expect_account, "%s%s", account_prefix, nonce);
    if (written < 0 || (unsigned long)written >= sizeof expect_account) {
        return FIXTURE_SYNTAX_NAME;
    }
    if (strcmp(service, expect_service) != 0 || strcmp(account, expect_account) != 0) {
        return FIXTURE_SYNTAX_NAME;
    }
    if (strcmp(service_prefix, FIXTURE_FIXED_SERVICE_PREFIX) != 0 ||
        strcmp(account_prefix, FIXTURE_FIXED_ACCOUNT_PREFIX) != 0) {
        return FIXTURE_SYNTAX_NAME;
    }
    return FIXTURE_SYNTAX_OK;
}

int fixture_syntax_explicit_list(int count, int match_search_list, int deprecated_search,
                                 int protected_cloud_service) {
    if (protected_cloud_service) {
        return FIXTURE_SYNTAX_REAL_PROFILE;
    }
    if (deprecated_search || !match_search_list || count != 1) {
        return FIXTURE_SYNTAX_SCOPE;
    }
    return FIXTURE_SYNTAX_OK;
}

int fixture_syntax_helper_launch(int argc, const char *environment_path, const char *xpc_path) {
    /* Launchd does not pass the run directory. These values cannot select one. */
    (void)environment_path;
    (void)xpc_path;
    return argc == 1 ? FIXTURE_SYNTAX_OK : FIXTURE_SYNTAX_PATH;
}

int fixture_syntax_direct_binding(int path_supplied, const char *argument, const char *sealed_directory) {
    if (fixture_syntax_run_path(sealed_directory) != FIXTURE_SYNTAX_OK) {
        return FIXTURE_SYNTAX_PATH;
    }
    if (!path_supplied) {
        return FIXTURE_SYNTAX_OK;
    }
    if (argument == NULL || strcmp(argument, sealed_directory) != 0) {
        return FIXTURE_SYNTAX_PATH;
    }
    return FIXTURE_SYNTAX_OK;
}

int fixture_syntax_sealed_match(const char *sealed_dir, const char *actual_dir, const char *sealed_nonce,
                                const char *actual_nonce, const char *sealed_service, const char *actual_service,
                                const char *sealed_account, const char *actual_account, unsigned long long sealed_euid,
                                unsigned long long actual_euid, unsigned long long sealed_run_dev,
                                unsigned long long actual_run_dev, unsigned long long sealed_run_ino,
                                unsigned long long actual_run_ino, unsigned long long sealed_store_dev,
                                unsigned long long actual_store_dev, unsigned long long sealed_store_ino,
                                unsigned long long actual_store_ino, const char *forbidden_service,
                                const char *forbidden_account) {
    int names;
    if (fixture_syntax_run_path(sealed_dir) != FIXTURE_SYNTAX_OK ||
        fixture_syntax_run_path(actual_dir) != FIXTURE_SYNTAX_OK || strcmp(sealed_dir, actual_dir) != 0) {
        return FIXTURE_SYNTAX_PATH;
    }
    if (sealed_euid != actual_euid || sealed_run_dev != actual_run_dev || sealed_run_ino != actual_run_ino ||
        sealed_store_dev != actual_store_dev || sealed_store_ino != actual_store_ino) {
        return FIXTURE_SYNTAX_SCOPE;
    }
    if (blank(sealed_nonce) || blank(actual_nonce) || strcmp(sealed_nonce, actual_nonce) != 0) {
        return FIXTURE_SYNTAX_NONCE;
    }
    if (blank(sealed_service) || blank(actual_service) || blank(sealed_account) || blank(actual_account) ||
        strcmp(sealed_service, actual_service) != 0 || strcmp(sealed_account, actual_account) != 0) {
        return FIXTURE_SYNTAX_NAME;
    }
    names = fixture_syntax_names(FIXTURE_FIXED_SERVICE_PREFIX, FIXTURE_FIXED_ACCOUNT_PREFIX, sealed_nonce,
                                 sealed_service, sealed_account, forbidden_service, forbidden_account);
    return names;
}

int fixture_syntax_ui_setup(int prior_ok, int set_ok, int read_ok, int read_allowed, int *operate) {
    if (operate != NULL) {
        *operate = 0;
    }
    if (!prior_ok || !set_ok || !read_ok || read_allowed != 0) {
        return FIXTURE_UI_SETUP_FAILED;
    }
    if (operate != NULL) {
        *operate = 1;
    }
    return FIXTURE_UI_READY;
}

int fixture_syntax_ui_restore(int prior_allowed, int set_ok, int read_ok, int read_allowed) {
    if ((prior_allowed != 0 && prior_allowed != 1) || !set_ok || !read_ok || read_allowed != prior_allowed) {
        return FIXTURE_UI_RESTORE_FAILED;
    }
    return FIXTURE_UI_READY;
}

int fixture_syntax_creation(int directories_ok, int ciphertext_empty, int marker_absent, int key_state,
                            int caller_claims_absent) {
    (void)caller_claims_absent;
    if (key_state == 1) {
        return FIXTURE_CREATE_READ_EXISTING;
    }
    if (key_state != 0 || !directories_ok || !ciphertext_empty || !marker_absent) {
        return FIXTURE_CREATE_REFUSED;
    }
    return FIXTURE_CREATE_ONCE;
}

int fixture_syntax_marker_survives(int unlinked_after_error) {
    return unlinked_after_error ? FIXTURE_SYNTAX_REQUEST : FIXTURE_SYNTAX_OK;
}
