/** A shared native clock for explicit review controls, never product measurements. */
import { nativeReviewClock } from './telemetry-network.js'
import { reviewClock, type ReviewClock } from './telemetry-review-lifetime.js'

export function readReviewClock(initialize = false, read = nativeReviewClock): ReviewClock | null {
  if (typeof initialize !== 'boolean') return null
  try {
    const value = read(initialize)
    if (!Array.isArray(value) || value.length !== 2) return null
    return reviewClock({ elapsed_ms: value[0], epoch: value[1] })
  } catch { return null }
}
