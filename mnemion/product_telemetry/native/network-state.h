/* SPDX-License-Identifier: MIT
 * Only fixed, process-local admission flags cross this ABI. No identifiers. */
#ifndef MNEMION_NETWORK_STATE_H
#define MNEMION_NETWORK_STATE_H
#include <stdint.h>
#if defined(_WIN32)
#define MNM_EXPORT __declspec(dllexport)
#else
#define MNM_EXPORT __attribute__((visibility("default")))
#endif
enum { MNM_UNKNOWN = 0, MNM_UNMETERED = 1, MNM_METERED = 2,
       MNM_CONSTRAINED = 4, MNM_OBSERVED = 8 };
MNM_EXPORT uint32_t mnemion_network_state_v1(void);
/* Pure decoders are also used by the native cross-platform contract test. */
uint32_t mnm_windows_cost(uint32_t cost, uint32_t level, int approaching, int over, int roaming);
uint32_t mnm_linux_cost(uint32_t cost, uint32_t state);
#endif
