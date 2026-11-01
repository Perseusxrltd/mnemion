#include "parent_direct_lookup.h"

#include "fixture_store.h"

#include <CoreFoundation/CoreFoundation.h>

#include <stdio.h>
#include <string.h>

/* Proof fixture only. Binds the sealed run, not a caller-selected store.
   This command is not a product feature and not native acceptance. */
int parent_direct_lookup(void) {
    CFDataRef found = NULL;
    OSStatus status = errSecParam;
    int invoked = 0;
    const char *name = "unavailable";
    if (fixture_store_runtime_allowed() != 0 || fixture_store_bind() != 0) {
        fprintf(stderr, "store_refused\n");
        printf("result=unavailable\nkeychain_calls=0\n");
        return 1;
    }
    if (fixture_store_copy_matching(&found, &status, &invoked) != 0) {
        if (found != NULL) {
            CFRelease(found);
        }
        fprintf(stderr, "store_refused\n");
        printf("result=unavailable\nkeychain_calls=%d\n", invoked);
        return 1;
    }
    fprintf(stderr, "direct_lookup=interaction_bracket\n");
    if (status == errSecSuccess) {
        /* The password bytes are released with the process. They are not printed. */
        name = "ok";
    } else if (status == errSecItemNotFound) {
        name = "missing_key";
    } else if (status == errSecUserCanceled || status == errSecAuthFailed) {
        name = "denied";
    } else if (status == errSecInteractionNotAllowed || status == errSecNotAvailable) {
        name = "locked";
    }
    if (found != NULL) {
        CFRelease(found);
    }
    printf("result=%s\nkeychain_calls=%d\n", name, invoked);
    return strcmp(name, "ok") == 0 ? 0 : 1;
}
