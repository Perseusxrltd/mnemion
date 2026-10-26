/** Portable bounded inspection lifetime. No clock reads, entropy or networking. */
export type ReviewClock = { epoch: string; elapsed_ms: number }
export type ReviewLifetime = {
  created_ms: number; expires_ms: number; checked_ms: number
  clock: ReviewClock; checked_elapsed_ms: number
}
export const REVIEW_LIFETIME_MS = 15 * 60 * 1000
const MAX_WALL_MS = 86400000000000
const integer = (value: unknown, maximum = Number.MAX_SAFE_INTEGER): value is number =>
  typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 && value <= maximum
const record = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)
const keys = (value: Record<string, unknown>, names: string[]) =>
  Object.keys(value).sort().join() === [...names].sort().join()
const invalid = () => new Error('telemetry_review_clock_unavailable')

export function reviewClock(value: unknown): ReviewClock {
  if (!record(value) || !keys(value, ['epoch', 'elapsed_ms']) ||
      typeof value.epoch !== 'string' || !/^[0-9a-f]{32}$/.test(value.epoch) || /^0+$/.test(value.epoch) ||
      !integer(value.elapsed_ms)) throw invalid()
  return { epoch: value.epoch, elapsed_ms: value.elapsed_ms }
}

export function reviewLifetime(value: unknown): ReviewLifetime {
  if (!record(value) || !keys(value, ['created_ms', 'expires_ms', 'checked_ms', 'clock', 'checked_elapsed_ms']) ||
      !integer(value.created_ms, MAX_WALL_MS) || !integer(value.expires_ms, MAX_WALL_MS) ||
      !integer(value.checked_ms, MAX_WALL_MS) || !integer(value.checked_elapsed_ms) ||
      value.expires_ms <= value.created_ms || value.expires_ms - value.created_ms > REVIEW_LIFETIME_MS ||
      value.checked_ms < value.created_ms || value.checked_ms >= value.expires_ms) throw invalid()
  const clock = reviewClock(value.clock)
  if (value.checked_elapsed_ms < clock.elapsed_ms ||
      value.checked_elapsed_ms - clock.elapsed_ms >= value.expires_ms - value.created_ms) throw invalid()
  return { created_ms: value.created_ms, expires_ms: value.expires_ms, checked_ms: value.checked_ms,
    clock, checked_elapsed_ms: value.checked_elapsed_ms }
}

export function startReviewLifetime(now: number, clock: ReviewClock, observationExpiry: number): ReviewLifetime {
  if (!integer(now, MAX_WALL_MS - REVIEW_LIFETIME_MS) || !integer(observationExpiry, MAX_WALL_MS)) throw invalid()
  const measured = reviewClock(clock)
  return reviewLifetime({ created_ms: now, expires_ms: Math.min(now + REVIEW_LIFETIME_MS, observationExpiry),
    checked_ms: now, clock: measured, checked_elapsed_ms: measured.elapsed_ms })
}

/** Neither a new process nor a successful read/approval renews the original age. */
export function checkReviewLifetime(value: ReviewLifetime, now: number, clock: ReviewClock | null): ReviewLifetime | null {
  try {
    const lifetime = reviewLifetime(value), measured = reviewClock(clock)
    if (!integer(now, MAX_WALL_MS) || now < lifetime.checked_ms || now >= lifetime.expires_ms ||
        measured.epoch !== lifetime.clock.epoch || measured.elapsed_ms < lifetime.checked_elapsed_ms ||
        measured.elapsed_ms - lifetime.clock.elapsed_ms >= lifetime.expires_ms - lifetime.created_ms) return null
    return { ...lifetime, checked_ms: now, checked_elapsed_ms: measured.elapsed_ms }
  } catch { return null }
}
