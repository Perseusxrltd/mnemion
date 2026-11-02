import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'
import { test } from 'node:test'
import ts from 'typescript'

const source = readFileSync(new URL('../src/workspace/map-model.ts', import.meta.url), 'utf8')
const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
const { positionGraph, filterGraph, project } = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'))
const options = { search: '', kind: '', creator: '', since: 0, focus: '', limit: 300 }

function fixture(count = 8) {
  const result = { nodes: [{ id: 'space:one', kind: 'space', space_id: 'one', label: 'Workspace' }, { id: 'entity:topic', kind: 'entity', space_id: 'one', label: 'Shared topic' }], edges: [], memories: [] }
  for (let i = 0; i < count; i++) {
    result.memories.push({ memory_id: String(i), created_by: i % 2 ? 'agent-b' : 'agent-a', updated_at: `2026-10-${i % 2 ? '10' : '11'}T00:00:00Z` })
    result.nodes.push({ id: 'memory:' + i, memory_id: String(i), kind: 'memory', space_id: 'one', label: 'Memory ' + i })
    result.nodes.push({ id: 'source:' + i, memory_id: String(i), kind: 'source', space_id: 'one', label: 'Source ' + i })
    result.edges.push({ source: 'memory:' + i, target: 'entity:topic', relation: 'about' }, { source: 'memory:' + i, target: 'source:' + i, relation: 'cites' }, { source: 'memory:' + i, target: 'space:one', relation: 'in_space' })
  }
  return result
}

test('live additions and input order do not move unchanged memory and subject anchors', () => {
  const before = positionGraph(fixture(8))
  const larger = fixture(9); larger.nodes.reverse(); larger.edges.reverse()
  const after = positionGraph(larger)
  for (const old of before.nodes.filter(node => node.kind !== 'source')) {
    const current = after.nodes.find(node => node.id === old.id)
    assert.deepEqual([current.x, current.y, current.z], [old.x, old.y, old.z])
  }
})

test('creator and time filters do not include other memories through a shared topic', () => {
  const result = fixture()
  const view = filterGraph(positionGraph(result), result, { ...options, creator: 'agent-a', since: Date.parse('2026-10-11T00:00:00Z') })
  assert.equal(view.nodes.filter(node => node.kind === 'memory').length, 4)
  assert.ok(!view.nodes.some(node => node.id === 'memory:1' || node.id === 'source:1'))
  assert.ok(view.nodes.some(node => node.id === 'entity:topic'))
})

test('the node budget keeps evidence and focus, and never leaves dangling or invented edges', () => {
  const result = fixture(250)
  result.edges.push({ source: 'memory:0', target: 'unavailable-private-node', relation: 'about' })
  const graph = positionGraph(result)
  const view = filterGraph(graph, result, { ...options, limit: 32, focus: 'memory:3' })
  const ids = new Set(view.nodes.map(node => node.id))
  assert.ok(ids.has('memory:3') && ids.has('source:3'))
  assert.ok(view.nodes.length <= 32)
  assert.ok(view.edges.every(edge => ids.has(edge.source) && ids.has(edge.target) && result.edges.includes(edge)))
  assert.ok(!graph.edges.some(edge => edge.target === 'unavailable-private-node'))
  const large = filterGraph(graph, result, { ...options, limit: 32 })
  assert.equal(large.nodes.length, 32)
  assert.equal(new Set(large.nodes.map(node => node.kind)).size, 4)
})

test('removed access cannot be restored by a stale selection or search', () => {
  const result = fixture(2)
  result.nodes = result.nodes.filter(node => !['memory:1', 'source:1'].includes(node.id))
  result.memories = result.memories.filter(memory => memory.memory_id !== '1')
  const view = filterGraph(positionGraph(result), result, { ...options, focus: 'memory:1', search: 'Memory 1' })
  assert.equal(view.nodes.length, 0)
  assert.equal(view.edges.length, 0)
})

test('3D rotation changes projected depth and the flat fallback ignores orbit', () => {
  const point = { x: 70, y: 45, z: 110 }, first = { yaw: 0, pitch: 0, zoom: 1 }, second = { yaw: 1, pitch: .5, zoom: 1 }
  const a = project(point, first, 800, 500), b = project(point, second, 800, 500)
  assert.notEqual(a.x, b.x)
  assert.notEqual(a.z, b.z)
  assert.deepEqual(project(point, first, 800, 500, true), project(point, second, 800, 500, true))
  assert.ok(Object.values(b).every(Number.isFinite))
})

const activitySource = readFileSync(new URL('../src/workspace/map-activity.ts', import.meta.url), 'utf8')
const activityCode = ts.transpileModule(activitySource, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
const activity = await import('data:text/javascript;base64,' + Buffer.from(activityCode).toString('base64'))
const {
  MAP_ACTIVITY_PAGE_SIZE, MAP_ACTIVITY_RETAINED_PAGES, directoryNames, earlierMapActivity, initialMapActivity, latestMapActivity,
  mapActivityPoll, mapActivityPositionCount, mapActivityScopeKey, mapActivityView, mapDirectoryQueryKey, newerMapActivity, placedMapActivity, relevantMapActivity,
} = activity

function event(id, fields = {}) {
  return { id, principal_id: 'actor-new', action: 'memory.created', resource_id: 'memory-new', reason: null, created_at: '2026-11-02T00:00:00Z', ...fields }
}
function scope(overrides = {}) {
  return { endpoint: 'https://workspace.example', access: 'grant-a', space: 'space-a', reviewer: true, administrator: false, search: '', kind: '', creator: '', hours: 0, limit: 120, focus: '', ...overrides }
}
function view(place, page, overrides = {}) {
  return mapActivityView({
    reviewer: true, pending: false, error: false, page, pageRequest: { scopeKey: place.scopeKey, cursor: place.cursor },
    place, visibleMemoryIds: new Set(['memory-old']), ...overrides,
  })
}

test('one earlier page reaches a relevant event older than the first 40 without keeping that page', () => {
  const visible = new Set(['memory-old'])
  const first = Array.from({ length: MAP_ACTIVITY_PAGE_SIZE }, (_, index) => event('new-' + index))
  assert.equal(relevantMapActivity(first, visible).length, 0)
  const place = earlierMapActivity(initialMapActivity('scope'), 'cursor-2')
  assert.equal(place.cursor, 'cursor-2')
  assert.deepEqual(place.previous, [undefined])
  const older = event('old-1', { principal_id: 'actor-old', action: 'memory.reviewed', resource_id: 'memory-old', reason: 'Checked the source', created_at: '2026-10-01T00:00:00Z' })
  const opened = view(place, { items: [older, event('old-deleted', { action: 'memory.deleted', resource_id: 'memory-old' })], next_cursor: null })
  assert.equal(opened.kind, 'events')
  assert.deepEqual(opened.events.map(item => item.id), ['old-1'])
  assert.equal(opened.events[0].principal_id, 'actor-old')
  assert.equal(opened.events[0].resource_id, 'memory-old')
  assert.equal(opened.events[0].reason, 'Checked the source')
  assert.equal(opened.end, true)
  assert.equal(opened.canEarlier, false)
  assert.equal(newerMapActivity(place).cursor, undefined)
  const map = readFileSync(new URL('../src/workspace/MemoryMap.tsx', import.meta.url), 'utf8')
  assert.match(map, /client\.activity\(space, \{ limit: MAP_ACTIVITY_PAGE_SIZE/)
  assert.match(map, /identityName\(event\.principal_id\)/)
  assert.match(map, /Open memory & history/)
  assert.match(map, /memory\.evidence\.source_revision_id/)
  assert.doesNotMatch(map, /\/activity\?limit=40/)
})

test('an empty activity page keeps its cursor and a terminal page says there is no older page', () => {
  const latest = initialMapActivity('scope')
  const irrelevant = Array.from({ length: MAP_ACTIVITY_PAGE_SIZE }, (_, index) => event('skip-' + index, { action: 'journal.organized' }))
  const empty = view(latest, { items: irrelevant, next_cursor: 'cursor-2' })
  assert.equal(empty.kind, 'empty-page')
  assert.equal(empty.events.length, 0)
  assert.equal(empty.canEarlier, true)
  assert.equal(empty.canNewer, false)
  const ended = view(earlierMapActivity(latest, 'cursor-2'), { items: [], next_cursor: null })
  assert.equal(ended.kind, 'empty-end')
  assert.equal(ended.canEarlier, false)
  assert.equal(ended.end, true)
  assert.equal(ended.canNewer, true)
  const legacy = view(latest, { items: [event('old-1', { resource_id: 'memory-old', action: 'memory.created' })] })
  assert.equal(legacy.kind, 'legacy')
  assert.equal(legacy.canEarlier, false)
  assert.equal(legacy.events.length, 1)
})

test('a late page, lost access, another workspace, or a new map query cannot restore the previous activity page', () => {
  const key = mapActivityScopeKey(scope())
  const browsed = earlierMapActivity(initialMapActivity(key), 'cursor-2')
  const stale = mapActivityView({
    reviewer: true, pending: false, error: false,
    page: { items: [event('old-1', { principal_id: 'actor-old', resource_id: 'memory-old', action: 'memory.revised' })], next_cursor: null },
    pageRequest: { scopeKey: 'previous-scope', cursor: 'cursor-2' },
    place: initialMapActivity(key), visibleMemoryIds: new Set(['memory-old']),
  })
  assert.equal(stale.kind, 'loading')
  assert.equal(stale.events.length, 0)
  for (const next of [scope({ reviewer: false }), scope({ administrator: true }), scope({ access: 'grant-b' }), scope({ space: 'space-b' }), scope({ search: 'billing' })]) {
    const cleared = placedMapActivity(browsed, mapActivityScopeKey(next))
    assert.equal(cleared.cursor, undefined)
    assert.deepEqual(cleared.previous, [])
    assert.equal(cleared.truncated, false)
  }
  const closed = view(placedMapActivity(browsed, mapActivityScopeKey(scope({ reviewer: false }))), { items: [event('old-1', { resource_id: 'memory-old' })], next_cursor: 'cursor-3' }, { reviewer: false })
  assert.equal(closed.kind, 'closed')
  assert.equal(closed.events.length, 0)
  assert.equal(closed.canEarlier, false)
  assert.equal(latestMapActivity(browsed).cursor, undefined)
})

test('the newest activity page can refresh with the map, and earlier pages stay one bounded page', () => {
  assert.equal(mapActivityPoll(true, undefined), 20_000)
  assert.equal(mapActivityPoll(true, 'cursor-2'), false)
  assert.equal(mapActivityPoll(false, undefined), false)
  let place = initialMapActivity('scope')
  for (let index = 0; index < MAP_ACTIVITY_RETAINED_PAGES + 1; index += 1) place = earlierMapActivity(place, 'cursor-' + index)
  assert.equal(place.previous.length, MAP_ACTIVITY_RETAINED_PAGES - 1)
  assert.equal(mapActivityPositionCount(place), MAP_ACTIVITY_RETAINED_PAGES)
  assert.equal(place.truncated, true)
  assert.equal(place.cursor, 'cursor-' + MAP_ACTIVITY_RETAINED_PAGES)
  const kept = view(place, { items: [event('old-1', { resource_id: 'memory-old', action: 'memory.created', principal_id: 'actor-old' })], next_cursor: 'cursor-next' })
  assert.deepEqual(kept.events.map(item => item.id), ['old-1'])
  assert.equal(kept.canEarlier, true)
  assert.equal(kept.canLatest, true)
})

test('same-query refreshed memory sets keep the historical cursor and do not resume polling', () => {
  const current = mapActivityScopeKey(Object.assign(scope(), { memoryIds: ['memory-old', 'memory-new'] }))
  const refreshed = mapActivityScopeKey(Object.assign(scope(), { memoryIds: ['memory-added', 'memory-old'] }))
  assert.equal(current, refreshed)
  assert.equal(current.includes('memory-added'), false)
  const browsed = earlierMapActivity(initialMapActivity(current), 'cursor-2')
  const kept = placedMapActivity(browsed, refreshed)
  assert.equal(kept.cursor, 'cursor-2')
  assert.deepEqual(kept.previous, [undefined])
  assert.equal(kept.truncated, false)
  assert.equal(mapActivityPoll(true, kept.cursor), false)
  const shown = view(kept, {
    items: [
      event('shown', { resource_id: 'memory-old', action: 'memory.revised' }),
      event('hidden', { resource_id: 'memory-added', action: 'memory.created' }),
    ],
    next_cursor: 'cursor-3',
  })
  assert.deepEqual(shown.events.map(item => item.id), ['shown'])
  assert.equal(shown.canEarlier, true)
  assert.equal(shown.canNewer, true)
})

test('explicit query or access changes clear the historical cursor and resume polling', () => {
  const key = mapActivityScopeKey(scope())
  const browsed = earlierMapActivity(earlierMapActivity(initialMapActivity(key), 'cursor-2'), 'cursor-3')
  assert.equal(mapActivityPoll(true, browsed.cursor), false)
  for (const next of [
    scope({ endpoint: 'https://other.example' }),
    scope({ access: 'grant-b' }),
    scope({ space: 'space-b' }),
    scope({ reviewer: false }),
    scope({ administrator: true }),
    scope({ search: 'billing' }),
    scope({ kind: 'memory' }),
    scope({ creator: 'actor-old' }),
    scope({ hours: 24 }),
    scope({ limit: 60 }),
    scope({ focus: 'memory:old' }),
  ]) {
    const nextKey = mapActivityScopeKey(next)
    assert.notEqual(nextKey, key)
    const cleared = placedMapActivity(browsed, nextKey)
    assert.equal(cleared.cursor, undefined)
    assert.deepEqual(cleared.previous, [])
    assert.equal(cleared.truncated, false)
    assert.equal(mapActivityPoll(true, cleared.cursor), 20_000)
  }
  assert.equal(mapActivityScopeKey(scope({ search: 'billing', focus: 'memory:old' })).includes('billing'), true)
  assert.equal(mapActivityScopeKey(scope({ search: 'billing', focus: 'memory:old' })).includes('memory:old'), true)
})

test('directory names from a previous access are unavailable after that access is lost or replaced', () => {
  const prior = [{ id: 'actor-old', name: 'Ada Lovelace', kind: 'human' }]
  assert.equal(directoryNames(true, false, prior).get('actor-old').name, 'Ada Lovelace')
  assert.equal(directoryNames(false, false, prior).size, 0)
  assert.equal(directoryNames(true, true, prior).size, 0)
  assert.equal(directoryNames(true, false, undefined).size, 0)
  const current = mapDirectoryQueryKey('grant-a', 'https://workspace.example', 'space-a')
  const replaced = mapDirectoryQueryKey('grant-b', 'https://workspace.example', 'space-a')
  assert.deepEqual(current, ['map-identities', 'grant-a', 'https://workspace.example', 'space-a'])
  assert.notDeepEqual(current, replaced)
  assert.equal(JSON.stringify(current).includes('token'), false)
  const map = readFileSync(new URL('../src/workspace/MemoryMap.tsx', import.meta.url), 'utf8')
  const knowledge = readFileSync(new URL('../src/workspace/Knowledge.tsx', import.meta.url), 'utf8')
  const workspace = readFileSync(new URL('../src/workspace/Workspace.tsx', import.meta.url), 'utf8')
  assert.match(map, /mapDirectoryQueryKey\(sessionIdentity, client\.baseUrl, space\)/)
  assert.match(map, /directoryNames\(administrator, !!identities\.error, identities\.data\?\.items\)/)
  assert.match(map, /enabled: administrator/)
  assert.doesNotMatch(map, /accessGeneration|apiKey|sessionToken/)
  assert.match(knowledge, /sessionIdentity=\{sessionIdentity\}/)
  assert.match(workspace, /sessionIdentity=\{JSON\.stringify\(\[client\.baseUrl, me\.tenant_id, me\.principal_id, me\.administrator\]\)\}/)
})

test('retained activity positions include the open page and stop at the declared bound', () => {
  let place = initialMapActivity('scope')
  assert.equal(mapActivityPositionCount(place), 1)
  for (let index = 0; index < MAP_ACTIVITY_RETAINED_PAGES + 5; index += 1) {
    place = earlierMapActivity(place, 'cursor-' + index)
    assert.ok(mapActivityPositionCount(place) <= MAP_ACTIVITY_RETAINED_PAGES)
  }
  assert.equal(place.truncated, true)
  assert.equal(place.previous.length, MAP_ACTIVITY_RETAINED_PAGES - 1)
  assert.equal(mapActivityPositionCount(place), MAP_ACTIVITY_RETAINED_PAGES)
  assert.equal(place.cursor, 'cursor-' + (MAP_ACTIVITY_RETAINED_PAGES + 4))
  const open = view(place, { items: [event('old-1', { resource_id: 'memory-old', action: 'memory.created' })], next_cursor: 'cursor-more' })
  assert.equal(open.canLatest, true)
  assert.equal(open.canNewer, true)
  const home = latestMapActivity(place)
  assert.equal(home.cursor, undefined)
  assert.deepEqual(home.previous, [])
  assert.equal(home.truncated, false)
  assert.equal(mapActivityPoll(true, home.cursor), 20_000)
  const map = readFileSync(new URL('../src/workspace/MemoryMap.tsx', import.meta.url), 'utf8')
  const guide = readFileSync(new URL('../../../docs/service/memory-map.md', import.meta.url), 'utf8')
  assert.match(map, /including this page/)
  assert.match(guide, /including the page now open/)
})
