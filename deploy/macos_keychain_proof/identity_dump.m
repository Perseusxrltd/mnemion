#include "signing.h"

#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    char cdhash[160];
    char identifier[256];
    char designated[1024];
    char sha1[41];
    char sha256[65];
    /* The original bundle form stays the entry point. der is an added
       measurement. Manifest walks live in real_store_measure so this tool
       keeps the compile-only link line. */
    if (argc == 3 && strcmp(argv[1], "der") == 0) {
        if (signing_leaf_der(argv[2], sha1, sizeof sha1, sha256, sizeof sha256) != 0) {
            fprintf(stderr, "der_unavailable\n");
            return 1;
        }
        printf("leaf_sha1=%s\nleaf_sha256=%s\n", sha1, sha256);
        return 0;
    }
    if (argc != 2) {
        fprintf(stderr, "usage: identity_dump bundle\n");
        return 2;
    }
    if (signing_describe(argv[1], cdhash, sizeof cdhash, identifier, sizeof identifier,
                         designated, sizeof designated) != 0) {
        fprintf(stderr, "identity_unavailable\n");
        return 1;
    }
    printf("cdhash=%s\nidentifier=%s\ndesignated=%s\n", cdhash, identifier, designated);
    return 0;
}
