/* SPDX-License-Identifier: MIT
 * Fixed, process-local admission flags and aggregate CPU counters. No identifiers. */
#ifndef MNEMION_NETWORK_STATE_H
#define MNEMION_NETWORK_STATE_H
#include <stddef.h>
#include <stdint.h>
#if defined(_WIN32)
#define MNM_EXPORT __declspec(dllexport)
#else
#define MNM_EXPORT __attribute__((visibility("default")))
#endif
enum { MNM_UNKNOWN = 0, MNM_UNMETERED = 1, MNM_METERED = 2,
       MNM_CONSTRAINED = 4, MNM_OBSERVED = 8 };
MNM_EXPORT uint32_t mnemion_network_state_v1(void);
/* Counter units are platform-local. Consumers must reset a delta when changing
 * counter sources or CPU count. These values are never outbound measurements. */
typedef struct { uint64_t idle, total; uint32_t count; } MnmCpuTotals;
MNM_EXPORT int mnemion_cpu_totals_v1(MnmCpuTotals *output);
/* Review-lifetime fencing only. The epoch is local control state, never a
 * measurement, hardware identity or outbound value. Windows initializes an
 * ephemeral per-user registry marker, which disappears when its hive unloads. */
typedef struct { uint64_t elapsed_ms; unsigned char epoch[16]; } MnmReviewClock;
/* initialize=1 is reserved for an explicit inspection action. Ordinary status,
 * format preview and sender checks pass 0 and never initialize the marker. */
MNM_EXPORT int mnemion_review_clock_v1(int initialize, MnmReviewClock *output);
/* Pure decoders are also used by the native cross-platform contract test. */
uint32_t mnm_windows_cost(uint32_t cost, uint32_t level, int approaching, int over, int roaming);
uint32_t mnm_linux_cost(uint32_t cost, uint32_t state);
int mnm_cpu_totals(uint64_t idle, uint64_t user, uint64_t nice, uint64_t system,
                   uint64_t irq, uint32_t count, MnmCpuTotals *output);
int mnm_linux_cpu_totals(const char *line, size_t length, uint32_t count, MnmCpuTotals *output);
int mnm_review_clock(const char *epoch, size_t length, uint64_t elapsed_ms, MnmReviewClock *output);
#endif
