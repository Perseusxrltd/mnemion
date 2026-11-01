#ifndef MNEMION_EXACT_HELPER_H
#define MNEMION_EXACT_HELPER_H

#include <stddef.h>

/* Parent-only. The helper binary does not link this file.
   These checks name one frozen helper: manifest, identifier, designated
   requirement, and cdhash. Caller certificate pins stay in auth. */

int auth_exact_helper_pin_shape_ok(void);
int auth_build_helper_requirement(char *buffer, size_t capacity);

#endif
