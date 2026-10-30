/* SPDX-License-Identifier: MIT
 * Read-only Windows owner/DACL decision shared by the helper process and the
 * in-process Node addon. No content, repair, settings, or network. */
#ifndef MNEMION_PRIVATE_STORE_H
#define MNEMION_PRIVATE_STORE_H
#if defined(_WIN32)
#include <wchar.h>
/* 1 only when both paths currently pass the owner, DACL, reparse, type,
 * hardlink and size checks. 0 refuses. Callers pass terminated strings.
 * The call closes every handle it opens before returning. */
int mnemion_private_store_accessible(const wchar_t *root, const wchar_t *database);
#endif
#endif
