#ifndef MNEMION_FIXTURE_STORE_SYNTAX_H
#define MNEMION_FIXTURE_STORE_SYNTAX_H

#include <stddef.h>

/* Pure admission checks. They do not open a store, sign, or read secret bytes.
   fixture_store_cases.c calls them. The compile-only lane does not. */

enum fixture_syntax {
    FIXTURE_SYNTAX_OK = 0,
    FIXTURE_SYNTAX_MISSING = 1,
    FIXTURE_SYNTAX_UNSUBSTITUTED = 2,
    FIXTURE_SYNTAX_COMPILE_ONLY = 3,
    FIXTURE_SYNTAX_REAL_PROFILE = 4,
    FIXTURE_SYNTAX_NONCE = 5,
    FIXTURE_SYNTAX_NAME = 6,
    FIXTURE_SYNTAX_PATH = 7,
    FIXTURE_SYNTAX_SCOPE = 8,
    FIXTURE_SYNTAX_REQUEST = 9
};

/* Fixed synthetic names. A generated header must copy these. It cannot
   substitute another prefix, including ProtectedCloudStorage. */
#define FIXTURE_FIXED_SERVICE_PREFIX "mnemion-disposable-service-"
#define FIXTURE_FIXED_ACCOUNT_PREFIX "mnemion-disposable-account-"
#define FIXTURE_FIXED_STORE_BASENAME "throwaway.keychain"
#define FIXTURE_FIXED_RECORD_BASENAME "fixture-run.txt"
#define FIXTURE_FIXED_CIPHERTEXT_DIR "ciphertext"
#define FIXTURE_FIXED_MARKER_NAME "creation-attempted"
#define FIXTURE_FIXED_LOCK_NAME "fixture.lock"

enum fixture_ui_result {
    FIXTURE_UI_READY = 0,
    FIXTURE_UI_SETUP_FAILED = 1,
    FIXTURE_UI_RESTORE_FAILED = 2
};

/* key_state 0: scoped item absent. 1: present. any other value: unknown. */
enum fixture_create_result {
    FIXTURE_CREATE_ONCE = 0,
    FIXTURE_CREATE_READ_EXISTING = 1,
    FIXTURE_CREATE_REFUSED = 2
};

int fixture_syntax_config(const char *store_class, const char *metadata,
                          const char *service_prefix, const char *account_prefix,
                          const char *store_basename, const char *record_basename,
                          const char *forbidden_service, const char *forbidden_account);

int fixture_syntax_names(const char *service_prefix, const char *account_prefix,
                         const char *nonce, const char *service, const char *account,
                         const char *forbidden_service, const char *forbidden_account);

int fixture_syntax_run_path(const char *run_directory);

int fixture_syntax_basename(const char *basename);

int fixture_syntax_join(const char *run_directory, const char *basename, char *out, size_t out_cap);

int fixture_syntax_scope_count(int count);

/* A request or environment boolean never admits a store. Both arguments are ignored. */
int fixture_syntax_request_boolean(int allowed, const char *path);

/* count is the search-list length. match_search_list is 1 only for kSecMatchSearchList.
   deprecated_search is 1 when a deprecated search API would be used.
   protected_cloud_service is 1 when the service is Apple's ProtectedCloudStorage exception. */
int fixture_syntax_explicit_list(int count, int match_search_list, int deprecated_search,
                                 int protected_cloud_service);

/* argc 1 is normal launchd. environment_path and xpc_path are ignored. */
int fixture_syntax_helper_launch(int argc, const char *environment_path, const char *xpc_path);

/* path_supplied 0 binds the sealed directory. path_supplied 1 requires byte equality. */
int fixture_syntax_direct_binding(int path_supplied, const char *argument, const char *sealed_directory);

int fixture_syntax_sealed_match(const char *sealed_dir, const char *actual_dir, const char *sealed_nonce,
                                const char *actual_nonce, const char *sealed_service, const char *actual_service,
                                const char *sealed_account, const char *actual_account, unsigned long long sealed_euid,
                                unsigned long long actual_euid, unsigned long long sealed_run_dev,
                                unsigned long long actual_run_dev, unsigned long long sealed_run_ino,
                                unsigned long long actual_run_ino, unsigned long long sealed_store_dev,
                                unsigned long long actual_store_dev, unsigned long long sealed_store_ino,
                                unsigned long long actual_store_ino, const char *forbidden_service,
                                const char *forbidden_account);

/* operate is set to 1 only when the bracket may run the Keychain call. */
int fixture_syntax_ui_setup(int prior_ok, int set_ok, int read_ok, int read_allowed, int *operate);

/* prior_allowed, read_allowed: 0 disabled, 1 enabled. */
int fixture_syntax_ui_restore(int prior_allowed, int set_ok, int read_ok, int read_allowed);

/* caller_claims_absent is ignored. It cannot permit or refuse a creation. */
int fixture_syntax_creation(int directories_ok, int ciphertext_empty, int marker_absent, int key_state,
                            int caller_claims_absent);

/* created files stay. unlinked 0 is the only accepted post-error state. */
int fixture_syntax_marker_survives(int unlinked_after_error);

#endif
