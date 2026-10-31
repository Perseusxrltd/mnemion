#ifndef MNEMION_KEYCHAIN_PROOF_KEY_ITEM_H
#define MNEMION_KEYCHAIN_PROOF_KEY_ITEM_H

#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>

/* Login-item lookup for the fixed service and account only.
   No path, ACL, partition, access group, or raw-key return across XPC.
   keychain_calls counts SecItem entries and is not a credential.
   allow_prompt 0 asks SecItem to fail instead of presenting UI. It does not
   change the item, its ACL, or its partition. */

enum key_result {
    KEY_OK = 0,
    KEY_ABSENT,
    KEY_DENIED,
    KEY_LOCKED,
    KEY_UNAVAILABLE
};

struct key_state {
    uint8_t derived[16];
    int derived_valid;
    atomic_uint_fast64_t keychain_calls;
};

void key_state_init(struct key_state *state);
void key_state_zero(struct key_state *state);

enum key_result key_item_load(struct key_state *state, int allow_prompt);
enum key_result key_item_create_empty(struct key_state *state);

#endif
