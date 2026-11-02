/** One recorded-activity page for the memory map. The service limit is 40. */
export const MAP_ACTIVITY_PAGE_SIZE = 40

/** Page positions kept, including the page now open. Event rows from other pages are not kept. */
export const MAP_ACTIVITY_RETAINED_PAGES = 40

const MATCHING_ACTIONS = new Set(["memory.created", "memory.revised", "memory.reviewed"])

export type MapActivityEvent = {
  id: string
  principal_id: string
  action: string
  resource_id: string
  reason: string | null
  created_at: string
}

export type MapActivityPage = {
  items: readonly MapActivityEvent[]
  next_cursor?: string | null
}

export type MapActivityScope = {
  endpoint: string
  access: string
  space: string
  reviewer: boolean
  administrator: boolean
  search: string
  kind: string
  creator: string
  hours: number
  limit: number
  focus: string
}

export type MapActivityRequest = { scopeKey: string; cursor?: string }

export type MapActivityPlace = {
  scopeKey: string
  cursor?: string
  previous: (string | undefined)[]
  truncated: boolean
}

/** Explicit workspace, access, and map query. A later graph snapshot's memory ids are not part of this key. */
export function mapActivityScopeKey(scope: MapActivityScope): string {
  return JSON.stringify([
    scope.endpoint,
    scope.access,
    scope.space,
    scope.reviewer,
    scope.administrator,
    scope.search,
    scope.kind,
    scope.creator,
    scope.hours,
    scope.limit,
    scope.focus,
  ])
}

/** Directory cache identity. `access` is the caller's principal and access tuple, never a credential or a counter that starts again at zero after remount. */
export function mapDirectoryQueryKey(access: string, endpoint: string, space: string) {
  return ["map-identities", access, endpoint, space] as const
}

export function directoryNames<T extends { id: string; name: string; kind: string }>(
  administrator: boolean,
  failed: boolean,
  items: readonly T[] | undefined,
): Map<string, T> {
  if (!administrator || failed || !items) return new Map()
  return new Map(items.map(item => [item.id, item]))
}

/** Open page plus the cursors Newer can still return to. */
export function mapActivityPositionCount(place: MapActivityPlace): number {
  return place.previous.length + 1
}

export function initialMapActivity(scopeKey: string): MapActivityPlace {
  return { scopeKey, previous: [], truncated: false }
}

/** Drop a cursor from another workspace, access grant, or map query. */
export function placedMapActivity(place: MapActivityPlace, scopeKey: string): MapActivityPlace {
  return place.scopeKey === scopeKey ? place : initialMapActivity(scopeKey)
}

export function earlierMapActivity(place: MapActivityPlace, nextCursor: string): MapActivityPlace {
  if (!nextCursor || nextCursor === place.cursor) return place
  const history = [...place.previous, place.cursor]
  const keptHistory = MAP_ACTIVITY_RETAINED_PAGES - 1
  const truncated = place.truncated || history.length > keptHistory
  return {
    scopeKey: place.scopeKey,
    cursor: nextCursor,
    previous: truncated ? history.slice(history.length - keptHistory) : history,
    truncated,
  }
}

export function newerMapActivity(place: MapActivityPlace): MapActivityPlace {
  if (!place.previous.length) return place
  const previous = place.previous.slice(0, -1)
  return { scopeKey: place.scopeKey, cursor: place.previous.at(-1), previous, truncated: place.truncated }
}

export function latestMapActivity(place: MapActivityPlace): MapActivityPlace {
  return initialMapActivity(place.scopeKey)
}

export function relevantMapActivity(items: readonly MapActivityEvent[], visibleMemoryIds: ReadonlySet<string>): MapActivityEvent[] {
  return items.filter(event => visibleMemoryIds.has(event.resource_id) && MATCHING_ACTIONS.has(event.action))
}

/** Newest page follows the map's 20s live check. An earlier page waits for a click. */
export function mapActivityPoll(live: boolean, cursor: string | undefined): number | false {
  return live && cursor === undefined ? 20_000 : false
}

export type MapActivityView = {
  kind: "closed" | "loading" | "error" | "legacy" | "empty-page" | "empty-end" | "events"
  events: MapActivityEvent[]
  canEarlier: boolean
  canNewer: boolean
  canLatest: boolean
  truncated: boolean
  end: boolean
}

export function mapActivityView(input: {
  reviewer: boolean
  pending: boolean
  error: boolean
  page: MapActivityPage | undefined
  pageRequest: MapActivityRequest
  place: MapActivityPlace
  visibleMemoryIds: ReadonlySet<string>
}): MapActivityView {
  const navigation = {
    canNewer: input.place.previous.length > 0,
    canLatest: input.place.cursor !== undefined,
    truncated: input.place.truncated,
    events: [] as MapActivityEvent[],
    canEarlier: false,
    end: false,
  }
  if (!input.reviewer) return { ...navigation, kind: "closed", canNewer: false, canLatest: false, truncated: false }
  const current = input.pageRequest.scopeKey === input.place.scopeKey && input.pageRequest.cursor === input.place.cursor
  if (!current) return { ...navigation, kind: "loading" }
  if (input.error) return { ...navigation, kind: "error" }
  if (input.pending || !input.page) return { ...navigation, kind: "loading" }
  const events = relevantMapActivity(input.page.items, input.visibleMemoryIds)
  const knownCursor = Object.hasOwn(input.page, "next_cursor")
  const nextCursor = knownCursor ? input.page.next_cursor : undefined
  const canEarlier = typeof nextCursor === "string" && nextCursor.length > 0
  const end = knownCursor && !canEarlier
  if (!knownCursor) return { ...navigation, kind: "legacy", events, canEarlier: false, end: false }
  if (!events.length) return { ...navigation, kind: end ? "empty-end" : "empty-page", canEarlier, end }
  return { ...navigation, kind: "events", events, canEarlier, end }
}
