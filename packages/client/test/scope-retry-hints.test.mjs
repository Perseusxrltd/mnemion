import { test } from 'node:test'
import assert from 'node:assert/strict'
import { MnemionClient, MnemionError } from '../dist/index.js'

test('scope changes offer a fresh-search hint without replaying the request', async () => {
  let calls = 0
  const codes = ['scope_changed', 'generation_changed', 'version_conflict']
  const client = new MnemionClient({ baseUrl: 'https://example.invalid', apiKey: 'fixture-key', retries: 2,
    fetch: async () => {
      const code = codes[calls++]
      return Response.json({ error: { code, message: 'Refresh the search' } }, { status: 409 })
    },
  })
  for (const code of codes) {
    const before = calls
    await assert.rejects(client.search({ query: 'billing', all_accessible: true }), error =>
      error instanceof MnemionError && error.code === code && error.retryable === (code === 'scope_changed'))
    assert.equal(calls, before + 1)
  }
})
