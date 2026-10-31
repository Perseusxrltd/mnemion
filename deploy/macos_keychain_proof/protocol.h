#ifndef MNEMION_KEYCHAIN_PROOF_PROTOCOL_H
#define MNEMION_KEYCHAIN_PROOF_PROTOCOL_H

/* Disposable proof surface. Not the production CredentialProcess switch.
   Workspace ciphertext stays outside Keychain. The Keychain item is only the
   existing Safe Storage secret Chromium already uses. */

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define MNEMION_PARENT_IDENTIFIER "com.perseusxr.mnemion-studio"
#define MNEMION_HELPER_IDENTIFIER "com.perseusxr.mnemion-studio.credential-helper"
#define MNEMION_WRONG_IDENTIFIER "com.perseusxr.mnemion-studio.not-the-app"
#define MNEMION_HELPER_SERVICE "com.perseusxr.mnemion-studio.credential-helper"

/* Reporter item, docs/validation/2026-10-29-macos-keychain.md. A helper
   bundle rename must not change these lookup strings. */
#define MNEMION_KEYCHAIN_SERVICE "mnemion-studio Safe Storage"
#define MNEMION_KEYCHAIN_ACCOUNT "mnemion-studio Key"

/* credential-process.ts MAX_VALUE and workspace-cipher.ts both cap stored
   ciphertext at 16,384 bytes. Seal rejects framed v10 output above that,
   including the PKCS#7 boundary past 16,367 plaintext bytes. */
#define MNEMION_MAX_VALUE 16384
#define MNEMION_MAX_CIPHERTEXT 16384
#define MNEMION_CHECK_TIMEOUT_MS 2000
#define MNEMION_OPERATION_TIMEOUT_MS 15000
/* Inside the parent waits, so a blocked lookup ends on the helper as well. */
#define MNEMION_HELPER_CHECK_DEADLINE_MS 1500
#define MNEMION_HELPER_OPERATION_DEADLINE_MS 12000
#define MNEMION_HELPER_IDLE_SECONDS 30

#define MNEMION_HELPER_VERSION "1"
#define MNEMION_HELPER_EPOCH_NAME "IdentityEpoch"

static inline void mnemion_zero(void *pointer, size_t size) {
    volatile unsigned char *bytes;
    size_t index;
    if (pointer == NULL || size == 0) {
        return;
    }
    /* explicit_bzero is undeclared for this deployment target. Apple's
       memset_s is only declared when Annex K is requested before string.h.
       Volatile stores stay in the object code, so the secret is cleared. */
    bytes = pointer;
    for (index = 0; index < size; index++) {
        bytes[index] = 0;
    }
}

#endif
