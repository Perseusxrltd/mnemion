#ifndef MNEMION_FIXTURE_STORE_H
#define MNEMION_FIXTURE_STORE_H

#include <CoreFoundation/CoreFoundation.h>
#include <Security/Security.h>

#include <stddef.h>
#include <stdint.h>

/* Shared disposable-store guard for helper and parent data operations.
   Lookup uses SecItemCopyMatching with one explicit store in
   kSecMatchSearchList. Add uses that same store as kSecUseKeychain.
   Service names are the fixed synthetic prefix plus the sealed nonce.
   They are not ProtectedCloudStorage, so that exceptional default-store
   append does not apply. The result's store is checked again as defense.
   File-Keychain calls run inside a process-local interaction bracket.
   LAContext is not the control for this route. */

int fixture_store_runtime_allowed(void);

/* key_state 0 absent, 1 present, any other value unknown.
   Returns 1 only for the one-time creation decision.
   caller_claims_absent is ignored. */
int fixture_store_create_permitted(int directories_ok, int ciphertext_empty, int marker_absent, int key_state,
                                   int caller_claims_absent);

/* Binds MNEMION_FIXTURE_RUN_DIRECTORY from the sealed header. No caller path. */
int fixture_store_bind(void);

/* 0 when path is exactly the sealed run directory. */
int fixture_store_argument_matches_seal(const char *path);

int fixture_store_copy_matching(CFDataRef *data_out, OSStatus *status_out, int *invoked);

/* caller_claims_absent is ignored. The pre-add transaction is the guard. */
int fixture_store_add_new(const uint8_t *secret, size_t secret_len, int caller_claims_absent, OSStatus *status_out,
                          int *invoked);

/* Writes one new file under the sealed ciphertext directory while holding
   the fixture lock. Does not remove an existing file. */
int fixture_store_publish_ciphertext(const uint8_t *bytes, size_t length);

#endif
