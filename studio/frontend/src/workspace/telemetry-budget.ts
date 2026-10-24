/** Origin-local spending metadata. Never a request body or analytics identity. */
import type { TelemetryStatus } from '../../../shared/product-telemetry'
export const choiceKey = 'mnemion.product-telemetry.choice.v1'
export const queueKey = 'mnemion.product-telemetry.pending.v1'
export const budgetKey = 'mnemion.product-telemetry.budget.v1'
export const DAY = 86400000, WEEK = 7 * DAY, DEADLINE = 5000, JITTER = 3600000
export const COST = 65536, DAILY_BYTES = 262144, MAX_CLOCK = 86400000000000
export type BrowserBudget = {
  version: 1; generation: string; clock_ms: number; next_ms: number
  attempts: { at_ms: number; reserved_bytes: number }[]
  lease: { token: string; deadline_ms: number } | null
  clear: 'none' | 'entries' | 'all'
}
export const generationValid = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{32}$/.test(value)
export const clockValid = (value: unknown, maximum = MAX_CLOCK): value is number =>
  typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 && value <= maximum
const object = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value)
const keys = (value: Record<string, unknown>, names: string[]) => Object.keys(value).sort().join() === [...names].sort().join()
const failure = () => new Error('telemetry_budget_unavailable')

export function freshBudget(generation: string): BrowserBudget {
  if (!generationValid(generation)) throw failure()
  return { version: 1, generation, clock_ms: 0, next_ms: 0, attempts: [], lease: null, clear: 'none' }
}

export function budgetState(raw: string): BrowserBudget {
  if (typeof raw !== 'string' || raw.length > 8192) throw failure()
  const value: unknown = JSON.parse(raw)
  if (!object(value) || !keys(value, ['version', 'generation', 'clock_ms', 'next_ms', 'attempts', 'lease', 'clear']) ||
      value.version !== 1 || !generationValid(value.generation) || !clockValid(value.clock_ms) || !clockValid(value.next_ms) ||
      !Array.isArray(value.attempts) || value.attempts.length > 7 || !['none', 'entries', 'all'].includes(value.clear as string)) throw failure()
  const at = new Set<number>()
  for (const item of value.attempts) {
    if (!object(item) || !keys(item, ['at_ms', 'reserved_bytes']) || !clockValid(item.at_ms) ||
        item.at_ms > value.clock_ms || item.reserved_bytes !== COST || at.has(item.at_ms)) throw failure()
    at.add(item.at_ms)
  }
  const lease = value.lease
  if (lease !== null && (!object(lease) || !keys(lease, ['token', 'deadline_ms']) ||
      !generationValid(lease.token) || lease.deadline_ms !== value.clock_ms + DEADLINE)) throw failure()
  if (at.size) {
    if (Math.max(...at) !== value.clock_ms || value.next_ms < value.clock_ms + DAY ||
        value.next_ms > value.clock_ms + DAY + JITTER) throw failure()
  } else if (value.clock_ms !== 0 || value.next_ms !== 0 || lease !== null) throw failure()
  return value as BrowserBudget
}

export function serializeBudget(value: BrowserBudget): string {
  const raw = JSON.stringify(value)
  budgetState(raw)
  return raw
}

export function budgetView(value: BrowserBudget | null, now = Date.now(), missing: 'not_initialized' | 'upgrade_required' = 'not_initialized'): NonNullable<TelemetryStatus['delivery_budget']> {
  if (!clockValid(now)) throw failure()
  return {
    state: !value ? missing : now < value.clock_ms ? 'clock_rollback'
      : value.lease && now < value.lease.deadline_ms ? 'in_flight' : now < value.next_ms ? 'cooldown' : 'ready',
    maximum_attempts_per_rolling_week: 7, minimum_attempt_spacing_seconds: DAY / 1000,
    wire_reservation_per_attempt_bytes: COST, wire_budget_per_rolling_day_bytes: DAILY_BYTES,
    attempts_in_rolling_week: value ? value.attempts.filter(item => item.at_ms > now - WEEK).length : 0,
    reserved_wire_bytes_in_rolling_day: value ? value.attempts.filter(item => item.at_ms > now - DAY).reduce((sum, item) => sum + item.reserved_bytes, 0) : 0,
    transport_available: false,
  }
}

/** The caller must hold the origin-wide privacy lock and recheck its policy. */
export function reserveBudget(value: BrowserBudget, now: number, token: string, jitter: number): BrowserBudget | null {
  if (!clockValid(now, MAX_CLOCK - DAY - JITTER) || !generationValid(token) || !clockValid(jitter, JITTER) ||
      value.clear !== 'none' || now < value.clock_ms || now < value.next_ms ||
      (value.lease && now < value.lease.deadline_ms)) return null
  const attempts = value.attempts.filter(item => item.at_ms > now - WEEK)
  if (attempts.length >= 7 || attempts.filter(item => item.at_ms > now - DAY).reduce((sum, item) => sum + item.reserved_bytes, 0) + COST > DAILY_BYTES) return null
  return { ...value, clock_ms: now, next_ms: now + DAY + jitter,
    attempts: [...attempts, { at_ms: now, reserved_bytes: COST }],
    lease: { token, deadline_ms: now + DEADLINE }, clear: 'entries' }
}
