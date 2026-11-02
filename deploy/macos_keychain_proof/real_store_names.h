#ifndef MNEMION_REAL_STORE_NAMES_H
#define MNEMION_REAL_STORE_NAMES_H

#include "fixture_store_syntax.h"

/* Fixed private names. The data-store basename is the sealed guard's name.
   A measured alias is not admitted by rewriting that name. */

#define REAL_STORE_DATA_BASENAME FIXTURE_FIXED_STORE_BASENAME
#define REAL_STORE_RECORD_BASENAME FIXTURE_FIXED_RECORD_BASENAME
#define REAL_STORE_LOCK_BASENAME FIXTURE_FIXED_LOCK_NAME
#define REAL_STORE_CIPHERTEXT_BASENAME FIXTURE_FIXED_CIPHERTEXT_DIR
#define REAL_STORE_SIGNING_BASENAME "fixture-signing.keychain"
#define REAL_STORE_SERVICE_PREFIX FIXTURE_FIXED_SERVICE_PREFIX
#define REAL_STORE_ACCOUNT_PREFIX FIXTURE_FIXED_ACCOUNT_PREFIX

#define REAL_STORE_STAGE "signed_artifact_and_empty_lookup"
#define REAL_STORE_SIGNING_CLASS "fixture"

#define REAL_STAGE_MS 300000L
#define REAL_CHILD_MS 45000L
#define REAL_CLEANUP_GRACE_MS 10000L
#define REAL_STALL_NORMAL_MS 400L
#define REAL_STALL_GRACE_MS 200L
#define REAL_HYGIENE_MS 100L
#define REAL_RECORD_BOUND 32
#define REAL_SUCCESS_COMMANDS 23
#define REAL_SPAWN_CAP 24

_Static_assert(sizeof(REAL_STORE_DATA_BASENAME) == sizeof("throwaway.keychain"), "data store basename drifted");
_Static_assert(sizeof(REAL_STORE_SIGNING_BASENAME) == sizeof("fixture-signing.keychain"), "signing store basename drifted");

#endif
