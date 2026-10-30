/** The existing 128 real save/fetch/search cycles. Not a new benchmark. */

export async function canonicalMemoryCycles({ number, space }) {
  const probe = globalThis.__mnemionMemoryProbe
  if (!probe?.client || !Number.isInteger(number) || number < 1 || number > 128 || typeof space !== 'string') {
    throw new Error('Canonical memory cycles require the real client')
  }
  for (let index = 0; index < number; index++) {
    const start = performance.now(), query = 'rendererprobe' + probe.cycles
    const content = (query + ' postgres backup billing procedure. ').repeat(20)
    const saved = await probe.client.save(space, { content, subject: 'PRIVATE_RENDERER_MEMORY_CANARY', kind: 'procedure' })
    if (!saved.lexical_ready || !saved.memory_id) throw new Error('Real save failed')
    const fetched = await probe.client.fetch(saved.memory_id)
    if (fetched.content !== content) throw new Error('Real fetch changed content')
    const recalled = await probe.client.search({ query, space_ids: [space], mode: 'lexical', limit: 5 })
    if (!recalled.hits.some(hit => hit.memory_id === saved.memory_id)) throw new Error('Real recall omitted the saved memory')
    probe.cycles++
    probe.latencies.push(performance.now() - start)
  }
}

/** Comparison and attribution keep the long checkpoints. The short pair is the other journey. */
export function canonicalRemainingBatches(comparison) {
  return comparison ? [[7, 8], [8, 16], [16, 32], [32, 64], [32, 96], [32, 128]] : [[31, 32], [96, 128]]
}

/** The verified total already stored on the probe. Unknown progress is explicit, never invented. */
export function canonicalTerminalMarker(phase, completed, known = true) {
  if (phase !== 'finished' && phase !== 'closed' && phase !== 'failed') {
    throw new Error('Terminal marker required')
  }
  const bounded = Number.isInteger(completed) && completed >= 0 && completed <= 128
  if (known === false) {
    return bounded ? { phase, completed, completed_known: false } : { phase, completed_known: false }
  }
  if (!bounded) return { phase, completed_known: false }
  return { phase, completed, completed_known: true }
}

/** Lower bound stays. The current total is unknown while a batch is still running. */
export function resourceProgress(state, event) {
  const previous = state && Number.isInteger(state.verified) && state.verified >= 0 && state.verified <= 128
    ? state.verified
    : undefined
  if (event === 'inflight') return { verified: previous, progressKnown: false }
  const settled = event && event.settled
  if (Number.isInteger(settled) && settled >= 0 && settled <= 128) {
    return { verified: settled, progressKnown: true }
  }
  return { verified: previous, progressKnown: false }
}
