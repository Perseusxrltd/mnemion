#include "v10_crypt.h"

#include <CommonCrypto/CommonCryptor.h>
#include <CommonCrypto/CommonKeyDerivation.h>

#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* KeychainKeyProvider: salt "saltysalt", PBKDF2-HMAC-SHA1, 1003 rounds, 16-byte key.
   Encryptor AES-128-CBC uses a 16-space IV and prepends the provider tag "v10".
   Chromium's empty-password fallback key is intentionally absent. */

static const uint8_t k_salt[] = {'s', 'a', 'l', 't', 'y', 's', 'a', 'l', 't'};
static const uint8_t k_iv[16] = {
    ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ',
    ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ',
};
static const uint8_t k_tag[] = {'v', '1', '0'};

int v10_utf8(const uint8_t *bytes, size_t length) {
    size_t index = 0;
    if (bytes == NULL && length > 0) {
        return -1;
    }
    while (index < length) {
        uint8_t lead = bytes[index];
        size_t need = 0;
        size_t next;
        if (lead <= 0x7F) {
            index++;
            continue;
        } else if (lead >= 0xC2 && lead <= 0xDF) {
            need = 2;
        } else if (lead == 0xE0) {
            need = 3;
        } else if ((lead >= 0xE1 && lead <= 0xEC) || lead == 0xEE || lead == 0xEF) {
            need = 3;
        } else if (lead == 0xED) {
            need = 3;
        } else if (lead == 0xF0) {
            need = 4;
        } else if (lead >= 0xF1 && lead <= 0xF3) {
            need = 4;
        } else if (lead == 0xF4) {
            need = 4;
        } else {
            return -1;
        }
        if (length - index < need) {
            return -1;
        }
        for (next = 1; next < need; next++) {
            if ((bytes[index + next] & 0xC0) != 0x80) {
                return -1;
            }
        }
        if (lead == 0xE0 && bytes[index + 1] < 0xA0) {
            return -1;
        }
        if (lead == 0xED && bytes[index + 1] > 0x9F) {
            return -1;
        }
        if (lead == 0xF0 && bytes[index + 1] < 0x90) {
            return -1;
        }
        if (lead == 0xF4 && bytes[index + 1] > 0x8F) {
            return -1;
        }
        index += need;
    }
    return 0;
}

int v10_derive_key(const uint8_t *password, size_t password_len, uint8_t key[16]) {
    int status;
    if (password == NULL || password_len == 0 || key == NULL) {
        return -1;
    }
    status = CCKeyDerivationPBKDF(kCCPBKDF2, (const char *)password, password_len,
                                  k_salt, sizeof k_salt, kCCPRFHmacAlgSHA1,
                                  1003, key, 16);
    if (status != kCCSuccess) {
        mnemion_zero(key, 16);
        return -1;
    }
    return 0;
}

int v10_seal(const uint8_t key[16], const uint8_t *plaintext, size_t plaintext_len,
             uint8_t *ciphertext, size_t ciphertext_cap, size_t *ciphertext_len) {
    size_t moved = 0;
    size_t pad;
    CCCryptorStatus status;
    if (key == NULL || plaintext == NULL || ciphertext == NULL || ciphertext_len == NULL) {
        return -1;
    }
    if (v10_seal_bounds(plaintext_len) != 0 || v10_utf8(plaintext, plaintext_len) != 0) {
        return -1;
    }
    pad = 16 - (plaintext_len % 16);
    if (ciphertext_cap < 3 + plaintext_len + pad) {
        return -1;
    }
    status = CCCrypt(kCCEncrypt, kCCAlgorithmAES, kCCOptionPKCS7Padding,
                     key, kCCKeySizeAES128, k_iv,
                     plaintext, plaintext_len,
                     ciphertext + sizeof k_tag, ciphertext_cap - sizeof k_tag, &moved);
    if (status != kCCSuccess || moved != plaintext_len + pad || (moved % 16) != 0 ||
        sizeof k_tag + moved > ciphertext_cap || sizeof k_tag + moved > MNEMION_MAX_CIPHERTEXT) {
        mnemion_zero(ciphertext, ciphertext_cap);
        return -1;
    }
    memcpy(ciphertext, k_tag, sizeof k_tag);
    *ciphertext_len = sizeof k_tag + moved;
    return 0;
}

int v10_open(const uint8_t key[16], const uint8_t *ciphertext, size_t ciphertext_len,
             uint8_t *plaintext, size_t plaintext_cap, size_t *plaintext_len) {
    size_t body;
    size_t moved = 0;
    CCCryptorStatus status;
    if (key == NULL || ciphertext == NULL || plaintext == NULL || plaintext_len == NULL) {
        return -1;
    }
    if (v10_ciphertext_bounds(ciphertext, ciphertext_len) != 0) {
        return -1;
    }
    body = ciphertext_len - sizeof k_tag;
    if (plaintext_cap < body || body > MNEMION_MAX_CIPHERTEXT) {
        return -1;
    }
    status = CCCrypt(kCCDecrypt, kCCAlgorithmAES, kCCOptionPKCS7Padding,
                     key, kCCKeySizeAES128, k_iv,
                     ciphertext + sizeof k_tag, body,
                     plaintext, plaintext_cap, &moved);
    if (status != kCCSuccess || moved == 0 || moved > MNEMION_MAX_VALUE || v10_utf8(plaintext, moved) != 0) {
        mnemion_zero(plaintext, plaintext_cap);
        return -1;
    }
    *plaintext_len = moved;
    return 0;
}
