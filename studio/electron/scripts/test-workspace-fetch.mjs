import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { once } from 'node:events'
import test from 'node:test'
import { workspaceFetch } from '../dist/workspace-fetch.js'

test('a protected gateway returns API responses and enforces current authorization', async t => {
  const credential = 'fixture-workspace-key'
  let revoked = false
  let forwarded = 0
  const observed = []
  const server = createServer(async (request, response) => {
    observed.push({ method: request.method, path: request.url, accept: request.headers.accept })
    if (request.url === '/redirected') { forwarded++; response.end(); return }
    if (request.url === '/redirect') {
      response.writeHead(302, { Location: '/redirected' }); response.end(); return
    }
    if (!request.headers['ngrok-skip-browser-warning']) {
      response.writeHead(200, { 'Content-Type': 'text/html' }); response.end('<p>Browser warning</p>'); return
    }
    if (request.headers.authorization !== 'Bearer ' + credential || revoked) {
      response.writeHead(401); response.end(); return
    }
    if (request.method === 'POST') {
      let body = ''
      for await (const chunk of request) body += chunk
      assert.equal(body, '{"query":"fixture"}')
      assert.equal(request.headers['idempotency-key'], 'fixture-request')
    }
    response.writeHead(200, { 'Content-Type': 'application/json' })
    response.end('{"authorized":true}')
  })
  server.listen(0, '127.0.0.1')
  await once(server, 'listening')
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections() }))
  const endpoint = 'http://127.0.0.1:' + server.address().port
  const headers = new Headers({ Authorization: 'Bearer ' + credential, Accept: 'application/json' })
  const options = { headers, signal: AbortSignal.timeout(5000) }
  const interstitial = await fetch(endpoint + '/v1/me', options)
  assert.equal(interstitial.headers.get('content-type'), 'text/html')
  await interstitial.text()
  const authorized = await workspaceFetch(fetch, endpoint + '/v1/me', options)
  assert.deepEqual(await authorized.json(), { authorized: true })
  assert.equal(headers.has('ngrok-skip-browser-warning'), false, 'do not mutate caller headers')
  const result = await workspaceFetch(fetch, endpoint + '/v1/recall', {
    ...options, method: 'POST', body: '{"query":"fixture"}',
    headers: { ...Object.fromEntries(headers), 'Content-Type': 'application/json', 'Idempotency-Key': 'fixture-request' },
  })
  assert.equal(result.status, 200)
  await result.json()
  assert.deepEqual(observed.at(-1), { method: 'POST', path: '/v1/recall', accept: 'application/json' })
  revoked = true
  const rejected = await workspaceFetch(fetch, endpoint + '/v1/me', options)
  assert.equal(rejected.status, 401)
  await rejected.text()
  await assert.rejects(workspaceFetch(fetch, endpoint + '/redirect', { ...options, redirect: 'follow' }))
  assert.equal(forwarded, 0, 'credentials must never follow a redirect')
})

test('native requests recover only after a confirmed session rotation', async () => {
  const requests = []
  const original = new Headers({ Authorization: 'Bearer original' })
  const response = await workspaceFetch(async (_, options) => {
    requests.push({ authorization: options.headers.get('authorization'), body: options.body,
      cache: options.cache, redirect: options.redirect, credentials: options.credentials })
    return requests.length === 1 ? new Response('', { status: 401 }) : Response.json({ hits: [] })
  }, 'https://example.invalid/team/v1/recall', { method: 'POST', headers: original, body: '{"query":"memory"}' },
  async () => 'Bearer rotated')
  assert.equal(response.status, 200)
  assert.deepEqual(requests.map(item => item.authorization), ['Bearer original', 'Bearer rotated'])
  assert.ok(requests.every(item => item.body === '{"query":"memory"}' && item.cache === 'no-store' && item.redirect === 'error' && item.credentials === 'omit'))
  assert.equal(original.get('authorization'), 'Bearer original')
})

test('native revocation, unsafe writes and repeated rejection never loop', async () => {
  for (const mode of ['unchanged', 'write', 'repeated-rejection', 'forbidden']) {
    let calls = 0, acquisitions = 0
    const response = await workspaceFetch(async () => {
      calls++; return new Response('', { status: mode === 'forbidden' ? 403 : 401 })
    }, 'https://example.invalid/v1/principals', { method: mode === 'write' ? 'POST' : 'GET',
      headers: { Authorization: 'Bearer original' } }, async () => {
      acquisitions++; return mode === 'unchanged' ? 'Bearer original' : 'Bearer rotated'
    })
    assert.equal(response.status, mode === 'forbidden' ? 403 : 401)
    assert.equal(calls, mode === 'repeated-rejection' ? 2 : 1, mode)
    assert.equal(acquisitions, ['write', 'forbidden'].includes(mode) ? 0 : 1, mode)
  }
})

test('a stalled native rotation observation cannot outlive the request deadline', async () => {
  const abort = new AbortController()
  let calls = 0
  const pending = workspaceFetch(async () => { calls++; return new Response('', { status: 401 }) },
    'https://example.invalid/v1/me', { headers: { Authorization: 'Bearer original' }, signal: abort.signal },
    () => new Promise(() => {}))
  const timer = setTimeout(() => abort.abort(new Error('Request ended')), 20)
  try { await assert.rejects(pending, /Request ended/) } finally { clearTimeout(timer) }
  assert.equal(calls, 1)
})
