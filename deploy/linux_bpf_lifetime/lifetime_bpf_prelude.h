#ifndef LIFETIME_BPF_PRELUDE_H
#define LIFETIME_BPF_PRELUDE_H

/* Public BPF UAPI before any libbpf helper header.
 * linux/types.h provides __u8, __u32 and __u64.
 * linux/bpf.h provides the map type and update constants.
 * The matching asm directory is the multiarch include path in the Makefile:
 * /usr/include/x86_64-linux-gnu on x64, /usr/include/aarch64-linux-gnu on ARM64.
 */

#include <linux/types.h>
#include <linux/bpf.h>

#endif
