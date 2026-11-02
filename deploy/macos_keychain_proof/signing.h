#ifndef MNEMION_KEYCHAIN_PROOF_SIGNING_H
#define MNEMION_KEYCHAIN_PROOF_SIGNING_H

#include <stddef.h>

/* Reads the on-disk signature. It does not sign, trust, or touch Keychain. */

int signing_describe(const char *path, char *cdhash, size_t cdhash_cap,
                     char *identifier, size_t identifier_cap,
                     char *designated, size_t designated_cap);

/* Leaf of the signed code, hashed as DER. Names and placeholder text are not
   certificate pins. hex buffers need 41 and 65 bytes. */
int signing_leaf_der(const char *path, char *sha1_hex, size_t sha1_cap, char *sha256_hex, size_t sha256_cap);

#endif
