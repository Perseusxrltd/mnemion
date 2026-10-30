import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer as tcpServer } from 'node:net'
import { createServer, getCACertificates, setDefaultCACertificates } from 'node:tls'
import { constants } from 'node:crypto'
import dns from 'node:dns'
import { setTimeout as delay } from 'node:timers/promises'
import { NativeTelemetryDelivery } from '../dist/telemetry-delivery.js'
import { DesktopTelemetryActivity } from '../dist/telemetry-activity.js'
import { TelemetryWorkflow } from '../dist/telemetry-workflow.js'
import { nativeTelemetryDefinitions } from '../dist/telemetry-store.js'
import { sendNativeTelemetry, TelemetryEndpoint } from '../dist/telemetry-transport.js'
import { parseTelemetryRoute, validCertificateAuthorities } from '../dist/telemetry-route.js'

const repository = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const python = process.env.MNEMION_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3')
const environment = { ...process.env, PYTHONPATH: repository, PYTHONNOUSERSITE: '1' }
let certificates, cert, key, otherCert
const run = (program, input) => {
  const child = spawnSync(python, ['-c', program], { env: environment, encoding: 'utf8', input: JSON.stringify(input), timeout: 20000 })
  assert.equal(child.status, 0, child.stderr)
  assert.equal(child.stderr, '')
  return child.stdout ? JSON.parse(child.stdout) : null
}

/** Refusal can finish without reaching a peer; report it instead of hanging CI. */
async function reached(stage, operation, label) {
  let timer
  try {
    await Promise.race([stage, operation.then(result => {
      throw new Error(`${label} was not reached before delivery settled${result?.outcome ? ` (${result.outcome})` : ''}`)
    }), new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`${label} was not reached within the fixture deadline`)), 7500)
    })])
  } finally { clearTimeout(timer) }
}
before(async () => {
  certificates = await mkdtemp(join(tmpdir(), 'mnemion-native-telemetry-ca-'))
  run(`
import json,sys
from pathlib import Path
from datetime import datetime,timedelta,timezone
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
folder=Path(json.load(sys.stdin))
key=ec.generate_private_key(ec.SECP256R1())
name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
now=datetime.now(timezone.utc)
cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
 .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
 .add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True)
 .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]),critical=False).sign(key,hashes.SHA256()))
(folder/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
(folder/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
(folder/'key.pem').chmod(0o600)
other_key=ec.generate_private_key(ec.SECP256R1())
other_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'other-test-authority')])
other_cert=(x509.CertificateBuilder().subject_name(other_name).issuer_name(other_name).public_key(other_key.public_key())
 .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
 .add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).sign(other_key,hashes.SHA256()))
(folder/'other-cert.pem').write_bytes(other_cert.public_bytes(serialization.Encoding.PEM))
`, certificates)
  cert = await readFile(join(certificates, 'cert.pem'), 'utf8')
  key = await readFile(join(certificates, 'key.pem'))
  otherCert = await readFile(join(certificates, 'other-cert.pem'), 'utf8')
})
after(async () => { await rm(certificates, { recursive: true, force: true }) })

for (const available of [false, true]) test('immutable release trust is parsed only when needed: ' + available, async t => {
  const definitions = nativeTelemetryDefinitions()
  const authorities = [cert], encoded = cert.trim().split('\n').slice(1, -1).join('')
  const activity = new DesktopTelemetryActivity('unused', {
    ...definitions.disclosure, collection_available: available, destination: 'https://localhost/v3/report',
  }, definitions.catalog, () => ({ network: 'unmetered', constrained: false }), undefined, '127.0.0.1', undefined, authorities)
  authorities[0] = 'PRIVATE_CALLER_REPLACEMENT'
  const original = Buffer.from
  let decodes = 0, reservations = 0
  t.mock.method(Buffer, 'from', (...args) => {
    if (args[0] === encoded && args[1] === 'base64') decodes++
    return original(...args)
  })
  activity.reserve = async () => { reservations++; return null }
  try {
    const stamp = { revision: 1, store_generation: 'a'.repeat(32) }
    for (let index = 0; index < 128; index++) activity.offerApproved(stamp)
    await activity.deliverySettled()
    assert.equal(reservations, available ? 1 : 0)
    assert.equal(decodes, available ? 1 : 0, 'Repeated offers use the same copied immutable release trust')
  } finally { activity.closeDelivery() }
})

async function peer(t, mode = 'success') {
  const sockets = new Set(), requests = []
  let connections = 0, enter, release, close
  const entered = new Promise(resolve => { enter = resolve })
  const closed = new Promise(resolve => { close = resolve })
  const handle = socket => {
    socket.on('error', () => {})
    let pending = Buffer.alloc(0)
    socket.on('data', chunk => {
      if (mode === 'stall_handshake') { enter(); return }
      pending = Buffer.concat([pending, chunk])
      const end = pending.indexOf('\r\n\r\n')
      if (end < 0 || pending.length < end + 29 || requests.length) return
      requests.push({ headers: pending.subarray(0, end).toString('ascii'), body: [...pending.subarray(end + 4)] })
      release = () => socket.end(mode === 'redirect'
        ? 'HTTP/1.1 302 Found\r\nLocation: https://private.invalid/secret\r\nContent-Length: 0\r\n\r\n'
        : mode === 'large_headers' ? 'HTTP/1.1 204 No Content\r\nX-Noise: ' + 'a'.repeat(4096) + '\r\n\r\n'
          : 'HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
      enter()
      if (mode !== 'hold') release()
    })
  }
  const server = mode === 'stall_handshake' ? tcpServer(handle) : createServer({ key,
    cert: mode === 'large_handshake' ? cert.repeat(100) : cert,
    minVersion: 'TLSv1.3', secureOptions: constants.SSL_OP_NO_TICKET }, handle)
  server.on('tlsClientError', () => {})
  server.on('connection', socket => {
    connections++; sockets.add(socket)
    socket.once('close', () => { sockets.delete(socket); close(performance.now()) })
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  t.after(async () => { for (const socket of sockets) socket.destroy(); await new Promise(resolve => server.close(resolve)) })
  return { endpoint: new TelemetryEndpoint('localhost', '127.0.0.1', server.address().port, [cert]), requests, entered, closed,
    release: () => release(), connections: () => connections }
}

async function installation(t, endpoint, options = {}) {
  const temporary = await mkdtemp(join(tmpdir(), 'mnemion-native-telemetry-'))
  t.after(() => rm(temporary, { recursive: true, force: true }))
  const root = join(temporary, 'private'), company = join(temporary, 'company.json')
  const destination = `https://${endpoint.authority()}/v3/report`
  const invoke = action => run(`
import json,sys,sqlite3
from pathlib import Path
from contextlib import closing
from mnemion.product_telemetry import policy
request=json.load(sys.stdin)
root=Path(request['root'])
policy.COLLECTION_AVAILABLE=True
policy.COLLECTOR_URL=request['destination']
policy.company_policy_file=lambda:Path(request['company'])
if request['action']=='init':result=policy.configure(root,{'enabled':True,'expected_revision':0,'disclosure_version':policy.DISCLOSURE_VERSION})
elif request['action']=='off':result=policy.configure(root,{'enabled':False,'expected_revision':0})
else:
 with closing(sqlite3.connect(root/policy.DATABASE_NAME)) as db:
  result={'leases':db.execute('SELECT count(*) FROM delivery_state WHERE lease_token IS NOT NULL').fetchone()[0],
   'attempts':db.execute('SELECT count(*) FROM delivery_attempts').fetchone()[0]}
print(json.dumps(result))
`, { root, company, destination, action })
  const { disclosure, catalog } = nativeTelemetryDefinitions()
  assert.equal(disclosure.collection_available, false)
  const active = { ...disclosure, collection_available: true, destination }
  const store = options.activity
    ? new DesktopTelemetryActivity(root, active, catalog, options.conditions ?? (() => ({ network: 'unmetered', constrained: false })), company, endpoint.address, options.gauges, endpoint.certificateAuthorities)
    : new NativeTelemetryDelivery(root, active, catalog, company)
  const stamp = invoke('init')
  if (options.activity) { t.after(() => store.closeDelivery()); return { store, stamp, invoke } }
  assert.equal(await store.record({ kind: 'submission', workflow: 'memory.recall', surface: 'desktop' }, stamp), true)
  const report = await store.reserve(stamp, { network: 'unmetered', constrained: false })
  assert.ok(report)
  const body = [...report.body()]
  return { store, report, body, invoke, cleaned() {
    assert.deepEqual([...report.body()], Array(25).fill(0)); assert.equal(report.closed, true)
    assert.deepEqual(invoke('inspect'), { leases: 0, attempts: 1 })
  } }
}

test('native TLS sends one fixed 25-byte request without DNS or ambient credentials', async t => {
  const server = await peer(t), f = await installation(t, server.endpoint)
  const lookup = dns.lookup
  dns.lookup = () => { throw new Error('DNS must not be used') }
  let result
  try { result = await sendNativeTelemetry(f.store, f.report, server.endpoint) } finally { dns.lookup = lookup }
  assert.equal(result.outcome, 'delivered')
  assert.ok(result.encrypted_bytes_charged > 500 && result.encrypted_bytes_charged <= 32768)
  assert.equal(server.connections(), 1); assert.equal(server.requests.length, 1)
  assert.deepEqual(server.requests[0].body, f.body)
  assert.deepEqual(server.requests[0].headers.split('\r\n'), ['POST /v3/report HTTP/1.1',
    `Host: ${server.endpoint.authority()}`, 'Content-Type: application/octet-stream', 'Content-Length: 25', 'Connection: close'])
  f.cleaned()
})

test('native TLS ignores ambient trust in an unselected certificate authority', async t => {
  const server = await peer(t), selected = new TelemetryEndpoint('localhost', '127.0.0.1', server.endpoint.port, [otherCert])
  const f = await installation(t, selected), previous = getCACertificates('default')
  setDefaultCACertificates([cert])
  let result
  try { result = await sendNativeTelemetry(f.store, f.report, selected) }
  finally { setDefaultCACertificates(previous) }
  assert.equal(result.outcome, 'failed')
  assert.equal(server.connections(), 1); assert.equal(server.requests.length, 0)
  f.cleaned()
})

test('native TLS accepts a second release authority without retaining the caller list', async t => {
  const server = await peer(t), roots = [otherCert, cert]
  const selected = new TelemetryEndpoint('localhost', '127.0.0.1', server.endpoint.port, roots)
  roots.splice(0)
  const f = await installation(t, selected)
  const result = await sendNativeTelemetry(f.store, f.report, selected)
  assert.equal(result.outcome, 'delivered'); assert.equal(server.requests.length, 1)
  assert.deepEqual(selected.certificateAuthorities, [otherCert, cert])
  f.cleaned()
})

for (const [kind, authorities] of [
  ['missing', () => []],
  ['invalid envelope', () => ['not-a-certificate']],
  ['invalid certificate', () => ['-----BEGIN CERTIFICATE-----\nMAMCAQE=\n-----END CERTIFICATE-----\n']],
]) test(`native ${kind} trust refuses before a connection`, async t => {
  const server = await peer(t), target = new TelemetryEndpoint('localhost', '127.0.0.1', server.endpoint.port, authorities())
  const f = await installation(t, target)
  const result = await sendNativeTelemetry(f.store, f.report, target)
  assert.ok(['suppressed', 'failed'].includes(result.outcome))
  assert.equal(server.connections(), 0); assert.equal(server.requests.length, 0)
  f.cleaned()
})

test('release trust permits one or two distinct public certificates and freezes its inputs', () => {
  const input = { version: 2, address: '127.0.0.1', certificate_authorities: [cert, otherCert] }
  const selected = parseTelemetryRoute(input)
  assert.ok(selected)
  input.address = '127.0.0.2'; input.certificate_authorities.splice(0)
  assert.equal(selected.address, '127.0.0.1')
  assert.deepEqual(selected.certificate_authorities, [cert, otherCert])
  assert.ok(Object.isFrozen(selected) && Object.isFrozen(selected.certificate_authorities))
  assert.equal(validCertificateAuthorities([cert.replace(/\n/g, '\r\n')]), true)
})

for (const kind of ['legacy', 'missing', 'empty', 'duplicate', 'excessive', 'extra', 'wrong_version', 'oversized', 'bundled', 'invalid_base64', 'unicode']) {
  test(`release trust rejects ${kind} inputs without ambient fallback`, () => {
    const value = { version: 2, address: '127.0.0.1', certificate_authorities: [cert] }
    if (kind === 'legacy') { value.version = 1; delete value.certificate_authorities }
    else if (kind === 'missing') delete value.certificate_authorities
    else if (kind === 'empty') value.certificate_authorities = []
    else if (kind === 'duplicate') value.certificate_authorities = [cert, cert.replace(/\n/g, '\r\n')]
    else if (kind === 'excessive') value.certificate_authorities = [cert, otherCert, cert]
    else if (kind === 'extra') value.ambient_fallback = true
    else if (kind === 'wrong_version') value.version = true
    else if (kind === 'oversized') value.certificate_authorities = ['x'.repeat(16385)]
    else if (kind === 'bundled') value.certificate_authorities = [cert + otherCert]
    else if (kind === 'invalid_base64') value.certificate_authorities = ['-----BEGIN CERTIFICATE-----\nA===\n-----END CERTIFICATE-----\n']
    else value.certificate_authorities = [cert.replace(/\n/g, '\u2028')]
    assert.equal(parseTelemetryRoute(value), null)
  })
}

test('a slow active privacy read cannot compete with its own final TLS handoff', async t => {
  const server = await peer(t), f = await installation(t, server.endpoint)
  const open = f.store.open.bind(f.store), close = f.store.closeDatabase.bind(f.store)
  const handles = new Set()
  let reads = 0, delayed = false, peak = 0
  f.store.open = async (...args) => {
    const database = await open(...args)
    handles.add(database); peak = Math.max(peak, handles.size)
    // Keep the actual single storage slot occupied while the TLS handshake
    // finishes, as a Windows ACL read can do. No policy read is bypassed.
    if (!args[0] && ++reads === 2) { delayed = true; await delay(150) }
    return database
  }
  f.store.closeDatabase = database => {
    close(database)
    if (database && !database.isOpen) handles.delete(database)
  }
  const result = await sendNativeTelemetry(f.store, f.report, server.endpoint)
  assert.equal(delayed, true)
  assert.equal(result.outcome, 'delivered')
  assert.equal(server.requests.length, 1)
  assert.equal(peak, 1); assert.equal(handles.size, 0)
  f.cleaned()
})

test('Python opt-out during a slow active privacy read still blocks the final TLS handoff', async t => {
  const server = await peer(t), f = await installation(t, server.endpoint)
  const open = f.store.open.bind(f.store)
  let reads = 0, enter, release
  const entered = new Promise(resolve => { enter = resolve }), held = new Promise(resolve => { release = resolve })
  t.after(() => release())
  f.store.open = async (...args) => {
    const database = await open(...args)
    if (!args[0] && ++reads === 2) { enter(); await held }
    return database
  }
  const pending = sendNativeTelemetry(f.store, f.report, server.endpoint)
  try {
    await reached(entered, pending, 'Active privacy read')
    f.invoke('off')
  } finally { release() }
  assert.equal((await pending).outcome, 'suppressed')
  assert.equal(server.requests.length, 0)
  f.cleaned()
})

test('ordinary desktop recording owns a real TLS send without a manual reserve or sender call', async t => {
  const server = await peer(t), f = await installation(t, server.endpoint, { activity: true })
  assert.equal(await f.store.record({ kind: 'submission', workflow: 'memory.recall', surface: 'desktop' }, f.stamp), true)
  await f.store.deliverySettled()
  assert.equal(server.requests.length, 1)
  assert.equal(server.requests[0].body.length, 25)
  assert.deepEqual(f.invoke('inspect'), { leases: 0, attempts: 1 })
  assert.equal(await f.store.record({ kind: 'submission', workflow: 'memory.save', surface: 'desktop' }, f.stamp), true)
  await f.store.deliverySettled()
  assert.equal(server.requests.length, 1)
})

test('desktop OS gauges never start during cooldown and close after the actual TLS attempt', async t => {
  let preparations = 0, closes = 0
  const server = await peer(t), f = await installation(t, server.endpoint, { activity: true,
    gauges: { prepare: async () => { preparations++; return true }, close: () => { closes++ } } })
  assert.equal(await f.store.eligible(f.stamp), false)
  await f.store.record({ kind: 'submission', workflow: 'memory.recall', surface: 'desktop' }, f.stamp)
  await f.store.deliverySettled()
  assert.equal(preparations, 1); assert.equal(closes, 1); assert.equal(server.requests.length, 1)
  f.store.resumeDelivery()
  await f.store.record({ kind: 'submission', workflow: 'memory.save', surface: 'desktop' }, f.stamp)
  await f.store.deliverySettled()
  assert.equal(preparations, 1); assert.equal(server.connections(), 1)
  assert.deepEqual(f.invoke('inspect'), { leases: 0, attempts: 1 })
})

for (const transition of ['ready', 'opted_out', 'closed']) test('queued desktop delivery after collection saturation: ' + transition, async t => {
  let now = 0, ready = false, preparations = 0
  t.mock.method(performance, 'now', () => now)
  const server = await peer(t), f = await installation(t, server.endpoint, { activity: true,
    gauges: { prepare: async () => { preparations++; return ready }, close: () => {} } })
  const observation = { kind: 'submission', workflow: 'memory.recall', surface: 'desktop' }
  for (let index = 0; index < 64; index++) {
    assert.equal(await f.store.record(observation, f.stamp), true)
    await f.store.deliverySettled()
  }
  assert.equal(preparations, 1)
  assert.deepEqual(f.invoke('inspect'), { leases: 0, attempts: 0 })
  assert.equal(server.connections(), 0)
  ready = true
  if (transition === 'opted_out') f.invoke('off')
  if (transition === 'closed') f.store.closeDelivery()
  now = 60001
  // Existing awake work can revisit queued data; it cannot buy another
  // collection contribution, override opt-out or flush a closed owner.
  assert.equal(await f.store.record(observation, f.stamp), false)
  await f.store.deliverySettled()
  assert.equal(server.requests.length, transition === 'ready' ? 1 : 0)
  assert.equal(preparations, transition === 'ready' ? 2 : 1)
  assert.deepEqual(f.invoke('inspect'), { leases: 0, attempts: transition === 'ready' ? 1 : 0 })
  assert.equal(await f.store.record(observation, f.stamp), false)
  await f.store.deliverySettled()
  assert.equal(server.requests.length, transition === 'ready' ? 1 : 0)
})

for (const transition of ['ready', 'opted_out', 'closed']) test('queued desktop delivery survives an exhausted workflow snapshot: ' + transition, async t => {
  let now = 0, ready = false, preparations = 0
  t.mock.method(performance, 'now', () => now)
  const server = await peer(t), f = await installation(t, server.endpoint, { activity: true,
    gauges: { prepare: async () => { preparations++; return ready }, close: () => {} } })
  const observation = { kind: 'submission', workflow: 'memory.recall', surface: 'desktop' }
  for (let index = 0; index < 64; index++) {
    now = index * 500
    assert.equal(await f.store.record(observation, f.stamp), true)
    await f.store.deliverySettled()
  }
  assert.equal(preparations, 1)
  assert.equal(server.connections(), 0)
  ready = true
  if (transition === 'opted_out') f.invoke('off')
  if (transition === 'closed') f.store.closeDelivery()
  now = 60001 // Delivery is due; the last collection hint is still live.
  // Unscoped inspection and invalid workflow names never offer old work.
  await f.store.snapshot()
  await f.store.snapshot('unknown.private.workflow', 'desktop')
  await f.store.deliverySettled()
  assert.equal(server.connections(), 0)
  const work = await TelemetryWorkflow.begin(f.store, 'memory.recall', 'desktop')
  assert.equal(work, null, 'A cached refusal must still avoid a new observation')
  await f.store.deliverySettled()
  assert.equal(server.requests.length, transition === 'ready' ? 1 : 0)
  assert.equal(preparations, transition === 'ready' ? 2 : 1)
  assert.deepEqual(f.invoke('inspect'), { leases: 0, attempts: transition === 'ready' ? 1 : 0 })
  const later = await TelemetryWorkflow.begin(f.store, 'memory.recall', 'desktop')
  if (later) await later.finish('success')
  await f.store.deliverySettled()
  assert.equal(server.requests.length, transition === 'ready' ? 1 : 0)
})

test('an opt-out during OS preparation is rechecked before any budget or socket is used', async t => {
  let enter, finish, closes = 0
  const entered = new Promise(resolve => { enter = resolve }), pending = new Promise(resolve => { finish = resolve })
  t.after(() => finish())
  const server = await peer(t), f = await installation(t, server.endpoint, { activity: true,
    gauges: { prepare: async () => { enter(); await pending; return true }, close: () => { closes++ } } })
  await f.store.record({ kind: 'submission', workflow: 'memory.recall', surface: 'desktop' }, f.stamp)
  await reached(entered, f.store.deliverySettled(), 'OS preparation'); f.invoke('off'); finish()
  await f.store.deliverySettled()
  assert.equal(closes, 1); assert.equal(server.connections(), 0)
  assert.deepEqual(f.invoke('inspect'), { leases: 0, attempts: 0 })
})

test('the desktop owner pauses before dispatch and cancels when actual admission changes', async t => {
  let constrained = false
  const server = await peer(t, 'hold'), f = await installation(t, server.endpoint,
    { activity: true, conditions: () => ({ network: 'unmetered', constrained }) })
  f.store.pauseDelivery('suspend'); f.store.pauseDelivery('update'); f.store.resumeDelivery('suspend')
  assert.equal(await f.store.record({ kind: 'submission', workflow: 'memory.recall', surface: 'desktop' }, f.stamp), true)
  await f.store.deliverySettled()
  assert.deepEqual(f.invoke('inspect'), { leases: 0, attempts: 0 })
  f.store.resumeDelivery('update')
  assert.equal(await f.store.record({ kind: 'submission', workflow: 'memory.save', surface: 'desktop' }, f.stamp), true)
  await reached(server.entered, f.store.deliverySettled(), 'TLS request')
  constrained = true
  await f.store.deliverySettled()
  assert.deepEqual(f.invoke('inspect'), { leases: 0, attempts: 1 })
  assert.equal(server.connections(), 1)
})

test('simultaneous and response-pending native sends cannot steal the winner or open another socket', async t => {
  const server = await peer(t, 'hold'), f = await installation(t, server.endpoint)
  const first = sendNativeTelemetry(f.store, f.report, server.endpoint)
  const duplicate = await sendNativeTelemetry(f.store, f.report, server.endpoint)
  assert.deepEqual(duplicate, { outcome: 'suppressed', encrypted_bytes_charged: 0 })
  await reached(server.entered, first, 'TLS request')
  assert.deepEqual(await sendNativeTelemetry(f.store, f.report, server.endpoint), duplicate)
  server.release()
  assert.equal((await first).outcome, 'delivered'); assert.equal(server.connections(), 1)
  f.cleaned()
})

for (const mode of ['stall_handshake', 'hold']) test(`Python opt-out cancels a native ${mode} attempt`, async t => {
  const server = await peer(t, mode), f = await installation(t, server.endpoint)
  const pending = sendNativeTelemetry(f.store, f.report, server.endpoint)
  await reached(server.entered, pending, 'TLS peer')
  const start = performance.now()
  f.invoke('off')
  assert.equal((await pending).outcome, 'suppressed')
  assert.ok(performance.now() - start < 1500)
  assert.equal(server.requests.length, mode === 'hold' ? 1 : 0)
  f.cleaned()
})

test('the owner aborts a native send without replay or refund', async t => {
  const server = await peer(t, 'hold'), f = await installation(t, server.endpoint), owner = new AbortController()
  const pending = sendNativeTelemetry(f.store, f.report, server.endpoint, owner.signal)
  await reached(server.entered, pending, 'TLS request')
  owner.abort()
  assert.equal((await pending).outcome, 'suppressed'); assert.equal(server.connections(), 1)
  f.cleaned()
})

for (const mode of ['redirect', 'large_headers']) test(`native ${mode} responses fail without another request`, async t => {
  const server = await peer(t, mode), f = await installation(t, server.endpoint)
  assert.equal((await sendNativeTelemetry(f.store, f.report, server.endpoint)).outcome, 'failed')
  assert.equal(server.connections(), 1); assert.equal(server.requests.length, 1)
  f.cleaned()
})

test('certificate name mismatch never exposes the report', async t => {
  const server = await peer(t), endpoint = new TelemetryEndpoint('wrong.invalid', '127.0.0.1', server.endpoint.port, [cert])
  const f = await installation(t, endpoint)
  assert.equal((await sendNativeTelemetry(f.store, f.report, endpoint)).outcome, 'failed')
  assert.equal(server.requests.length, 0)
  f.cleaned()
})

test('an oversized encrypted handshake exhausts the native TLS allowance before application data', async t => {
  const server = await peer(t, 'large_handshake'), f = await installation(t, server.endpoint)
  const result = await sendNativeTelemetry(f.store, f.report, server.endpoint)
  assert.equal(result.outcome, 'wire_limit'); assert.equal(result.encrypted_bytes_charged, 32768)
  assert.equal(server.requests.length, 0)
  f.cleaned()
})

test('the five-second native deadline closes a silent TLS peer before cleanup finishes', { timeout: 15000 }, async t => {
  const server = await peer(t, 'stall_handshake'), f = await installation(t, server.endpoint)
  const start = performance.now(), deadline = f.report.monotonicDeadline
  const cancel = f.store.cancel.bind(f.store)
  let finishCleanup, enterCleanup, settled = false
  const cleanup = new Promise(resolve => { finishCleanup = resolve })
  const cleanupEntered = new Promise(resolve => { enterCleanup = resolve })
  t.after(() => finishCleanup())
  // Hold only post-expiry cleanup completion. The actual TCP/TLS transport, private
  // policy and five-second reservation clock remain unchanged. This proves
  // that a slow native ACL cleanup cannot keep the connection alive.
  f.store.cancel = async report => {
    const local = cancel(report)
    enterCleanup()
    await cleanup
    return local
  }
  const pending = sendNativeTelemetry(f.store, f.report, server.endpoint).then(result => { settled = true; return result })
  let closedAt, closedBeforeCleanup, erasedBeforeCleanup, result
  try {
    await reached(server.entered, pending, 'Silent TLS peer')
    await reached(server.closed, pending, 'TCP close')
    closedAt = await server.closed
    await reached(cleanupEntered, pending, 'Post-expiry cleanup')
    closedBeforeCleanup = !settled
    erasedBeforeCleanup = f.report.closed
  } finally { finishCleanup(); result = await pending }
  assert.equal(closedBeforeCleanup, true)
  assert.equal(erasedBeforeCleanup, true)
  assert.ok(['deadline', 'suppressed'].includes(result.outcome))
  // The lease starts during reservation, before send() is entered. Keep the
  // previous 500 ms early/700 ms late allowance against that real deadline,
  // measuring the peer's observed close rather than final database cleanup.
  const timing = { connection_ms: closedAt - start, deadline_remaining_ms: deadline - start,
    deadline_offset_ms: closedAt - deadline, cleanup_ms: performance.now() - closedAt }
  t.diagnostic(JSON.stringify(timing))
  assert.ok(closedAt >= deadline - 500 && closedAt < deadline + 700, JSON.stringify(timing))
  assert.equal(server.requests.length, 0); assert.equal(server.connections(), 1)
  f.cleaned()
})

test('only the exact disclosed HTTPS destination and a literal address are accepted', async t => {
  const server = await peer(t), f = await installation(t, server.endpoint)
  const invalid = new TelemetryEndpoint('private.invalid', 'localhost', server.endpoint.port)
  assert.equal((await sendNativeTelemetry(f.store, f.report, invalid)).outcome, 'suppressed')
  assert.equal(server.connections(), 0)
  f.cleaned()
})
