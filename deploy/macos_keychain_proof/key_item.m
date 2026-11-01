#include "key_item.h"

#include "fixture_store.h"
#include "protocol.h"
#include "v10_crypt.h"

#include <CoreFoundation/CoreFoundation.h>
#include <Security/Security.h>

#include <stddef.h>
#include <stdint.h>
#include <string.h>

void key_state_init(struct key_state *state) {
    memset(state->derived, 0, sizeof state->derived);
    state->derived_valid = 0;
    atomic_init(&state->keychain_calls, 0);
}

void key_state_zero(struct key_state *state) {
    if (state == NULL) {
        return;
    }
    mnemion_zero(state->derived, sizeof state->derived);
    state->derived_valid = 0;
}

static enum key_result map_status(OSStatus status) {
    if (status == errSecItemNotFound) {
        return KEY_ABSENT;
    }
    if (status == errSecUserCanceled || status == errSecAuthFailed) {
        return KEY_DENIED;
    }
    if (status == errSecInteractionNotAllowed || status == errSecNotAvailable) {
        return KEY_LOCKED;
    }
    return KEY_UNAVAILABLE;
}

static enum key_result accept_password(struct key_state *state, CFDataRef data) {
    const uint8_t *bytes;
    CFIndex length;
    uint8_t derived[16];
    if (data == NULL) {
        return KEY_UNAVAILABLE;
    }
    bytes = CFDataGetBytePtr(data);
    length = CFDataGetLength(data);
    if (bytes == NULL || length <= 0) {
        return KEY_UNAVAILABLE;
    }
    if (v10_derive_key(bytes, (size_t)length, derived) != 0) {
        mnemion_zero(derived, sizeof derived);
        return KEY_UNAVAILABLE;
    }
    memcpy(state->derived, derived, sizeof derived);
    state->derived_valid = 1;
    mnemion_zero(derived, sizeof derived);
    return KEY_OK;
}

enum key_result key_item_load(struct key_state *state) {
    CFDataRef found = NULL;
    OSStatus status = errSecParam;
    int invoked = 0;
    enum key_result result;
    if (state == NULL) {
        return KEY_UNAVAILABLE;
    }
    if (fixture_store_copy_matching(&found, &status, &invoked) != 0) {
        if (invoked > 0) {
            atomic_fetch_add_explicit(&state->keychain_calls, (uint_fast64_t)invoked, memory_order_relaxed);
        }
        if (found != NULL) {
            CFRelease(found);
        }
        return KEY_UNAVAILABLE;
    }
    if (invoked > 0) {
        atomic_fetch_add_explicit(&state->keychain_calls, (uint_fast64_t)invoked, memory_order_relaxed);
    }
    if (status != errSecSuccess) {
        if (found != NULL) {
            CFRelease(found);
        }
        return map_status(status);
    }
    result = accept_password(state, found);
    CFRelease(found);
    return result;
}

static void base64_16(const uint8_t raw[16], char out[25]) {
    static const char alphabet[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    size_t index = 0;
    size_t cursor = 0;
    while (index < 16) {
        unsigned value = (unsigned)raw[index++] << 16;
        int remaining = 2;
        if (index < 16) {
            value |= (unsigned)raw[index++] << 8;
            remaining = 1;
        }
        if (index < 16) {
            value |= raw[index++];
            remaining = 0;
        }
        out[cursor++] = alphabet[(value >> 18) & 63];
        out[cursor++] = alphabet[(value >> 12) & 63];
        out[cursor++] = remaining == 2 ? '=' : alphabet[(value >> 6) & 63];
        out[cursor++] = remaining != 0 ? '=' : alphabet[value & 63];
    }
    out[24] = '\0';
}

enum key_result key_item_create_empty(struct key_state *state, int caller_claims_absent) {
    uint8_t raw[16];
    char password[25];
    OSStatus status = errSecParam;
    int invoked = 0;
    enum key_result loaded;
    if (state == NULL) {
        return KEY_UNAVAILABLE;
    }
    if (SecRandomCopyBytes(kSecRandomDefault, sizeof raw, raw) != errSecSuccess) {
        mnemion_zero(raw, sizeof raw);
        return KEY_UNAVAILABLE;
    }
    base64_16(raw, password);
    mnemion_zero(raw, sizeof raw);
    if (fixture_store_add_new((const uint8_t *)password, 24, caller_claims_absent, &status, &invoked) != 0) {
        mnemion_zero(password, sizeof password);
        if (invoked > 0) {
            atomic_fetch_add_explicit(&state->keychain_calls, (uint_fast64_t)invoked, memory_order_relaxed);
        }
        return KEY_UNAVAILABLE;
    }
    if (invoked > 0) {
        atomic_fetch_add_explicit(&state->keychain_calls, (uint_fast64_t)invoked, memory_order_relaxed);
    }
    mnemion_zero(password, sizeof password);
    if (status == errSecDuplicateItem) {
        /* The explicit store already has the item. Read it. Never replace it. */
        return key_item_load(state);
    }
    if (status != errSecSuccess) {
        return map_status(status);
    }
    loaded = key_item_load(state);
    return loaded;
}
