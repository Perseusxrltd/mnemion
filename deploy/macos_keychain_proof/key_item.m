#include "key_item.h"

#include "protocol.h"
#include "v10_crypt.h"

#include <CoreFoundation/CoreFoundation.h>
#include <Security/Security.h>

#include <stddef.h>
#include <stdint.h>
#include <string.h>

static CFStringRef service_name(void) {
    return CFStringCreateWithCString(NULL, MNEMION_KEYCHAIN_SERVICE, kCFStringEncodingUTF8);
}

static CFStringRef account_name(void) {
    return CFStringCreateWithCString(NULL, MNEMION_KEYCHAIN_ACCOUNT, kCFStringEncodingUTF8);
}

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

enum key_result key_item_load(struct key_state *state, int allow_prompt) {
    CFStringRef service;
    CFStringRef account;
    CFMutableDictionaryRef query;
    CFTypeRef found = NULL;
    OSStatus status;
    enum key_result result;
    service = service_name();
    account = account_name();
    query = CFDictionaryCreateMutable(NULL, 0, &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    if (service == NULL || account == NULL || query == NULL) {
        if (service != NULL) CFRelease(service);
        if (account != NULL) CFRelease(account);
        if (query != NULL) CFRelease(query);
        return KEY_UNAVAILABLE;
    }
    CFDictionarySetValue(query, kSecClass, kSecClassGenericPassword);
    CFDictionarySetValue(query, kSecAttrService, service);
    CFDictionarySetValue(query, kSecAttrAccount, account);
    CFDictionarySetValue(query, kSecReturnData, kCFBooleanTrue);
    CFDictionarySetValue(query, kSecMatchLimit, kSecMatchLimitOne);
    if (!allow_prompt) {
        /* Availability must not raise a prompt. Seal and open still can. */
        CFDictionarySetValue(query, kSecUseAuthenticationUI, kSecUseAuthenticationUIFail);
    }
    atomic_fetch_add_explicit(&state->keychain_calls, 1, memory_order_relaxed);
    status = SecItemCopyMatching(query, &found);
    CFRelease(query);
    CFRelease(service);
    CFRelease(account);
    if (status != errSecSuccess) {
        if (found != NULL) {
            CFRelease(found);
        }
        return map_status(status);
    }
    result = accept_password(state, (CFDataRef)found);
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

enum key_result key_item_create_empty(struct key_state *state) {
    uint8_t raw[16];
    char password[25];
    CFStringRef service;
    CFStringRef account;
    CFDataRef secret = NULL;
    CFMutableDictionaryRef query;
    OSStatus status;
    enum key_result loaded;
    if (SecRandomCopyBytes(kSecRandomDefault, sizeof raw, raw) != errSecSuccess) {
        mnemion_zero(raw, sizeof raw);
        return KEY_UNAVAILABLE;
    }
    base64_16(raw, password);
    mnemion_zero(raw, sizeof raw);
    service = service_name();
    account = account_name();
    secret = CFDataCreate(NULL, (const UInt8 *)password, 24);
    query = CFDictionaryCreateMutable(NULL, 0, &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    if (service == NULL || account == NULL || secret == NULL || query == NULL) {
        mnemion_zero(password, sizeof password);
        if (service != NULL) CFRelease(service);
        if (account != NULL) CFRelease(account);
        if (secret != NULL) CFRelease(secret);
        if (query != NULL) CFRelease(query);
        return KEY_UNAVAILABLE;
    }
    CFDictionarySetValue(query, kSecClass, kSecClassGenericPassword);
    CFDictionarySetValue(query, kSecAttrService, service);
    CFDictionarySetValue(query, kSecAttrAccount, account);
    CFDictionarySetValue(query, kSecValueData, secret);
    CFDictionarySetValue(query, kSecAttrAccessible, kSecAttrAccessibleWhenUnlocked);
    atomic_fetch_add_explicit(&state->keychain_calls, 1, memory_order_relaxed);
    status = SecItemAdd(query, NULL);
    CFRelease(query);
    CFRelease(secret);
    CFRelease(service);
    CFRelease(account);
    mnemion_zero(password, sizeof password);
    if (status == errSecDuplicateItem) {
        /* Somebody else created it. Read it. Never replace it. */
        return key_item_load(state, 1);
    }
    if (status != errSecSuccess) {
        return map_status(status);
    }
    loaded = key_item_load(state, 1);
    return loaded;
}
