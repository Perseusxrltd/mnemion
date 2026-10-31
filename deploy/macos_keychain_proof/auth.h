#ifndef MNEMION_KEYCHAIN_PROOF_AUTH_H
#define MNEMION_KEYCHAIN_PROOF_AUTH_H

#include <stddef.h>
#include <xpc/xpc.h>

/* Audit-bound caller check. PID, displayed name, and a pipe nonce are not
   inputs. Same-UID uses the public xpc_connection_get_euid call. Dynamic
   XPC peers use SecCodeCreateWithXPCMessage on the message itself. The helper
   requirement also pins the frozen helper cdhash. The on-disk bundle uses
   SecStaticCodeCheckValidity because it is not a message sender yet. */

int auth_pin_shape_ok(void);
int auth_pins_compile_only(void);
int auth_build_parent_requirement(char *buffer, size_t capacity);
int auth_build_helper_requirement(char *buffer, size_t capacity);
int auth_check_xpc_sender(xpc_object_t message, xpc_connection_t peer, const char *requirement);
int auth_check_bundle(const char *path, const char *requirement);

#endif
