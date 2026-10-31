#ifndef MNEMION_BUNDLE_MANIFEST_H
#define MNEMION_BUNDLE_MANIFEST_H

#include <stddef.h>

/* Exact file list of a signed helper bundle. Paths are relative and sorted.
   Symlinks, devices, and unexpected path bytes fail closed. Comparison uses
   the bytes already read, or one descriptor kept open. It does not close and
   reopen a temporary path. */

int bundle_manifest_write(const char *root, const char *destination, char *error, size_t error_cap);
int bundle_manifest_check(const char *root, const char *manifest_path, char *error, size_t error_cap);
int bundle_manifest_digest(const char *root, char *hex, size_t hex_cap, char *error, size_t error_cap);
int bundle_trees_equal(const char *left, const char *right, char *error, size_t error_cap);

#endif
