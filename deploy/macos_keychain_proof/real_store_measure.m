#include "bundle_manifest.h"
#include "protocol.h"
#include "signing.h"

#include <stdio.h>
#include <string.h>

/* Prints allowlisted measurement lines. It does not sign, trust, or open a
   store. Freeze output is private to the owner; compare output is booleans. */

struct described {
    char cdhash[160];
    char identifier[256];
    char designated[1024];
    char sha1[41];
    char sha256[65];
    char manifest[65];
};

static int describe_bundle(const char *path, struct described *out, int with_manifest) {
    char error[128];
    memset(out, 0, sizeof *out);
    if (signing_describe(path, out->cdhash, sizeof out->cdhash, out->identifier, sizeof out->identifier, out->designated,
                         sizeof out->designated) != 0 ||
        signing_leaf_der(path, out->sha1, sizeof out->sha1, out->sha256, sizeof out->sha256) != 0) {
        return -1;
    }
    if (!with_manifest) {
        return 0;
    }
    if (bundle_manifest_digest(path, out->manifest, sizeof out->manifest, error, sizeof error) != 0) {
        return -1;
    }
    return 0;
}

static int same_text(const char *left, const char *right) {
    return left != NULL && right != NULL && strcmp(left, right) == 0;
}

static void emit_bool(const char *key, int yes) {
    printf("%s=%s\n", key, yes ? "yes" : "no");
}

static int freeze_main(const char *bundle) {
    struct described helper;
    if (describe_bundle(bundle, &helper, 1) != 0 || helper.identifier[0] == '\0' || helper.designated[0] == '\0') {
        return 1;
    }
    printf("cdhash=%s\n", helper.cdhash);
    printf("identifier=%s\n", helper.identifier);
    printf("designated=%s\n", helper.designated);
    printf("leaf_sha1=%s\n", helper.sha1);
    printf("leaf_sha256=%s\n", helper.sha256);
    printf("manifest_sha256=%s\n", helper.manifest);
    return 0;
}

static int compare_main(const char *frozen, const char *helper_a, const char *helper_b, const char *parent_a,
                        const char *parent_b) {
    struct described frozen_helper;
    struct described copy_a;
    struct described copy_b;
    struct described parent_one;
    struct described parent_two;
    char error[128];
    int trees_ok;
    int manifest_ok;
    int cdhash_ok;
    int requirement_ok;
    int identifier_ok;
    int helper_der_ok;
    int parents_distinct;
    int parent_identifier_ok;
    int parent_der_ok;
    int parent_helper_der_ok;
    int frozen_trees_a;
    int frozen_trees_b;
    if (describe_bundle(frozen, &frozen_helper, 1) != 0 || describe_bundle(helper_a, &copy_a, 1) != 0 ||
        describe_bundle(helper_b, &copy_b, 1) != 0 || describe_bundle(parent_a, &parent_one, 0) != 0 ||
        describe_bundle(parent_b, &parent_two, 0) != 0) {
        return 1;
    }
    frozen_trees_a = bundle_trees_equal(frozen, helper_a, error, sizeof error) == 0;
    frozen_trees_b = bundle_trees_equal(frozen, helper_b, error, sizeof error) == 0;
    trees_ok = frozen_trees_a && frozen_trees_b;
    manifest_ok = same_text(frozen_helper.manifest, copy_a.manifest) && same_text(frozen_helper.manifest, copy_b.manifest);
    cdhash_ok = same_text(frozen_helper.cdhash, copy_a.cdhash) && same_text(frozen_helper.cdhash, copy_b.cdhash);
    requirement_ok =
        same_text(frozen_helper.designated, copy_a.designated) && same_text(frozen_helper.designated, copy_b.designated);
    identifier_ok = same_text(frozen_helper.identifier, MNEMION_HELPER_IDENTIFIER) &&
                    same_text(copy_a.identifier, MNEMION_HELPER_IDENTIFIER) &&
                    same_text(copy_b.identifier, MNEMION_HELPER_IDENTIFIER);
    helper_der_ok = same_text(frozen_helper.sha1, copy_a.sha1) && same_text(frozen_helper.sha1, copy_b.sha1) &&
                    same_text(frozen_helper.sha256, copy_a.sha256) && same_text(frozen_helper.sha256, copy_b.sha256);
    parents_distinct = parent_one.cdhash[0] != '\0' && strcmp(parent_one.cdhash, parent_two.cdhash) != 0;
    parent_identifier_ok = same_text(parent_one.identifier, MNEMION_PARENT_IDENTIFIER) &&
                           same_text(parent_two.identifier, MNEMION_PARENT_IDENTIFIER);
    parent_der_ok = same_text(parent_one.sha1, parent_two.sha1) && same_text(parent_one.sha256, parent_two.sha256);
    parent_helper_der_ok = same_text(parent_one.sha1, frozen_helper.sha1) && same_text(parent_one.sha256, frozen_helper.sha256);
    emit_bool("trees_equal", trees_ok);
    emit_bool("manifest_equal", manifest_ok);
    emit_bool("helper_cdhash_equal", cdhash_ok);
    emit_bool("helper_requirement_equal", requirement_ok);
    emit_bool("helper_identifier_equal", identifier_ok);
    emit_bool("helper_der_equal", helper_der_ok);
    emit_bool("parent_cdhash_distinct", parents_distinct);
    emit_bool("parent_identifier_equal", parent_identifier_ok);
    emit_bool("parent_der_equal", parent_der_ok);
    emit_bool("parent_helper_der_equal", parent_helper_der_ok);
    if (!trees_ok || !manifest_ok || !cdhash_ok || !requirement_ok || !identifier_ok || !helper_der_ok ||
        !parents_distinct || !parent_identifier_ok || !parent_der_ok || !parent_helper_der_ok) {
        return 1;
    }
    return 0;
}

int main(int argc, char **argv) {
    if (argc == 3 && strcmp(argv[1], "freeze") == 0) {
        return freeze_main(argv[2]);
    }
    if (argc == 7 && strcmp(argv[1], "compare") == 0) {
        return compare_main(argv[2], argv[3], argv[4], argv[5], argv[6]);
    }
    fprintf(stderr, "usage: real-store-measure freeze|compare\n");
    return 2;
}
