#include "signing.h"

#include <CoreFoundation/CoreFoundation.h>
#include <Security/Security.h>

#include <stddef.h>
#include <stdio.h>
#include <string.h>

static int copy_string(CFStringRef value, char *buffer, size_t capacity) {
    if (value == NULL || buffer == NULL || capacity == 0) {
        return -1;
    }
    if (!CFStringGetCString(value, buffer, (CFIndex)capacity, kCFStringEncodingUTF8)) {
        return -1;
    }
    if (strchr(buffer, '\n') != NULL || strchr(buffer, '\r') != NULL) {
        return -1;
    }
    return 0;
}

int signing_describe(const char *path, char *cdhash, size_t cdhash_cap,
                     char *identifier, size_t identifier_cap,
                     char *designated, size_t designated_cap) {
    CFURLRef url;
    SecStaticCodeRef code = NULL;
    CFDictionaryRef info = NULL;
    SecRequirementRef requirement = NULL;
    CFStringRef requirement_text = NULL;
    CFDataRef unique;
    CFStringRef ident;
    OSStatus status;
    const UInt8 *bytes;
    CFIndex length;
    CFIndex index;
    if (path == NULL) {
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
    status = SecCodeCopySigningInformation(code, kSecCSSigningInformation, &info);
    if (status != errSecSuccess) {
        CFRelease(code);
        return -1;
    }
    unique = CFDictionaryGetValue(info, kSecCodeInfoUnique);
    ident = CFDictionaryGetValue(info, kSecCodeInfoIdentifier);
    if (unique == NULL || ident == NULL || cdhash_cap < 3) {
        CFRelease(info);
        CFRelease(code);
        return -1;
    }
    bytes = CFDataGetBytePtr(unique);
    length = CFDataGetLength(unique);
    if (bytes == NULL || length <= 0 || (size_t)length * 2 + 1 > cdhash_cap) {
        CFRelease(info);
        CFRelease(code);
        return -1;
    }
    for (index = 0; index < length; index++) {
        snprintf(cdhash + (size_t)index * 2, 3, "%02X", bytes[index]);
    }
    cdhash[length * 2] = '\0';
    if (copy_string(ident, identifier, identifier_cap) != 0) {
        CFRelease(info);
        CFRelease(code);
        return -1;
    }
    status = SecCodeCopyDesignatedRequirement(code, kSecCSDefaultFlags, &requirement);
    CFRelease(info);
    CFRelease(code);
    if (status != errSecSuccess) {
        return -1;
    }
    status = SecRequirementCopyString(requirement, kSecCSDefaultFlags, &requirement_text);
    CFRelease(requirement);
    if (status != errSecSuccess || copy_string(requirement_text, designated, designated_cap) != 0) {
        if (requirement_text != NULL) {
            CFRelease(requirement_text);
        }
        return -1;
    }
    CFRelease(requirement_text);
    return 0;
}
