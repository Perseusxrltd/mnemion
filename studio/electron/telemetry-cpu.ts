/** Current aggregate CPU admission, never a measurement or hardware profile. */
import { cpus, type CpuInfo } from 'node:os'
import { nativeCpuTotals } from './telemetry-network.js'

export type CpuTotals = { idle: number; total: number; count: number; source: 'native' | 'node' }
const integer = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0

function valid(idle: unknown, total: unknown, count: unknown): boolean {
  return integer(idle) && integer(total) && integer(count) && total > 0 && idle <= total && count > 0 && count <= 1048576
}

export function readCpuTotals(native: () => unknown = nativeCpuTotals, fallback: () => CpuInfo[] = cpus): CpuTotals | null {
  try {
    const value = native()
    if (Array.isArray(value) && value.length === 3 && valid(value[0], value[1], value[2])) {
      return { idle: value[0], total: value[1], count: value[2], source: 'native' }
    }
  } catch { /* An older, missing or unavailable helper retains the existing OS path. */ }
  try {
    const cores = fallback()
    if (!Array.isArray(cores) || !cores.length || cores.length > 1048576) return null
    let idle = 0, total = 0
    for (const core of cores) {
      const times = core.times
      if (!integer(times.user) || !integer(times.nice) || !integer(times.sys) || !integer(times.idle) || !integer(times.irq)) return null
      idle += times.idle
      total += times.user + times.nice + times.sys + times.idle + times.irq
    }
    return valid(idle, total, cores.length) ? { idle, total, count: cores.length, source: 'node' } : null
  } catch { return null }
}
