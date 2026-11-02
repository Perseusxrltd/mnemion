#include "fixture_store_syntax.h"
#include "real_store_names.h"

#include <stdio.h>
#include <string.h>

/* Offline source contracts. This file is not a fixture run and is not executed
   by the real-store workflow. */

static int g_failed = 0;

static void expect(const char *name, int ok) {
    if (ok) {
        return;
    }
    fprintf(stderr, "contract=%s result=fail\n", name);
    g_failed = 1;
}

static int header_keeps_helper_pins_out(const char *caller_header) {
    if (caller_header == NULL) {
        return 0;
    }
    if (strstr(caller_header, "MNEMION_HELPER_CDHASH") != NULL || strstr(caller_header, "MNEMION_HELPER_MANIFEST") != NULL ||
        strstr(caller_header, "MNEMION_HELPER_DESIGNATED") != NULL) {
        return 0;
    }
    return strstr(caller_header, "MNEMION_PIN_CLASS \"fixture\"") != NULL;
}

static int receipt_rejects_injected_zero(const char *receipt) {
    if (receipt == NULL || strstr(receipt, "lane=real_store") == NULL) {
        return 0;
    }
    if (strstr(receipt, "native_operations=real") == NULL) {
        return 0;
    }
    if (strstr(receipt, "native_security_calls=0") != NULL) {
        return 0;
    }
    return 1;
}

static int lookup_accepted(int exit_code, const char *stdout_text, const char *stderr_text) {
    if (exit_code != 1 || stdout_text == NULL || stderr_text == NULL) {
        return 0;
    }
    if (strcmp(stdout_text, "result=missing_key\nkeychain_calls=1\n") != 0) {
        return 0;
    }
    if (strcmp(stderr_text, "direct_lookup=interaction_bracket\n") != 0) {
        return 0;
    }
    return 1;
}

static int manifest_source_ok(const char *source) {
    return source != NULL && strcmp(source, "bundle_manifest_digest") == 0;
}

static int measured_basename_admitted(const char *measured) {
    return measured != NULL && strcmp(measured, REAL_STORE_DATA_BASENAME) == 0 &&
           fixture_syntax_basename(measured) == FIXTURE_SYNTAX_OK;
}

int main(void) {
    const char *metadata = "fixture: owned private data store";
    const char *caller = "#define MNEMION_PIN_CLASS \"fixture\"\n#define MNEMION_PIN_METADATA \"fixture leaf\"\n";
    expect("fixed_data_basename",
           fixture_syntax_config("fixture", metadata, REAL_STORE_SERVICE_PREFIX, REAL_STORE_ACCOUNT_PREFIX,
                                 REAL_STORE_DATA_BASENAME, REAL_STORE_RECORD_BASENAME, "mnemion-studio Safe Storage",
                                 "mnemion-studio Key") == FIXTURE_SYNTAX_OK);
    expect("reject_keychain_db_alias",
           fixture_syntax_config("fixture", metadata, REAL_STORE_SERVICE_PREFIX, REAL_STORE_ACCOUNT_PREFIX,
                                 "throwaway.keychain-db", REAL_STORE_RECORD_BASENAME, "mnemion-studio Safe Storage",
                                 "mnemion-studio Key") != FIXTURE_SYNTAX_OK);
    expect("reject_login_basename",
           fixture_syntax_config("fixture", metadata, REAL_STORE_SERVICE_PREFIX, REAL_STORE_ACCOUNT_PREFIX,
                                 "login.keychain-db", REAL_STORE_RECORD_BASENAME, "mnemion-studio Safe Storage",
                                 "mnemion-studio Key") != FIXTURE_SYNTAX_OK);
    expect("reject_compile_only_class",
           fixture_syntax_config("compile_only", "compile_only placeholder", REAL_STORE_SERVICE_PREFIX,
                                 REAL_STORE_ACCOUNT_PREFIX, REAL_STORE_DATA_BASENAME, REAL_STORE_RECORD_BASENAME,
                                 "mnemion-studio Safe Storage", "mnemion-studio Key") != FIXTURE_SYNTAX_OK);
    expect("signing_name_not_login", strstr(REAL_STORE_SIGNING_BASENAME, "login.keychain") == NULL &&
                                         strcmp(REAL_STORE_SIGNING_BASENAME, "System.keychain") != 0);
    expect("caller_header_separation", header_keeps_helper_pins_out(caller));
    expect("caller_header_rejects_helper_pin",
           !header_keeps_helper_pins_out("#define MNEMION_PIN_CLASS \"fixture\"\n#define MNEMION_HELPER_CDHASH \"AA\"\n"));
    expect("receipt_real_lane", receipt_rejects_injected_zero("lane=real_store\nnative_operations=real\n"
                                                             "external_tool_security_calls=unavailable\n"));
    expect("receipt_rejects_zero_native",
           !receipt_rejects_injected_zero("lane=real_store\nnative_operations=real\nnative_security_calls=0\n"));
    expect("empty_lookup_exact", lookup_accepted(1, "result=missing_key\nkeychain_calls=1\n",
                                                 "direct_lookup=interaction_bracket\n"));
    expect("reject_unavailable", !lookup_accepted(1, "result=unavailable\nkeychain_calls=1\n",
                                                  "direct_lookup=interaction_bracket\n"));
    expect("reject_wrong_calls", !lookup_accepted(1, "result=missing_key\nkeychain_calls=0\n",
                                                  "direct_lookup=interaction_bracket\n"));
    expect("reject_wrong_exit", !lookup_accepted(2, "result=missing_key\nkeychain_calls=1\n",
                                                 "direct_lookup=interaction_bracket\n"));
    expect("reject_missing_bracket", !lookup_accepted(1, "result=missing_key\nkeychain_calls=1\n", ""));
    expect("manifest_not_zip", manifest_source_ok("bundle_manifest_digest") && !manifest_source_ok("zip"));
    expect("measured_alias_not_admitted", measured_basename_admitted(REAL_STORE_DATA_BASENAME) &&
                                             !measured_basename_admitted("throwaway.keychain-db"));
    expect("tmp_run_rejected", fixture_syntax_run_path("/tmp/owned-run") != FIXTURE_SYNTAX_OK);
    if (g_failed) {
        return 1;
    }
    printf("contract=real_store result=pass\n");
    return 0;
}
