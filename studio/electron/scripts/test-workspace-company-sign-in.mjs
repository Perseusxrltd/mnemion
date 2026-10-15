import assert from 'node:assert/strict'
import { randomBytes, randomUUID } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { request as httpRequest } from 'node:http'
import { test } from 'node:test'
import { WorkspaceCompanyAuth } from '../dist/workspace-company-auth.js'
import { WorkspacePasswordAuth } from '../dist/workspace-auth.js'
import { WorkspaceConnections } from '../dist/workspace-connections.js'
import { WorkspaceStore } from '../dist/workspace-store.js'
import { workspaceFixture } from './workspace-fixture.mjs'

const endpoint = 'https://memory.example.test', api = new URL(endpoint + '/v1/me')
const secret = prefix => prefix + randomBytes(32).toString('base64url')
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }
function callback(address, headers = {}) {
  return new Promise((resolve, reject) => {
    const request = httpRequest(address, { headers }, response => {
      let body = ''; response.setEncoding('utf8'); response.on('data', chunk => { body += chunk })
      response.on('end', () => resolve({ status: response.statusCode, headers: response.headers, body }))
    })
    request.on('error', reject); request.end()
  })
}
async function setup(t) {
  const f = await workspaceFixture(t), sessionId = randomUUID()
  const provider = { id: 'company', name: 'Company account', issuer: 'https://identity.example.test', session_seconds: 28800 }
  const flow = { state: secret('mnm_o_'), code_verifier: secret(''), expires_in: 300, provider }
  flow.authorization_url = provider.issuer + '/authorize?state=' + flow.state
  const expires = new Date(Date.now() + provider.session_seconds * 1000).toISOString()
  const server = { current: null, refreshes: 0, finishes: 0, signouts: 0, opens: 0, callback: '', startGate: null, finishGate: null,
    started: deferred(), finishing: deferred(), responseOverride: {}, browser: null }
  const issue = seconds => ({ session_id: sessionId, tenant_id: f.identity.tenant_id, principal_id: f.identity.principal_id,
    access_token: secret('mnm_s_'), refresh_token: secret('mnm_r_'), csrf_token: null,
    access_expires_at: new Date(Date.now() + seconds * 1000).toISOString(), expires_at: expires,
    persistence: 'native', authentication: 'company' })
  const request = async (address, operation, input) => {
    assert.equal(address, endpoint)
    if (operation === 'company/configuration') return { providers: [provider], callback_uri: endpoint + '/company/callback' }
    if (operation === 'company/start') {
      assert.equal(input.workspace_id, f.identity.tenant_id); assert.equal(input.transport, 'native')
      assert.equal(input.provider_id, provider.id)
      assert.match(input.callback_uri, /^http:\/\/127\.0\.0\.1:\d+\/mnemion-company\/[A-Za-z0-9_-]{43}$/)
      server.callback = input.callback_uri; server.started.resolve()
      if (server.startGate) await server.startGate.promise
      return flow
    }
    if (operation === 'company/finish') {
      server.finishes++; server.finishing.resolve()
      assert.equal(input.state, flow.state); assert.equal(input.code_verifier, flow.code_verifier)
      assert.equal(input.code, 'provider-code'); assert.equal(input.transport, 'native')
      if (server.finishGate) await server.finishGate.promise
      return server.current = issue(30)
    }
    if (operation === 'logout') { server.signouts++; assert.equal(input.refresh_token, server.current.refresh_token); return { signed_out: true } }
    assert.equal(operation, 'refresh'); server.refreshes++
    assert.equal(input.refresh_token, server.current.refresh_token)
    return server.current = { ...issue(900), ...server.responseOverride }
  }
  const company = new WorkspaceCompanyAuth(request, async address => {
    server.opens++; assert.equal(address, flow.authorization_url)
    if (server.browser) return server.browser()
    const answer = await callback(server.callback + '?state=' + flow.state + '&code=provider-code')
    assert.equal(answer.status, 200); assert.equal(answer.headers['cache-control'], 'no-store')
    assert.ok(!answer.body.includes(flow.state)); assert.ok(!answer.body.includes('provider-code'))
  })
  const password = new WorkspacePasswordAuth(request)
  const verify = async (address, credential) => {
    assert.equal(address, endpoint); assert.equal(credential, server.current.access_token); return f.identity
  }
  const broker = new WorkspaceConnections(f.store, verify, password, undefined, undefined, undefined, company)
  t.after(() => broker.lock())
  const input = { workspace_id: f.identity.tenant_id, provider_id: provider.id, device_name: 'Company test device' }
  return { ...f, server, flow, company, password, verify, broker, input, open: () => broker.companySignIn(endpoint, input, true) }
}

test('native company login uses a real temporary receiver, protected storage and a refresh after restart', async t => {
  const f = await setup(t)
  assert.equal((await f.broker.companyConfiguration(endpoint, f.identity.tenant_id)).providers[0].id, 'company')
  const session = await f.open()
  assert.equal(session.authentication, 'company')
  const visible = JSON.stringify([session, await f.broker.status(), await f.broker.inspect(session.bookmarkId)])
  const stored = await readFile(f.path, 'utf8')
  for (const value of [f.flow.code_verifier, f.server.current.access_token, f.server.current.refresh_token, 'provider-code']) {
    assert.ok(!visible.includes(value)); assert.ok(!stored.includes(value))
  }
  const saved = await f.store.credential(session.bookmarkId)
  assert.equal(saved.credential, f.server.current.refresh_token); assert.equal(saved.session.authentication, 'company')
  await assert.rejects(callback(f.server.callback), { code: 'ECONNREFUSED' })
  f.broker.lock()
  const reopened = new WorkspaceConnections(new WorkspaceStore(f.directory, f.cipher), f.verify, f.password)
  const restored = await reopened.resume()
  assert.equal(restored.authentication, 'company'); assert.equal(f.server.refreshes, 1)
  assert.notEqual(restored.sessionToken, session.sessionToken)
  assert.equal(await reopened.authorization(api, 'Bearer ' + restored.sessionToken), 'Bearer ' + f.server.current.access_token)
  await reopened.disconnect()
  assert.equal(f.server.signouts, 1)
})

test('the receiver rejects foreign origins, hosts, state and duplicate codes before accepting the pinned callback', async t => {
  const f = await setup(t)
  f.server.browser = async () => {
    const valid = f.server.callback + '?state=' + f.flow.state + '&code=provider-code'
    for (const [url, headers] of [
      [valid, { Origin: 'https://foreign.example.test' }], [valid, { Host: 'foreign.example.test' }],
      [valid.replace(f.flow.state, secret('mnm_o_')), {}], [valid + '&code=second', {}],
      [valid + '&state=' + f.flow.state, {}], [valid.replace('/mnemion-company/', '/wrong/'), {}],
    ]) assert.equal((await callback(url, headers)).status, 400)
    assert.equal(f.server.finishes, 0)
    assert.equal((await callback(valid)).status, 200)
  }
  await f.open(); assert.equal(f.server.finishes, 1)
})

test('cancel during the start request closes the receiver and prevents opening a browser or saving a login', async t => {
  const f = await setup(t); f.server.startGate = deferred()
  const opening = f.open(), rejected = assert.rejects(opening, /cancelled/)
  await f.server.started.promise; f.broker.cancelCompanySignIn(); f.server.startGate.resolve()
  await rejected
  assert.equal(f.server.opens, 0); assert.equal(f.server.finishes, 0)
  assert.equal((await f.broker.status()).active, null); assert.equal((await f.broker.status()).bookmarks.length, 0)
  await assert.rejects(callback(f.server.callback), { code: 'ECONNREFUSED' })
})

test('cancel during token exchange signs out the late-issued session without storing it', async t => {
  const f = await setup(t); f.server.finishGate = deferred()
  const opening = f.open(), rejected = assert.rejects(opening, /cancelled/)
  await f.server.finishing.promise; f.broker.cancelCompanySignIn(); f.server.finishGate.resolve()
  await rejected
  assert.equal(f.server.signouts, 1); assert.equal((await f.broker.status()).active, null)
  assert.equal((await f.broker.status()).bookmarks.length, 0)
})

test('a provider decline closes the receiver and leaves no device session', async t => {
  const f = await setup(t)
  f.server.browser = () => callback(f.server.callback + '?state=' + f.flow.state + '&error=access_denied')
  await assert.rejects(f.open(), /cancelled or declined/)
  assert.equal(f.server.finishes, 0); assert.equal((await f.broker.status()).bookmarks.length, 0)
  await assert.rejects(callback(f.server.callback), { code: 'ECONNREFUSED' })
})

test('a company refresh cannot silently replace its authentication method', async t => {
  const f = await setup(t), session = await f.open()
  f.server.responseOverride = { authentication: 'password' }
  await assert.rejects(f.broker.authorization(api, 'Bearer ' + session.sessionToken), /saved account/)
  assert.equal(f.server.refreshes, 1); assert.equal((await f.broker.status()).active, null)
  assert.equal((await f.store.credential(session.bookmarkId)).session.refreshPending, true)
})
