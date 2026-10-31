#ifndef MNEMION_V10_CRYPT_H
#define MNEMION_V10_CRYPT_H

#include "protocol.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* Chromium 152 KeychainKeyProvider + Encryptor AES-128-CBC framing.
   No empty-key fallback. The caller supplies the Keychain password bytes.
   Stored ciphertext is capped at MNEMION_MAX_CIPHERTEXT (16,384). PKCS#7
   adds 1..16 bytes and the v10 tag adds 3, so the largest plaintext that
   still fits is 16,367 bytes (16,367 + 1 + 3 = 16,371). 16,368 plaintext
   bytes pad to a full extra block and frame to 16,387, which is rejected
   before any Keychain call. */

static inline int v10_seal_bounds(size_t plaintext_len) {
    size_t pad;
    size_t framed;
    if (plaintext_len == 0 || plaintext_len > MNEMION_MAX_VALUE) {
        return -1;
    }
    pad = 16 - (plaintext_len % 16);
    framed = 3 + plaintext_len + pad;
    if (framed > MNEMION_MAX_CIPHERTEXT) {
        return -1;
    }
    return 0;
}

static inline int v10_ciphertext_bounds(const uint8_t *ciphertext, size_t ciphertext_len) {
    size_t body;
    if (ciphertext == NULL || ciphertext_len < 19 || ciphertext_len > MNEMION_MAX_CIPHERTEXT) {
        return -1;
    }
    if (ciphertext[0] != 'v' || ciphertext[1] != '1' || ciphertext[2] != '0') {
        return -1;
    }
    body = ciphertext_len - 3;
    if ((body % 16) != 0) {
        return -1;
    }
    return 0;
}

int v10_derive_key(const uint8_t *password, size_t password_len, uint8_t key[16]);

int v10_seal(const uint8_t key[16], const uint8_t *plaintext, size_t plaintext_len,
             uint8_t *ciphertext, size_t ciphertext_cap, size_t *ciphertext_len);

int v10_open(const uint8_t key[16], const uint8_t *ciphertext, size_t ciphertext_len,
             uint8_t *plaintext, size_t plaintext_cap, size_t *plaintext_len);

int v10_utf8(const uint8_t *bytes, size_t length);

#endif
