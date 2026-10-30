import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import { canonicalLaunchPrefix, canonicalMemoryCycles, canonicalRemainingBatches, canonicalTerminalMarker } from '../canonical-memory-cycles.mjs'

const prefixA = 'a0123456789ab'
const prefixB = 'b0123456789cd'

const historicalCycle = ('rendererprobe0 postgres backup billing procedure. ').repeat(20)

test('the canonical batches stay the existing checkpoint sizes', () => {
  assert.deepEqual(canonicalRemainingBatches(true), [[7, 8], [8, 16], [16, 32], [32, 64], [32, 96], [32, 128]])
  assert.deepEqual(canonicalRemainingBatches(false), [[31, 32], [96, 128]])
  const completed = [1, ...canonicalRemainingBatches(true).map(([, done]) => done)]
  assert.deepEqual(completed, [1, 8, 16, 32, 64, 96, 128])
})

test('one canonical cycle checks the real save, fetch and lexical recall', async () => {
  const calls = []
  const prefix = prefixA
  globalThis.__mnemionMemoryProbe = {
    cycles: 0,
    latencies: [],
    queryPrefix: prefix,
    client: {
      async save(space, memory) {
        calls.push(['save', space, memory.kind, memory.subject, memory.content.length])
        return { lexical_ready: true, memory_id: 'mem-1' }
      },
      async fetch(id) {
        calls.push(['fetch', id])
        return { memory_id: id, content: (prefix + '0 postgres backup billing procedure. ').repeat(20) }
      },
      async search(input) {
        calls.push(['search', input.mode, input.query, input.space_ids[0], input.limit])
        return { hits: [{ memory_id: 'mem-1' }] }
      },
    },
  }
  await canonicalMemoryCycles({ number: 1, space: 'space-1' })
  assert.equal(prefix.length, 13)
  assert.deepEqual(calls, [
    ['save', 'space-1', 'procedure', 'PRIVATE_RENDERER_MEMORY_CANARY', historicalCycle.length],
    ['fetch', 'mem-1'],
    ['search', 'lexical', prefix + '0', 'space-1', 5],
  ])
  assert.equal(globalThis.__mnemionMemoryProbe.cycles, 1)
  assert.equal(globalThis.__mnemionMemoryProbe.latencies.length, 1)
})

test('a terminal marker keeps the verified count and marks unknown progress', () => {
  assert.deepEqual(canonicalTerminalMarker('finished', 128), { phase: 'finished', completed: 128, completed_known: true })
  assert.deepEqual(canonicalTerminalMarker('finished', 96), { phase: 'finished', completed: 96, completed_known: true })
  assert.deepEqual(canonicalTerminalMarker('failed', 40), { phase: 'failed', completed: 40, completed_known: true })
  assert.deepEqual(canonicalTerminalMarker('closed', undefined, false), { phase: 'closed', completed_known: false })
  assert.equal(Object.hasOwn(canonicalTerminalMarker('finished', undefined, false), 'completed'), false)
  assert.equal(canonicalTerminalMarker('failed', undefined, false).completed, undefined)
})

test('a failed recall is not counted as a completed cycle', async () => {
  globalThis.__mnemionMemoryProbe = {
    cycles: 0,
    latencies: [],
    queryPrefix: prefixA,
    client: {
      async save() { return { lexical_ready: true, memory_id: 'mem-1' } },
      async fetch() { return { content: (prefixA + '0 postgres backup billing procedure. ').repeat(20) } },
      async search() { return { hits: [{ memory_id: 'mem-other' }] } },
    },
  }
  await assert.rejects(() => canonicalMemoryCycles({ number: 1, space: 'space-1' }), /Real recall omitted/)
  assert.equal(globalThis.__mnemionMemoryProbe.cycles, 0)
})

test('distinct launches search only their own prefix and keep the same payload length', async () => {
  const notes = []
  let sequence = 0
  function client() {
    return {
      async save(space, memory) {
        const id = 'mem-' + (++sequence)
        notes.push({ id, space, query: memory.content.split(' ')[0], content: memory.content })
        return { lexical_ready: true, memory_id: id }
      },
      async fetch(id) {
        return { memory_id: id, content: notes.find(note => note.id === id).content }
      },
      async search(input) {
        return { hits: notes.filter(note => note.query === input.query).slice(0, input.limit).map(note => ({ memory_id: note.id })) }
      },
    }
  }
  async function launch(prefix) {
    globalThis.__mnemionMemoryProbe = { cycles: 0, latencies: [], queryPrefix: prefix, client: client() }
    await canonicalMemoryCycles({ number: 1, space: 'space-1' })
    return notes.find(note => note.query === prefix + '0')
  }
  const first = await launch(prefixA)
  const second = await launch(prefixB)
  assert.equal(first.content.length, historicalCycle.length)
  assert.equal(second.content.length, historicalCycle.length)
  assert.notEqual(first.id, second.id)
  assert.equal(notes.filter(note => note.query === prefixA + '0').length, 1)
  assert.equal(notes.filter(note => note.query === prefixB + '0').length, 1)
  globalThis.__mnemionMemoryProbe = {
    cycles: 0,
    latencies: [],
    queryPrefix: prefixB,
    client: {
      async save() { return { lexical_ready: true, memory_id: second.id } },
      async fetch() { return { content: second.content } },
      async search() { return { hits: [{ memory_id: first.id }] } },
    },
  }
  await assert.rejects(() => canonicalMemoryCycles({ number: 1, space: 'space-1' }), /Real recall omitted/)
  assert.equal(globalThis.__mnemionMemoryProbe.cycles, 0)
})

test('both resource callers install one launch prefix before measurement', () => {
  const installed = readFileSync(new URL('../native-telemetry-resource-probe.ts', import.meta.url), 'utf8')
  const compiled = readFileSync(new URL('./probe-telemetry-renderer.mjs', import.meta.url), 'utf8')
  for (const source of [installed, compiled]) {
    assert.equal(source.includes('canonicalLaunchPrefix()'), true)
    assert.equal(source.includes('queryPrefix'), true)
    assert.equal(source.includes("'rendererprobe'"), false)
  }
  const prefix = canonicalLaunchPrefix()
  assert.equal(prefix.length, 13)
  assert.match(prefix, /^[a-z][a-f0-9]{12}$/)
  assert.notEqual(prefix, canonicalLaunchPrefix())
  const embedded = canonicalMemoryCycles.toString()
  assert.equal(embedded.includes('LAUNCH_QUERY_PREFIX'), false)
  assert.equal(embedded.includes('queryPrefix'), true)
  assert.equal(embedded.includes("query = prefix + probe.cycles"), true)
  assert.equal(embedded.includes('limit: 5'), true)
})

test('the serialized cycle runs in a fresh vm without a module prefix binding', async () => {
  const content = (prefixA + '0 postgres backup billing procedure. ').repeat(20)
  const sandbox = vm.createContext({ performance })
  const cycle = vm.runInContext(`(${canonicalMemoryCycles.toString()})`, sandbox)
  const calls = []
  sandbox.__mnemionMemoryProbe = {
    cycles: 0,
    latencies: [],
    queryPrefix: prefixA,
    client: {
      async save(space, memory) {
        calls.push(['save', space, memory.content, memory.kind, memory.subject])
        return { lexical_ready: true, memory_id: 'mem-vm' }
      },
      async fetch(id) {
        calls.push(['fetch', id])
        return { memory_id: id, content }
      },
      async search(input) {
        calls.push(['search', input.mode, input.query, input.space_ids[0], input.limit])
        return { hits: [{ memory_id: 'mem-vm' }] }
      },
    },
  }
  assert.equal(sandbox.LAUNCH_QUERY_PREFIX, undefined)
  await cycle({ number: 1, space: 'space-vm' })
  assert.deepEqual(calls, [
    ['save', 'space-vm', content, 'procedure', 'PRIVATE_RENDERER_MEMORY_CANARY'],
    ['fetch', 'mem-vm'],
    ['search', 'lexical', prefixA + '0', 'space-vm', 5],
  ])
  assert.equal(content.length, historicalCycle.length)
  assert.equal(sandbox.__mnemionMemoryProbe.cycles, 1)
  assert.equal(sandbox.__mnemionMemoryProbe.latencies.length, 1)
})
