import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import test from 'node:test'
import { JOURNAL_CHUNK_BYTES, MnemionClient, journalChunk, journalTransportDigest, supportsJournalUploads, verifyJournalPrefix } from '../dist/index.js'

test('binary uploads verify the exact bounded prefix before resuming', async () => {
  const data = new TextEncoder().encode('mémoire 🌌 '.repeat(50000))
  const first = data.slice(0, JOURNAL_CHUNK_BYTES)
  const chunk = await journalChunk(first.buffer, 0)
  assert.deepEqual(Buffer.from(chunk.data, 'base64'), Buffer.from(first))
  assert.equal(chunk.sha256, createHash('sha256').update(first).digest('hex'))
  const header = Buffer.alloc(48)
  header.writeBigUInt64BE(BigInt(first.length), 40)
  const expected = createHash('sha256').update(header).update(createHash('sha256').update(first).digest()).digest('hex')
  assert.equal(await journalTransportDigest('0'.repeat(64), 0, first.buffer), expected)
  class BoundedBlob extends Blob {
    async arrayBuffer() { throw new Error('The complete file must never be loaded') }
    slice(start, end) { assert.ok(end - start <= JOURNAL_CHUNK_BYTES); return super.slice(start, end) }
  }
  const file = new BoundedBlob([data])
  const receipt = { index: 0, path: 'fixture', bytes: data.length, received: first.length, transport_sha256: expected, complete: false }
  assert.equal(await verifyJournalPrefix(file, receipt), true)
  data[42] ^= 1
  await assert.rejects(verifyJournalPrefix(new BoundedBlob([data]), receipt), /differs from the accepted/)
  assert.equal(await verifyJournalPrefix(file, receipt, () => true), false)
})

test('recovery operations use versioned steps and page through bounded receipts', async () => {
  const seen = []
  const client = new MnemionClient({ baseUrl: 'https://memory.example', apiKey: 'fixture-key', retries: 0,
    fetch: async (url, options) => { seen.push({ url, ...options }); return new Response(JSON.stringify({ id: 'upload', state: 'reviewed' }), { headers: { 'content-type': 'application/json' } }) },
  })
  await client.beginJournalUpload('space', { catalog: '{}', files: [], withdrawn_ids: [] }, 'same-attempt')
  await client.journalUploadFiles('space', 'upload', 128)
  await client.journalUploadDecisions('space', 'upload', 2)
  await client.advanceJournalUpload('space', 'upload', { expected_version: 7, action: 'review' })
  assert.equal(seen[0].headers['Idempotency-Key'], 'same-attempt')
  assert.ok(seen[1].url.endsWith('/files?cursor=128'))
  assert.ok(seen[2].url.endsWith('/decisions?cursor=2'))
  assert.deepEqual(JSON.parse(seen[3].body), { expected_version: 7, action: 'review' })
  assert.equal(supportsJournalUploads('4.28.99'), false)
  assert.equal(supportsJournalUploads('4.29.0'), true)
  assert.equal(supportsJournalUploads('5.0.0'), true)
  assert.equal(supportsJournalUploads('unknown'), false)
})
