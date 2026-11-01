#include "fixture_store_syntax.h"

#include <string.h>

/* Source-only rejection cases for the pure guard checks.
   Not linked by compile_only.sh. Astra selects the first execution.
   These cases do not open a keychain, sign, or read secret bytes. */

static int expect(int actual, int wanted) {
    return actual == wanted ? 0 : -1;
}

static int fixture_policy_cases(const char *prefix_s, const char *prefix_a, const char *nonce, const char *service,
                                const char *account, const char *real_s, const char *real_a);

int fixture_store_rejection_cases(void) {
    const char *prefix_s = "mnemion-disposable-service-";
    const char *prefix_a = "mnemion-disposable-account-";
    const char *nonce = "0123456789abcdef0123456789abcdef";
    const char *service = "mnemion-disposable-service-0123456789abcdef0123456789abcdef";
    const char *account = "mnemion-disposable-account-0123456789abcdef0123456789abcdef";
    const char *real_s = "mnemion-studio Safe Storage";
    const char *real_a = "mnemion-studio Key";
    const char *metadata = "disposable fixture store";
    char joined[256];
    if (expect(fixture_syntax_config(NULL, NULL, NULL, NULL, NULL, NULL, real_s, real_a),
               FIXTURE_SYNTAX_MISSING) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_config("compile_only", "compile_only: not an owned store", prefix_s, prefix_a,
                                     "throwaway.keychain", "fixture-run.txt", real_s, real_a),
               FIXTURE_SYNTAX_COMPILE_ONLY) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_config("fixture", "UNSUBSTITUTED fixture", prefix_s, prefix_a,
                                     "throwaway.keychain", "fixture-run.txt", real_s, real_a),
               FIXTURE_SYNTAX_UNSUBSTITUTED) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_config("fixture", "compile_only leftover", prefix_s, prefix_a,
                                     "throwaway.keychain", "fixture-run.txt", real_s, real_a),
               FIXTURE_SYNTAX_UNSUBSTITUTED) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_config("fixture", metadata, real_s, prefix_a, "throwaway.keychain",
                                     "fixture-run.txt", real_s, real_a),
               FIXTURE_SYNTAX_REAL_PROFILE) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_config("fixture", metadata, prefix_s, prefix_a, "login.keychain-db",
                                     "fixture-run.txt", real_s, real_a),
               FIXTURE_SYNTAX_PATH) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_config("fixture", metadata, "mnemion-disposable-other-", prefix_a,
                                     "throwaway.keychain", "fixture-run.txt", real_s, real_a),
               FIXTURE_SYNTAX_NAME) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_config("fixture", metadata, "ProtectedCloudStorage-", prefix_a,
                                     "throwaway.keychain", "fixture-run.txt", real_s, real_a),
               FIXTURE_SYNTAX_REAL_PROFILE) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_config("fixture", metadata, prefix_s, prefix_a, "other.keychain",
                                     "fixture-run.txt", real_s, real_a),
               FIXTURE_SYNTAX_PATH) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_config("fixture", metadata, prefix_s, prefix_a, "throwaway.keychain",
                                     "fixture-run.txt", real_s, real_a),
               FIXTURE_SYNTAX_OK) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_names(prefix_s, prefix_a, "ABCDEF0123456789ABCDEF0123456789", service, account,
                                    real_s, real_a),
               FIXTURE_SYNTAX_NONCE) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_names(prefix_s, prefix_a, nonce, real_s, account, real_s, real_a),
               FIXTURE_SYNTAX_REAL_PROFILE) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_names(prefix_s, prefix_a, nonce, service, "mnemion-disposable-account-other",
                                    real_s, real_a),
               FIXTURE_SYNTAX_NAME) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_names(prefix_s, prefix_a, nonce, service, account, real_s, real_a),
               FIXTURE_SYNTAX_OK) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_run_path("owned/run"), FIXTURE_SYNTAX_PATH) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_run_path("/tmp/../owned"), FIXTURE_SYNTAX_PATH) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_run_path("/Users/x/Library/Keychains"), FIXTURE_SYNTAX_REAL_PROFILE) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_run_path("/owned/run"), FIXTURE_SYNTAX_OK) != 0) {
        return -1;
    }
    if (fixture_syntax_join("/owned/run", "throwaway.keychain", joined, sizeof joined) != 0 ||
        strcmp(joined, "/owned/run/throwaway.keychain") != 0) {
        return -1;
    }
    if (fixture_syntax_join("/owned/run", "login.keychain-db", joined, sizeof joined) == 0) {
        return -1;
    }
    if (expect(fixture_syntax_scope_count(0), FIXTURE_SYNTAX_SCOPE) != 0 ||
        expect(fixture_syntax_scope_count(2), FIXTURE_SYNTAX_SCOPE) != 0 ||
        expect(fixture_syntax_scope_count(1), FIXTURE_SYNTAX_OK) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_request_boolean(1, "/Users/x/Library/Keychains/login.keychain-db"),
               FIXTURE_SYNTAX_REQUEST) != 0 ||
        expect(fixture_syntax_request_boolean(0, "/owned/run"), FIXTURE_SYNTAX_REQUEST) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_explicit_list(1, 1, 0, 0), FIXTURE_SYNTAX_OK) != 0 ||
        expect(fixture_syntax_explicit_list(1, 1, 1, 0), FIXTURE_SYNTAX_SCOPE) != 0 ||
        expect(fixture_syntax_explicit_list(2, 1, 0, 0), FIXTURE_SYNTAX_SCOPE) != 0 ||
        expect(fixture_syntax_explicit_list(1, 0, 0, 0), FIXTURE_SYNTAX_SCOPE) != 0 ||
        expect(fixture_syntax_explicit_list(1, 1, 0, 1), FIXTURE_SYNTAX_REAL_PROFILE) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_names("ProtectedCloudStorage-", prefix_a, nonce,
                                    "ProtectedCloudStorage-0123456789abcdef0123456789abcdef", account, real_s,
                                    real_a),
               FIXTURE_SYNTAX_REAL_PROFILE) != 0) {
        return -1;
    }
    if (fixture_policy_cases(prefix_s, prefix_a, nonce, service, account, real_s, real_a) != 0) {
        return -1;
    }
    return 0;
}

static int same_creation(int directories_ok, int ciphertext_empty, int marker_absent, int key_state, int wanted) {
    if (expect(fixture_syntax_creation(directories_ok, ciphertext_empty, marker_absent, key_state, 0), wanted) !=
            0 ||
        expect(fixture_syntax_creation(directories_ok, ciphertext_empty, marker_absent, key_state, 1), wanted) !=
            0) {
        return -1;
    }
    return 0;
}

static int fixture_policy_cases(const char *prefix_s, const char *prefix_a, const char *nonce, const char *service,
                                const char *account, const char *real_s, const char *real_a) {
    const char *sealed = "/owned/run";
    int operate = 1;
    (void)prefix_s;
    (void)prefix_a;
    if (expect(fixture_syntax_helper_launch(1, "/tmp/not-the-run", "/Users/x/Library/Keychains"),
               FIXTURE_SYNTAX_OK) != 0 ||
        expect(fixture_syntax_helper_launch(1, NULL, NULL), FIXTURE_SYNTAX_OK) != 0 ||
        expect(fixture_syntax_helper_launch(2, NULL, NULL), FIXTURE_SYNTAX_PATH) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_direct_binding(0, "/somewhere/else", sealed), FIXTURE_SYNTAX_OK) != 0 ||
        expect(fixture_syntax_direct_binding(1, sealed, sealed), FIXTURE_SYNTAX_OK) != 0 ||
        expect(fixture_syntax_direct_binding(1, "/owned/other", sealed), FIXTURE_SYNTAX_PATH) != 0 ||
        expect(fixture_syntax_direct_binding(1, "/Users/x/Library/Keychains/login.keychain-db", sealed),
               FIXTURE_SYNTAX_PATH) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_sealed_match(sealed, sealed, nonce, nonce, service, service, account, account, 501, 501,
                                           11, 11, 22, 22, 33, 33, 44, 44, real_s, real_a),
               FIXTURE_SYNTAX_OK) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_sealed_match(sealed, "/owned/other", nonce, nonce, service, service, account, account,
                                           501, 501, 11, 11, 22, 22, 33, 33, 44, 44, real_s, real_a),
               FIXTURE_SYNTAX_PATH) != 0 ||
        expect(fixture_syntax_sealed_match(sealed, sealed, nonce, "0123456789abcdef0123456789abcdee", service,
                                           service, account, account, 501, 501, 11, 11, 22, 22, 33, 33, 44, 44, real_s,
                                           real_a),
               FIXTURE_SYNTAX_NONCE) != 0 ||
        expect(fixture_syntax_sealed_match(sealed, sealed, nonce, nonce, service, service, account, account, 501, 502,
                                           11, 11, 22, 22, 33, 33, 44, 44, real_s, real_a),
               FIXTURE_SYNTAX_SCOPE) != 0 ||
        expect(fixture_syntax_sealed_match(sealed, sealed, nonce, nonce, service, service, account, account, 501, 501,
                                           11, 99, 22, 22, 33, 33, 44, 44, real_s, real_a),
               FIXTURE_SYNTAX_SCOPE) != 0 ||
        expect(fixture_syntax_sealed_match(sealed, sealed, nonce, nonce, service,
                                           "mnemion-disposable-service-0123456789abcdef0123456789abcdee", account,
                                           account, 501, 501, 11, 11, 22, 22, 33, 33, 44, 44, real_s, real_a),
               FIXTURE_SYNTAX_NAME) != 0) {
        return -1;
    }
    /* Predicate coverage only. These booleans are not wrapper, fsync, or restart evidence. */
    if (fixture_syntax_ui_setup(1, 1, 1, 0, &operate) != FIXTURE_UI_READY || operate != 1) {
        return -1;
    }
    operate = 1;
    if (fixture_syntax_ui_setup(0, 1, 1, 0, &operate) != FIXTURE_UI_SETUP_FAILED || operate != 0 ||
        fixture_syntax_ui_setup(1, 0, 1, 0, &operate) != FIXTURE_UI_SETUP_FAILED || operate != 0 ||
        fixture_syntax_ui_setup(1, 1, 0, 0, &operate) != FIXTURE_UI_SETUP_FAILED || operate != 0 ||
        fixture_syntax_ui_setup(1, 1, 1, 1, &operate) != FIXTURE_UI_SETUP_FAILED || operate != 0) {
        return -1;
    }
    if (fixture_syntax_ui_restore(1, 1, 1, 1) != FIXTURE_UI_READY ||
        fixture_syntax_ui_restore(0, 1, 1, 0) != FIXTURE_UI_READY ||
        fixture_syntax_ui_restore(1, 0, 1, 1) != FIXTURE_UI_RESTORE_FAILED ||
        fixture_syntax_ui_restore(1, 1, 0, 1) != FIXTURE_UI_RESTORE_FAILED ||
        fixture_syntax_ui_restore(1, 1, 1, 0) != FIXTURE_UI_RESTORE_FAILED ||
        fixture_syntax_ui_restore(0, 1, 1, 1) != FIXTURE_UI_RESTORE_FAILED) {
        return -1;
    }
    if (same_creation(1, 1, 1, 0, FIXTURE_CREATE_ONCE) != 0 ||
        same_creation(1, 1, 1, 1, FIXTURE_CREATE_READ_EXISTING) != 0 ||
        same_creation(1, 0, 1, 1, FIXTURE_CREATE_READ_EXISTING) != 0 ||
        same_creation(1, 1, 0, 1, FIXTURE_CREATE_READ_EXISTING) != 0 ||
        same_creation(1, 0, 1, 0, FIXTURE_CREATE_REFUSED) != 0 ||
        same_creation(1, 1, 0, 0, FIXTURE_CREATE_REFUSED) != 0 ||
        same_creation(1, 0, 0, 0, FIXTURE_CREATE_REFUSED) != 0 ||
        same_creation(0, 1, 1, 0, FIXTURE_CREATE_REFUSED) != 0 ||
        same_creation(1, 1, 1, -1, FIXTURE_CREATE_REFUSED) != 0) {
        return -1;
    }
    if (expect(fixture_syntax_marker_survives(0), FIXTURE_SYNTAX_OK) != 0 ||
        expect(fixture_syntax_marker_survives(1), FIXTURE_SYNTAX_REQUEST) != 0) {
        return -1;
    }
    return 0;
}
