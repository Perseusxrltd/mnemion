/** Fixed numeric main-process counters. No mappings, paths, names or other strings. */

import { closeSync, openSync, readSync } from 'node:fs'

export const LINUX_FIELDS = ['VmRSS', 'VmHWM', 'RssAnon', 'RssFile', 'RssShmem']
export const HEAP_FIELDS = ['total_heap_size', 'total_physical_size', 'used_heap_size', 'malloced_memory']
const STATUS_LIMIT = 65536

export function unavailableLinux() {
  return Object.fromEntries(LINUX_FIELDS.map(field => [field, null]))
}

function numeric(value) {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : null
}

/** A missing, oversized or malformed status is unavailable, not zero. */
export function parseLinuxStatus(text) {
  const result = unavailableLinux()
  if (typeof text !== 'string' || text.length > STATUS_LIMIT) return result
  for (const field of LINUX_FIELDS) {
    const match = text.match(new RegExp(`^${field}:\\s+(\\d+) kB$`, 'm'))
    if (!match) continue
    const bytes = Number(match[1]) * 1024
    if (numeric(bytes) === null) continue
    result[field] = bytes
  }
  return result
}

/**
 * Read at most one byte past the cap so an oversized status cannot be parsed
 * from a truncated line. Non-Linux and oversized input are unavailable.
 * An IO failure is thrown so the caller can choose nulls or an error record.
 */
export function readBoundedLinuxStatus() {
  if (process.platform !== 'linux') return unavailableLinux()
  const fd = openSync('/proc/self/status', 'r')
  try {
    const buffer = Buffer.alloc(STATUS_LIMIT + 1)
    const count = readSync(fd, buffer, 0, buffer.length, 0)
    if (count > STATUS_LIMIT) return unavailableLinux()
    return parseLinuxStatus(buffer.toString('utf8', 0, count))
  } finally {
    closeSync(fd)
  }
}

/** Reserved, committed, live, and V8 malloc bytes. Other statistics are dropped. */
export function selectHeap(statistics) {
  return Object.fromEntries(HEAP_FIELDS.map(field => [field, numeric(statistics?.[field])]))
}
