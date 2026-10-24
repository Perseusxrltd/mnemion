import assert from 'node:assert/strict'
import test from 'node:test'
import { randomUUID, randomBytes } from 'node:crypto'
import { connect } from 'node:net'
import { mkdtemp, readFile, realpath, rm } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { tmpdir } from 'node:os'
import { spawn } from 'node:child_process'
import { DesktopOperator } from '../dist/desktop-operator.js'
import { desktopAction } from '../dist/desktop-actions.js'
import { measureDesktop } from '../dist/desktop-measurement.js'
import { TelemetryCatalog } from '../dist/telemetry-catalog.js'

const python = process.env.MNEMION_OPERATOR_PYTHON || process.env.MNEMION_BUILD_PYTHON || (process.platform === 'win32' ? 'python' : 'python3')
const root = resolve(import.meta.dirname, '../../..')
function child(args, input) {
  return new Promise((resolve, reject) => {
    const process = spawn(python, args, { cwd: root, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true })
    let output = '', failed = false
    const timer = setTimeout(() => { failed = true; process.kill(); reject(new Error('Private operator client timed out')) }, 20000)
    process.stdout.on('data', bytes => { output += bytes.toString(); if (output.length > 300000) { failed = true; process.kill(); reject(new Error('Private operator output exceeded its limit')) } })
    process.stderr.resume()
    process.stdin.on('error', () => {})
    process.once('error', reject)
    process.once('close', code => { clearTimeout(timer); if (!failed) resolve({ code, output }) })
    process.stdin.end(JSON.stringify(input))
  })
}
async function fixture(t, execute = async request => ({ action: request.action })) {
  const directory = await mkdtemp(join(await realpath(tmpdir()), 'mnemion-operator-test-'))
  const control = join(directory, 'mnemion-desktop-control')
  let endpoint
  const server = new DesktopOperator({ directory: control, version: '4.5.0', execute, publish: async value => {
    const result = await child(['-c', 'import json,sys; from mnemion.desktop_operator import publish_request; print(json.dumps(publish_request(sys.stdin.buffer.read(16385))))'], value)
    assert.equal(result.code, 0, 'The native private endpoint writer must succeed')
    assert.equal(JSON.parse(result.output).protected, true)
    endpoint = value.endpoint
  } })
  await server.start()
  t.after(async () => { await server.close(); await rm(directory, { recursive: true, force: true }) })
  const request = (overrides = {}) => ({ protocol: 1, session_id: endpoint.session_id, credential: endpoint.credential,
    request_id: randomUUID(), action: 'status', input: {}, ...overrides })
  return { server, directory, control, endpoint, request }
}
function send(address, value, change = bytes => bytes) {
  const body = Buffer.from(JSON.stringify(value)), header = Buffer.alloc(4)
  header.writeUInt32BE(body.length)
  return new Promise((resolve, reject) => {
    const socket = connect(address)
    let response = Buffer.alloc(0)
    const timer = setTimeout(() => { socket.destroy(); reject(new Error('Operator pipe response timed out')) }, 10000)
    socket.once('connect', () => socket.write(change(Buffer.concat([header, body]))))
    socket.on('data', bytes => { response = Buffer.concat([response, bytes]) })
    socket.on('error', () => {})
    socket.once('close', () => {
      clearTimeout(timer)
      try { resolve(response.length ? JSON.parse(response.subarray(4).toString()) : null) } catch (error) { reject(error) }
    })
  })
}

test('the actual Python client reads the private endpoint and exchanges framed requests', async t => {
  const f = await fixture(t, async request => ({ action: request.action, unicode: 'Équipe' }))
  const result = await child(['-m', 'mnemion.desktop_operator', '--control-directory', f.control, '--timeout', '10'], { action: 'status' })
  assert.equal(result.code, 0)
  const reply = JSON.parse(result.output)
  assert.equal(reply.ok, true)
  assert.equal(reply.result.unicode, 'Équipe')
  assert.ok(!result.output.includes(f.endpoint.credential))
  assert.equal(f.server.ready, true)
})

test('wrong credentials, wrong sessions, oversized frames and trailing requests cannot invoke a controller', async t => {
  let calls = 0
  const f = await fixture(t, async () => { ++calls; return true })
  assert.equal(await send(f.endpoint.address, f.request({ credential: randomBytes(32).toString('hex') })), null)
  assert.equal(await send(f.endpoint.address, f.request({ session_id: randomUUID() })), null)
  assert.equal(await send(f.endpoint.address, f.request(), bytes => { bytes.writeUInt32BE(16385); return bytes }), null)
  assert.equal(await send(f.endpoint.address, f.request(), bytes => Buffer.concat([bytes, Buffer.from('extra')])), null)
  assert.equal(calls, 0)
})

test('same request IDs replay a completed mutation but cannot change its input', async t => {
  let calls = 0
  const values = []
  const store = { available: true, catalog: new TelemetryCatalog(JSON.parse(await readFile(new URL('../dist/telemetry-catalog.json', import.meta.url), 'utf8'))),
    async snapshot() { return { revision: 1, store_generation: 'a'.repeat(32) } },
    async recordMany(observations) { values.push(...observations); return true },
  }
  const f = await fixture(t, request => measureDesktop(store, request.action, request.input, 'native_agent', async () => ({ calls: ++calls })))
  const request = f.request({ action: 'backup.configure', input: { enabled: false } })
  const first = await send(f.endpoint.address, request)
  assert.deepEqual(await send(f.endpoint.address, request), first)
  assert.equal((await send(f.endpoint.address, { ...request, input: { enabled: true } })).error, 'request_changed')
  assert.equal(calls, 1)
  assert.equal(values.length, 2, 'the cached reply did not emit another submission or outcome')
  assert.ok(values.every(value => value.workflow === 'backup.configure' && value.surface === 'native_agent'))
})

test('an in-flight request is not started twice and disconnect aborts its owned work', async t => {
  let entered, observed, calls = 0
  const inside = new Promise(resolve => { entered = resolve })
  const cancelled = new Promise(resolve => { observed = resolve })
  const f = await fixture(t, async (_request, signal) => {
    ++calls; entered()
    await new Promise(resolve => signal.addEventListener('abort', () => { observed(); resolve() }, { once: true }))
    throw new Error('Cancelled')
  })
  const request = f.request({ action: 'backup.run' }), bytes = Buffer.from(JSON.stringify(request)), header = Buffer.alloc(4)
  header.writeUInt32BE(bytes.length)
  const socket = connect(f.endpoint.address)
  socket.on('error', () => {})
  socket.once('connect', () => socket.write(Buffer.concat([header, bytes])))
  await inside
  assert.equal((await send(f.endpoint.address, request)).error, 'request_in_progress')
  socket.destroy()
  await cancelled
  assert.equal(calls, 1)
})

for (const action of ['backup.key', 'local.vault-key']) test(`${action} requires a private result destination reserved before any request`, async t => {
  const key = (action === 'backup.key' ? 'mnm_bk_' : 'mnv_') + randomBytes(32).toString('base64url')
  let calls = 0
  const f = await fixture(t, async () => { ++calls; return { recovery_key: key } })
  const request = { action }
  const refused = await child(['-m', 'mnemion.desktop_operator', '--control-directory', f.control], request)
  assert.equal(refused.code, 1); assert.equal(calls, 0)
  const file = join(f.directory, 'private-recovery-key.json')
  const saved = await child(['-m', 'mnemion.desktop_operator', '--control-directory', f.control, '--result-file', file], request)
  assert.equal(saved.code, 0); assert.equal(calls, 1)
  assert.ok(!saved.output.includes(key))
  assert.equal(JSON.parse(await readFile(file, 'utf8')).result.recovery_key, key)
  const duplicate = await child(['-m', 'mnemion.desktop_operator', '--control-directory', f.control, '--result-file', file], request)
  assert.equal(duplicate.code, 1); assert.equal(calls, 1)
})

test('private failures redact even long secret values and oversized results remain bounded', async t => {
  const secret = randomBytes(1800).toString('hex')
  const f = await fixture(t, async request => {
    if (request.action === 'status') throw new Error('Provider rejected ' + request.input.ngrok_authtoken)
    return { text: 'x'.repeat(262144) }
  })
  const failed = await send(f.endpoint.address, f.request({ input: { ngrok_authtoken: secret } }))
  assert.equal(failed.ok, false)
  assert.equal(failed.message, 'Provider rejected [private]')
  assert.ok(!JSON.stringify(failed).includes(secret.slice(0, 32)))
  assert.equal((await send(f.endpoint.address, f.request({ action: 'backup.status' }))).error, 'response_limit')
})

test('private connection failures redact nested login, invitation and key inputs', async t => {
  const key = 'mnm_' + randomBytes(32).toString('base64url')
  const password = 'A private password ' + randomBytes(32).toString('base64url')
  const invitation = 'mnm_i_' + randomBytes(32).toString('base64url')
  const f = await fixture(t, async request => {
    const input = request.input
    throw new Error([input.credential, input.credentials.password, input.credentials.invitation].join(' '))
  })
  const result = await send(f.endpoint.address, f.request({ action: 'workspace.sign-in',
    input: { credential: key, credentials: { password, invitation } } }))
  assert.equal(result.ok, false)
  assert.equal(result.message, '[private] [private] [private]')
})

test('a second live desktop cannot overwrite discovery and closing removes the stale endpoint', async t => {
  const f = await fixture(t)
  const duplicate = await child(['-c', 'import json,sys; from mnemion.desktop_operator import publish_request; print(json.dumps(publish_request(sys.stdin.buffer.read(16385))))'], { directory: f.control, endpoint: f.endpoint })
  assert.notEqual(duplicate.code, 0)
  assert.equal(JSON.parse(await readFile(join(f.control, 'endpoint.json'), 'utf8')).session_id, f.endpoint.session_id)
  await f.server.close()
  await assert.rejects(readFile(join(f.control, 'endpoint.json')), { code: 'ENOENT' })
})

test('the operator catalog rejects arbitrary methods and unreviewed arguments', () => {
  assert.throws(() => desktopAction('__proto__', {}), /catalog/)
  assert.throws(() => desktopAction('service.request', {}), /catalog/)
  assert.throws(() => desktopAction('backup.configure', { administrator_key: 'not-a-host-credential' }), /unsupported/)
  assert.equal(desktopAction('backup.cancel', {}).mutation, false)
  assert.equal(desktopAction('backup.configure', {}).workspace, true)
})
