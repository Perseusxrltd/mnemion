#include "signing.h"

#include <stdio.h>

int main(int argc, char **argv) {
    char cdhash[160];
    char identifier[256];
    char designated[1024];
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
