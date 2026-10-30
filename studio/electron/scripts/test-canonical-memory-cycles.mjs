import assert from 'node:assert/strict'
import test from 'node:test'
import { canonicalMemoryCycles, canonicalRemainingBatches, canonicalTerminalMarker } from '../canonical-memory-cycles.mjs'

test('the canonical batches stay the existing checkpoint sizes', () => {
  assert.deepEqual(canonicalRemainingBatches(true), [[7, 8], [8, 16], [16, 32], [32, 64], [32, 96], [32, 128]])
  assert.deepEqual(canonicalRemainingBatches(false), [[31, 32], [96, 128]])
  const completed = [1, ...canonicalRemainingBatches(true).map(([, done]) => done)]
  assert.deepEqual(completed, [1, 8, 16, 32, 64, 96, 128])
})

test('one canonical cycle checks the real save, fetch and lexical recall', async () => {
  const calls = []
  globalThis.__mnemionMemoryProbe = {
    cycles: 0,
    latencies: [],
    client: {
      async save(space, memory) {
        calls.push(['save', space, memory.kind, memory.subject, memory.content.length])
        return { lexical_ready: true, memory_id: 'mem-1' }
      },
      async fetch(id) {
        calls.push(['fetch', id])
        return { memory_id: id, content: ('rendererprobe0 postgres backup billing procedure. ').repeat(20) }
      },
      async search(input) {
        calls.push(['search', input.mode, input.query, input.space_ids[0], input.limit])
        return { hits: [{ memory_id: 'mem-1' }] }
      },
    },
  }
  await canonicalMemoryCycles({ number: 1, space: 'space-1' })
  assert.deepEqual(calls, [
    ['save', 'space-1', 'procedure', 'PRIVATE_RENDERER_MEMORY_CANARY', ('rendererprobe0 postgres backup billing procedure. ').repeat(20).length],
    ['fetch', 'mem-1'],
    ['search', 'lexical', 'rendererprobe0', 'space-1', 5],
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
    client: {
      async save() { return { lexical_ready: true, memory_id: 'mem-1' } },
      async fetch() { return { content: ('rendererprobe0 postgres backup billing procedure. ').repeat(20) } },
      async search() { return { hits: [] } },
    },
  }
  await assert.rejects(() => canonicalMemoryCycles({ number: 1, space: 'space-1' }), /Real recall omitted/)
  assert.equal(globalThis.__mnemionMemoryProbe.cycles, 0)
})
