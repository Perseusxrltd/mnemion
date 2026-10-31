#include "auth.h"

#include "parent_pin.h"
#include "protocol.h"

#include <CoreFoundation/CoreFoundation.h>
#include <Security/Security.h>

#include <ctype.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
#include <unistd.h>

_Static_assert(sizeof(MNEMION_FIXTURE_LEAF_SHA1) == 41, "leaf sha1 pin length");
_Static_assert(sizeof(MNEMION_FIXTURE_LEAF_SHA256) == 65, "leaf sha256 pin length");
_Static_assert(sizeof(MNEMION_HELPER_CDHASH) == 41 || sizeof(MNEMION_HELPER_CDHASH) == 65, "helper cdhash pin length");
_Static_assert(sizeof(MNEMION_HELPER_MANIFEST_SHA256) == 65, "helper manifest pin length");
_Static_assert(sizeof(MNEMION_SEALED_HELPER_IDENTIFIER) == sizeof(MNEMION_HELPER_IDENTIFIER), "helper identifier pin length");
_Static_assert(sizeof(MNEMION_HELPER_DESIGNATED) > 1 && sizeof(MNEMION_HELPER_DESIGNATED) < 1024, "designated pin length");
_Static_assert(sizeof(MNEMION_PIN_CLASS) == sizeof("compile_only") || sizeof(MNEMION_PIN_CLASS) == sizeof("fixture"), "pin class length");

enum { HEX_ANY = 0, HEX_UPPER = 1, HEX_LOWER = 2 };

static int hex_pin(const char *pin, size_t expect, int letter_case) {
    size_t index;
    if (pin == NULL || strlen(pin) != expect) {
        return -1;
    }
    for (index = 0; index < expect; index++) {
        unsigned char character = (unsigned char)pin[index];
        if (!isxdigit(character)) {
            return -1;
        }
        if (letter_case == HEX_UPPER && character >= 'a' && character <= 'f') {
            return -1;
        }
        if (letter_case == HEX_LOWER && character >= 'A' && character <= 'F') {
            return -1;
        }
    }
    return 0;
}

static int copy_upper_hex(const char *pin, size_t expect, char *out) {
    size_t index;
    if (hex_pin(pin, expect, HEX_ANY) != 0) {
        return -1;
    }
    for (index = 0; index < expect; index++) {
        unsigned char character = (unsigned char)pin[index];
        if (character >= 'a' && character <= 'f') {
            character = (unsigned char)(character - 'a' + 'A');
        }
        out[index] = (char)character;
    }
    out[expect] = '\0';
    return 0;
}

int auth_pin_shape_ok(void) {
    size_t cdhash_len;
    if (strcmp(MNEMION_PIN_CLASS, "compile_only") == 0) {
        if (strstr(MNEMION_PIN_METADATA, "compile_only") == NULL) {
            return -1;
        }
    } else if (strcmp(MNEMION_PIN_CLASS, "fixture") == 0) {
        if (strstr(MNEMION_PIN_METADATA, "compile_only") != NULL) {
            return -1;
        }
    } else {
        return -1;
    }
    /* Text shape only. Certificate DER comparison belongs to the later recipe. */
    if (hex_pin(MNEMION_FIXTURE_LEAF_SHA1, 40, HEX_ANY) != 0 ||
        hex_pin(MNEMION_FIXTURE_LEAF_SHA256, 64, HEX_ANY) != 0) {
        return -1;
    }
    cdhash_len = strlen(MNEMION_HELPER_CDHASH);
    if (cdhash_len != 40 && cdhash_len != 64) {
        return -1;
    }
    if (hex_pin(MNEMION_HELPER_CDHASH, cdhash_len, HEX_UPPER) != 0 ||
        hex_pin(MNEMION_HELPER_MANIFEST_SHA256, 64, HEX_LOWER) != 0) {
        return -1;
    }
    if (strcmp(MNEMION_SEALED_HELPER_IDENTIFIER, MNEMION_HELPER_IDENTIFIER) != 0) {
        return -1;
    }
    if (MNEMION_HELPER_DESIGNATED[0] == '\0' ||
        strlen(MNEMION_HELPER_DESIGNATED) >= 1024 ||
        strchr(MNEMION_HELPER_DESIGNATED, '\n') != NULL ||
        strchr(MNEMION_HELPER_DESIGNATED, '\r') != NULL) {
        return -1;
    }
    return 0;
}

int auth_pins_compile_only(void) {
    return strcmp(MNEMION_PIN_CLASS, "compile_only") == 0;
}

static int build_parent_requirement(char *buffer, size_t capacity) {
    char sha1[41];
    int written;
    if (auth_pin_shape_ok() != 0 || copy_upper_hex(MNEMION_FIXTURE_LEAF_SHA1, 40, sha1) != 0) {
        return -1;
    }
    written = snprintf(buffer, capacity,
                       "identifier \"%s\" and certificate leaf = H\"%s\"",
                       MNEMION_PARENT_IDENTIFIER, sha1);
    if (written < 0 || (size_t)written >= capacity) {
        return -1;
    }
    return 0;
}

int auth_build_parent_requirement(char *buffer, size_t capacity) {
    if (buffer == NULL || capacity == 0) {
        return -1;
    }
    return build_parent_requirement(buffer, capacity);
}

int auth_build_helper_requirement(char *buffer, size_t capacity) {
    char sha1[41];
    int written;
    if (buffer == NULL || capacity == 0 || auth_pin_shape_ok() != 0 ||
        copy_upper_hex(MNEMION_FIXTURE_LEAF_SHA1, 40, sha1) != 0) {
        return -1;
    }
    /* TN3127: cdhash H"<hex>" matches one frozen helper, not merely its signer. */
    written = snprintf(buffer, capacity,
                       "identifier \"%s\" and certificate leaf = H\"%s\" and cdhash H\"%s\"",
                       MNEMION_HELPER_IDENTIFIER, sha1, MNEMION_HELPER_CDHASH);
    if (written < 0 || (size_t)written >= capacity) {
        return -1;
    }
    return 0;
}

static int euid_matches(xpc_connection_t peer) {
    uid_t caller;
    if (peer == NULL) {
        return -1;
    }
    caller = xpc_connection_get_euid(peer);
    if (caller != geteuid()) {
        return -1;
    }
    return 0;
}

static int check_code(SecCodeRef code, const char *requirement) {
    SecRequirementRef parsed = NULL;
    CFStringRef text;
    OSStatus status;
    if (code == NULL || requirement == NULL) {
        return -1;
    }
    text = CFStringCreateWithCString(NULL, requirement, kCFStringEncodingUTF8);
    if (text == NULL) {
        return -1;
    }
    status = SecRequirementCreateWithString(text, kSecCSDefaultFlags, &parsed);
    CFRelease(text);
    if (status != errSecSuccess) {
        return -1;
    }
    status = SecCodeCheckValidity(code, kSecCSDefaultFlags, parsed);
    CFRelease(parsed);
    return status == errSecSuccess ? 0 : -1;
}

int auth_check_xpc_sender(xpc_object_t message, xpc_connection_t peer, const char *requirement) {
    SecCodeRef code = NULL;
    OSStatus status;
    int result;
    if (message == NULL || xpc_get_type(message) != XPC_TYPE_DICTIONARY) {
        return -1;
    }
    if (euid_matches(peer) != 0) {
        return -1;
    }
    status = SecCodeCreateWithXPCMessage(message, kSecCSDefaultFlags, &code);
    if (status != errSecSuccess) {
        return -1;
    }
    result = check_code(code, requirement);
    CFRelease(code);
    return result;
}

int auth_check_bundle(const char *path, const char *requirement) {
    CFURLRef url;
    SecStaticCodeRef code = NULL;
    SecRequirementRef parsed = NULL;
    CFStringRef text;
    OSStatus status;
    int result = -1;
    if (path == NULL || requirement == NULL) {
        return -1;
    }
    url = CFURLCreateFromFileSystemRepresentation(NULL, (const UInt8 *)path, (CFIndex)strlen(path), true);
    if (url == NULL) {
        return -1;
    }
    status = SecStaticCodeCreateWithPath(url, kSecCSDefaultFlags, &code);
    CFRelease(url);
    if (status != errSecSuccess) {
        return -1;
    }
    text = CFStringCreateWithCString(NULL, requirement, kCFStringEncodingUTF8);
    if (text == NULL) {
        CFRelease(code);
        return -1;
    }
    status = SecRequirementCreateWithString(text, kSecCSDefaultFlags, &parsed);
    CFRelease(text);
    if (status != errSecSuccess) {
        CFRelease(code);
        return -1;
    }
    /* On-disk bundle, before the helper is a reply sender. Dynamic validity
       still does not cover every resource; the parent seals the manifest pin. */
    status = SecStaticCodeCheckValidity(code, kSecCSDefaultFlags, parsed);
    result = status == errSecSuccess ? 0 : -1;
    CFRelease(parsed);
    CFRelease(code);
    return result;
}
