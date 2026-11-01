#include "exact_helper.h"

#include "auth.h"
#include "caller_pin.h"
#include "parent_pin.h"
#include "protocol.h"

#include <stdio.h>
#include <string.h>

_Static_assert(sizeof(MNEMION_HELPER_CDHASH) == 41 || sizeof(MNEMION_HELPER_CDHASH) == 65, "helper cdhash pin length");
_Static_assert(sizeof(MNEMION_HELPER_MANIFEST_SHA256) == 65, "helper manifest pin length");
_Static_assert(sizeof(MNEMION_SEALED_HELPER_IDENTIFIER) == sizeof(MNEMION_HELPER_IDENTIFIER), "helper identifier pin length");
_Static_assert(sizeof(MNEMION_HELPER_DESIGNATED) > 1 && sizeof(MNEMION_HELPER_DESIGNATED) < 1024, "designated pin length");

int auth_exact_helper_pin_shape_ok(void) {
    size_t cdhash_len;
    if (auth_caller_pin_shape_ok() != 0) {
        return -1;
    }
    cdhash_len = strlen(MNEMION_HELPER_CDHASH);
    if (cdhash_len != 40 && cdhash_len != 64) {
        return -1;
    }
    if (auth_hex_pin(MNEMION_HELPER_CDHASH, cdhash_len, AUTH_HEX_UPPER) != 0 ||
        auth_hex_pin(MNEMION_HELPER_MANIFEST_SHA256, 64, AUTH_HEX_LOWER) != 0) {
        return -1;
    }
    if (strcmp(MNEMION_SEALED_HELPER_IDENTIFIER, MNEMION_HELPER_IDENTIFIER) != 0) {
        return -1;
    }
    if (MNEMION_HELPER_DESIGNATED[0] == '\0' || strlen(MNEMION_HELPER_DESIGNATED) >= 1024 ||
        strchr(MNEMION_HELPER_DESIGNATED, '\n') != NULL || strchr(MNEMION_HELPER_DESIGNATED, '\r') != NULL) {
        return -1;
    }
    return 0;
}

int auth_build_helper_requirement(char *buffer, size_t capacity) {
    char sha1[41];
    int written;
    if (buffer == NULL || capacity == 0 || auth_exact_helper_pin_shape_ok() != 0 ||
        auth_copy_upper_hex(MNEMION_FIXTURE_LEAF_SHA1, 40, sha1) != 0) {
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
