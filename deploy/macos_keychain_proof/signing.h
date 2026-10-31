#ifndef MNEMION_KEYCHAIN_PROOF_SIGNING_H
#define MNEMION_KEYCHAIN_PROOF_SIGNING_H

#include <stddef.h>

/* Reads the on-disk signature. It does not sign, trust, or touch Keychain. */

int signing_describe(const char *path, char *cdhash, size_t cdhash_cap,
                     char *identifier, size_t identifier_cap,
                     char *designated, size_t designated_cap);

#endif
