#ifndef MNEMION_KEYCHAIN_PROOF_AUTH_H
#define MNEMION_KEYCHAIN_PROOF_AUTH_H

#include <stddef.h>
#include <xpc/xpc.h>

/* Audit-bound caller check. PID, displayed name, and a pipe nonce are not
   inputs. Same-UID uses the public xpc_connection_get_euid call. Dynamic
   XPC peers use SecCodeCreateWithXPCMessage on the message itself. This file
   pins the caller certificate only. The frozen helper cdhash, manifest,
   identifier, and designated requirement stay in exact_helper.h so the helper
   can be signed before those pins exist. The on-disk bundle uses
   SecStaticCodeCheckValidity because it is not a message sender yet. */

enum {
    AUTH_HEX_ANY = 0,
    AUTH_HEX_UPPER = 1,
    AUTH_HEX_LOWER = 2
};

int auth_hex_pin(const char *pin, size_t expect, int letter_case);
int auth_copy_upper_hex(const char *pin, size_t expect, char *out);
int auth_caller_pin_shape_ok(void);
int auth_pins_compile_only(void);
int auth_build_parent_requirement(char *buffer, size_t capacity);
int auth_check_xpc_sender(xpc_object_t message, xpc_connection_t peer, const char *requirement);
int auth_check_bundle(const char *path, const char *requirement);

#endif
