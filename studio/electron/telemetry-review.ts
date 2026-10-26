/** Bounded local report state. No I/O, entropy, encoding or implicit approval. */
import type { TelemetryStamp } from '../shared/product-telemetry.js'
import { checkReviewLifetime, reviewLifetime, type ReviewClock, type ReviewLifetime } from './telemetry-review-lifetime.js'

export type ReviewBinding = {
  disclosure_version: number; wire_version: number; catalog_version: number
  destination: string; route_address: string | null
}
export type ReviewContext = { stamp: TelemetryStamp; groups: string[]; binding: ReviewBinding }
export type ReviewReport = ReviewContext & { packet: number[]; lifetime: ReviewLifetime }
export type ReviewMetadata = ReviewContext & { lifetime: ReviewLifetime }
export type ReviewState = {
  version: 1; mode: 'automatic' | 'review'; token: string | null
  outcome: 'inactive' | 'paused' | 'held' | 'approved' | 'consumed' | 'discarded' | 'invalidated' | 'expired'
  report: ReviewReport | null
}
const groups = ['usage', 'reliability', 'performance', 'resources']
const outcomes = ['inactive', 'paused', 'held', 'approved', 'consumed', 'discarded', 'invalidated', 'expired']
const integer = (value: unknown, max: number): value is number => typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= max
const token = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{32}$/.test(value)
const object = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value)
const keys = (value: Record<string, unknown>, names: string[]) => Object.keys(value).sort().join() === [...names].sort().join()
const invalid = () => new Error('telemetry_review_unavailable')

export const freshReview = (): ReviewState => ({ version: 1, mode: 'automatic', token: null, outcome: 'inactive', report: null })

export function reviewContext(value: unknown): ReviewContext {
  if (!object(value) || !keys(value, ['stamp', 'groups', 'binding']) || !object(value.stamp) ||
      !keys(value.stamp, ['revision', 'store_generation']) || !integer(value.stamp.revision, 2147483646) ||
      !token(value.stamp.store_generation) || !Array.isArray(value.groups) || !value.groups.length || value.groups.length > 4 ||
      new Set(value.groups).size !== value.groups.length || value.groups.some(group => !groups.includes(group))) throw invalid()
  const binding = value.binding
  if (!object(binding) || !keys(binding, ['disclosure_version', 'wire_version', 'catalog_version', 'destination', 'route_address']) ||
      !integer(binding.disclosure_version, 1000000) || !integer(binding.wire_version, 255) || !integer(binding.catalog_version, 1000000) ||
      typeof binding.destination !== 'string' || binding.destination.length > 512 ||
      !/^https:\/\/[^\s/?#@]+\/v1\/report$/.test(binding.destination) ||
      (binding.route_address !== null && (typeof binding.route_address !== 'string' || binding.route_address.length > 45 ||
        !/^[0-9a-f:.]+$/.test(binding.route_address)))) throw invalid()
  const permitted = value.groups
  return { stamp: { revision: value.stamp.revision, store_generation: value.stamp.store_generation },
    groups: groups.filter(group => permitted.includes(group)), binding: {
      disclosure_version: binding.disclosure_version, wire_version: binding.wire_version, catalog_version: binding.catalog_version,
      destination: binding.destination, route_address: binding.route_address as string | null } }
}

export function reviewState(value: unknown): ReviewState {
  if (!object(value) || !keys(value, ['version', 'mode', 'token', 'outcome', 'report']) || value.version !== 1 ||
      !['automatic', 'review'].includes(value.mode as string) || !outcomes.includes(value.outcome as string) ||
      (value.token !== null && !token(value.token)) ||
      (value.mode === 'automatic' ? value.outcome !== 'inactive' : value.outcome === 'inactive' || !token(value.token))) throw invalid()
  const live = value.outcome === 'held' || value.outcome === 'approved'
  if (live !== (value.report !== null)) throw invalid()
  let report: ReviewReport | null = null
  if (live) {
    const raw = value.report
    if (!object(raw) || !keys(raw, ['packet', 'stamp', 'groups', 'binding', 'lifetime']) ||
        !Array.isArray(raw.packet) || raw.packet.length !== 4 || raw.packet.some(byte => !integer(byte, 255))) throw invalid()
    const context = reviewContext({ stamp: raw.stamp, groups: raw.groups, binding: raw.binding })
    report = { ...context, packet: [...raw.packet], lifetime: reviewLifetime(raw.lifetime) }
  }
  return { version: 1, mode: value.mode as ReviewState['mode'], token: value.token as string | null,
    outcome: value.outcome as ReviewState['outcome'], report }
}

export function parseReview(raw: unknown): ReviewState {
  if (typeof raw !== 'string' || raw.length > 4096) throw invalid()
  return reviewState(JSON.parse(raw))
}
export function serializeReview(value: ReviewState): string {
  const raw = JSON.stringify(reviewState(value))
  if (raw.length > 4096) throw invalid()
  return raw
}

/** Invalidating a body never resumes automatic delivery or restores its input. */
export function clearReview(value: ReviewState, outcome: 'consumed' | 'discarded' | 'invalidated' | 'expired' = 'invalidated'): ReviewState {
  return { ...value, outcome: value.mode === 'automatic' ? 'inactive' : outcome, report: null }
}

export function checkReview(value: ReviewState, context: ReviewContext | null, now: number, clock: ReviewClock | null): ReviewState {
  const state = reviewState(value), report = state.report
  if (!report) return state
  try {
    const expected = reviewContext(context)
    if (JSON.stringify(reviewContext(reportContext(report))) !== JSON.stringify(expected)) return clearReview(state)
    const lifetime = checkReviewLifetime(report.lifetime, now, clock)
    return lifetime ? { ...state, report: { ...report, lifetime } } : clearReview(state, 'expired')
  } catch { return clearReview(state) }
}

function reportContext(value: ReviewReport): ReviewContext {
  return { stamp: value.stamp, groups: value.groups, binding: value.binding }
}

export function checkReviewMetadata(value: ReviewMetadata, context: ReviewContext, now: number, clock: ReviewClock | null): ReviewMetadata | null {
  try {
    const actual = reviewContext({ stamp: value.stamp, groups: value.groups, binding: value.binding })
    if (JSON.stringify(actual) !== JSON.stringify(reviewContext(context))) return null
    const lifetime = checkReviewLifetime(value.lifetime, now, clock)
    return lifetime ? { ...actual, lifetime } : null
  } catch { return null }
}
