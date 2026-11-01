#ifndef MNEMION_PARENT_DIRECT_LOOKUP_H
#define MNEMION_PARENT_DIRECT_LOOKUP_H

/* Parent direct lookup, split out so the injected fixture can call this
   body without linking the parent's signing, XPC, or helper-pin path.
   The bytes of the check are the direct-lookup command. */

int parent_direct_lookup(void);

#endif
