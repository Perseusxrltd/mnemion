/** The existing 128 real save/fetch/search cycles. Not a new benchmark. */

import { randomUUID } from 'node:crypto'
import { closeSync, constants, lstatSync, mkdirSync, openSync, renameSync, rmSync, writeSync } from 'node:fs'
import { join } from 'node:path'

/** One synthetic prefix per launch, created before measurement. Not a saved identity. */
export function canonicalLaunchPrefix() {
  const hex = randomUUID().replaceAll('-', '')
  const launchQueryPrefix = /^[a-z][a-f0-9]{12}$/
  const prefix = 'abcdef'[Number.parseInt(hex[0], 16) % 6] + hex.slice(1, 13)
  if (!launchQueryPrefix.test(prefix)) throw new Error('Canonical launch prefix unavailable')
  return prefix
}

const PROGRESS_SNAPSHOTS = 64
const PROGRESS_RECORD_BYTES = 1024

/** Host-only publisher. The serialized cycle function does not call this. */
export function canonicalProgressWriter(directory) {
  if (typeof directory !== 'string' || directory.length === 0) throw new Error('Progress directory required')
  try {
    mkdirSync(directory)
  } catch (error) {
    if (error?.code === 'EEXIST') throw new Error('Progress snapshot name already used')
    throw new Error('Progress snapshot failed')
  }
  let sequence = 0
  return function publish(record) {
    if (sequence >= PROGRESS_SNAPSHOTS) throw new Error('Progress snapshot capacity exceeded')
    if (record === null || typeof record !== 'object' || Array.isArray(record)) {
      throw new Error('Progress record invalid')
    }
    let body
    try {
      body = JSON.stringify(record)
    } catch {
      throw new Error('Progress record invalid')
    }
    if (typeof body !== 'string' || Buffer.byteLength(body) > PROGRESS_RECORD_BYTES) {
      throw new Error('Progress record oversized')
    }
    const next = sequence + 1
    const name = String(next).padStart(2, '0') + '.json'
    const dest = join(directory, name)
    const temp = `${dest}.tmp`
    let fd
    let owned = false
    try {
      fd = openSync(temp, constants.O_CREAT | constants.O_EXCL | constants.O_WRONLY)
      owned = true
      const bytes = Buffer.from(body)
      let offset = 0
      while (offset < bytes.length) {
        const wrote = writeSync(fd, bytes, offset, bytes.length - offset)
        if (!Number.isInteger(wrote) || wrote < 1) throw new Error('Progress snapshot failed')
        offset += wrote
      }
      closeSync(fd)
      fd = undefined
      // Node rename replaces an existing path. A new snapshot must not.
      let taken = true
      try {
        lstatSync(dest)
      } catch (error) {
        if (error?.code === 'ENOENT') taken = false
        else throw error
      }
      if (taken) throw new Error('Progress snapshot name already used')
      renameSync(temp, dest)
      sequence = next
    } catch (error) {
      if (fd !== undefined) {
        try { closeSync(fd) } catch { /* The owned temp is removed next. */ }
      }
      if (owned) {
        try { rmSync(temp, { force: true }) } catch { /* Only the temp this call created. */ }
      }
      if (error instanceof Error && error.message === 'Progress snapshot name already used') throw error
      if (error && error.code === 'EEXIST') throw new Error('Progress snapshot name already used')
      throw new Error('Progress snapshot failed')
    }
  }
}

export async function canonicalMemoryCycles({ number, space }) {
  const launchQueryPrefix = /^[a-z][a-f0-9]{12}$/
  const probe = globalThis.__mnemionMemoryProbe
  const prefix = probe?.queryPrefix
  if (!probe?.client || !Number.isInteger(number) || number < 1 || number > 128 || typeof space !== 'string'
      || typeof prefix !== 'string' || !launchQueryPrefix.test(prefix)) {
    throw new Error('Canonical memory cycles require the real client')
  }
  for (let index = 0; index < number; index++) {
    const start = performance.now(), query = prefix + probe.cycles
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
