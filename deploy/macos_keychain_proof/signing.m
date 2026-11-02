#include "signing.h"

#include <CommonCrypto/CommonDigest.h>
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

static void digest_hex(const unsigned char *digest, size_t count, char *out) {
    static const char digits[] = "0123456789abcdef";
    size_t index;
    for (index = 0; index < count; index++) {
        out[index * 2] = digits[digest[index] >> 4];
        out[index * 2 + 1] = digits[digest[index] & 15];
    }
    out[count * 2] = '\0';
}

int signing_leaf_der(const char *path, char *sha1_hex, size_t sha1_cap, char *sha256_hex, size_t sha256_cap) {
    CFURLRef url;
    SecStaticCodeRef code = NULL;
    CFDictionaryRef info = NULL;
    CFArrayRef certs;
    SecCertificateRef leaf;
    CFDataRef der = NULL;
    unsigned char sha1[CC_SHA1_DIGEST_LENGTH];
    unsigned char sha256[CC_SHA256_DIGEST_LENGTH];
    OSStatus status;
    const UInt8 *bytes;
    CFIndex length;
    if (path == NULL || sha1_hex == NULL || sha256_hex == NULL || sha1_cap < CC_SHA1_DIGEST_LENGTH * 2 + 1 ||
        sha256_cap < CC_SHA256_DIGEST_LENGTH * 2 + 1) {
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
    CFRelease(code);
    if (status != errSecSuccess) {
        return -1;
    }
    certs = CFDictionaryGetValue(info, kSecCodeInfoCertificates);
    if (certs == NULL || CFGetTypeID(certs) != CFArrayGetTypeID() || CFArrayGetCount(certs) < 1) {
        CFRelease(info);
        return -1;
    }
    leaf = (SecCertificateRef)CFArrayGetValueAtIndex(certs, 0);
    if (leaf == NULL || CFGetTypeID(leaf) != SecCertificateGetTypeID()) {
        CFRelease(info);
        return -1;
    }
    der = SecCertificateCopyData(leaf);
    CFRelease(info);
    if (der == NULL) {
        return -1;
    }
    bytes = CFDataGetBytePtr(der);
    length = CFDataGetLength(der);
    if (bytes == NULL || length <= 0) {
        CFRelease(der);
        return -1;
    }
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    CC_SHA1(bytes, (CC_LONG)length, sha1);
#pragma clang diagnostic pop
    CC_SHA256(bytes, (CC_LONG)length, sha256);
    CFRelease(der);
    digest_hex(sha1, sizeof sha1, sha1_hex);
    digest_hex(sha256, sizeof sha256, sha256_hex);
    return 0;
}
