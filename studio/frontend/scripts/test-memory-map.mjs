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
