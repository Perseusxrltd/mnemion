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
import { NativeTelemetryDelivery } from '../dist/telemetry-delivery.js'
import { nativeTelemetryDefinitions } from '../dist/telemetry-store.js'
import { sendNativeTelemetry, TelemetryEndpoint } from '../dist/telemetry-transport.js'

const repository = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const python = process.env.MNEMION_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3')
const environment = { ...process.env, PYTHONPATH: repository, PYTHONNOUSERSITE: '1' }
const originalRoots = getCACertificates('default')
let certificates, cert, key
const run = (program, input) => {
  const child = spawnSync(python, ['-c', program], { env: environment, encoding: 'utf8', input: JSON.stringify(input), timeout: 20000 })
  assert.equal(child.status, 0, child.stderr)
  assert.equal(child.stderr, '')
  return child.stdout ? JSON.parse(child.stdout) : null
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
`, certificates)
  cert = await readFile(join(certificates, 'cert.pem'), 'utf8')
  key = await readFile(join(certificates, 'key.pem'))
  setDefaultCACertificates([...originalRoots, cert])
})
after(async () => { setDefaultCACertificates(originalRoots); await rm(certificates, { recursive: true, force: true }) })

async function peer(t, mode = 'success') {
  const sockets = new Set(), requests = []
  let connections = 0, enter, release
  const entered = new Promise(resolve => { enter = resolve })
  const handle = socket => {
    socket.on('error', () => {})
    let pending = Buffer.alloc(0)
    socket.on('data', chunk => {
      if (mode === 'stall_handshake') { enter(); return }
      pending = Buffer.concat([pending, chunk])
      const end = pending.indexOf('\r\n\r\n')
      if (end < 0 || pending.length < end + 8 || requests.length) return
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
  server.on('connection', socket => { connections++; sockets.add(socket); socket.once('close', () => sockets.delete(socket)) })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  t.after(async () => { for (const socket of sockets) socket.destroy(); await new Promise(resolve => server.close(resolve)) })
  return { endpoint: new TelemetryEndpoint('localhost', '127.0.0.1', server.address().port), requests, entered,
    release: () => release(), connections: () => connections }
}

async function installation(t, endpoint) {
  const temporary = await mkdtemp(join(tmpdir(), 'mnemion-native-telemetry-'))
  t.after(() => rm(temporary, { recursive: true, force: true }))
  const root = join(temporary, 'private'), company = join(temporary, 'company.json')
  const destination = `https://${endpoint.authority()}/v1/report`
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
if request['action']=='init':result=policy.configure(root,{'enabled':True,'expected_revision':0,'disclosure_version':1})
elif request['action']=='off':result=policy.configure(root,{'enabled':False,'expected_revision':0})
else:
 with closing(sqlite3.connect(root/policy.DATABASE_NAME)) as db:
  result={'leases':db.execute('SELECT count(*) FROM delivery_state WHERE lease_token IS NOT NULL').fetchone()[0],
   'attempts':db.execute('SELECT count(*) FROM delivery_attempts').fetchone()[0]}
print(json.dumps(result))
`, { root, company, destination, action })
  const { disclosure, catalog } = nativeTelemetryDefinitions()
  assert.equal(disclosure.collection_available, false)
  const store = new NativeTelemetryDelivery(root, { ...disclosure, collection_available: true, destination }, catalog, company)
  const stamp = invoke('init')
  assert.equal(await store.record({ kind: 'submission', workflow: 'memory.recall', surface: 'desktop' }, stamp), true)
  const report = await store.reserve(stamp, { network: 'unmetered', constrained: false })
  assert.ok(report)
  const body = [...report.body()]
  return { store, report, body, invoke, cleaned() {
    assert.deepEqual([...report.body()], [0, 0, 0, 0]); assert.equal(report.closed, true)
    assert.deepEqual(invoke('inspect'), { leases: 0, attempts: 1 })
  } }
}

test('native TLS sends one fixed four-byte request without DNS or ambient credentials', async t => {
  const server = await peer(t), f = await installation(t, server.endpoint)
  const lookup = dns.lookup
  dns.lookup = () => { throw new Error('DNS must not be used') }
  let result
  try { result = await sendNativeTelemetry(f.store, f.report, server.endpoint) } finally { dns.lookup = lookup }
  assert.equal(result.outcome, 'delivered')
  assert.ok(result.encrypted_bytes_charged > 500 && result.encrypted_bytes_charged <= 32768)
  assert.equal(server.connections(), 1); assert.equal(server.requests.length, 1)
  assert.deepEqual(server.requests[0].body, f.body)
  assert.deepEqual(server.requests[0].headers.split('\r\n'), ['POST /v1/report HTTP/1.1',
    `Host: ${server.endpoint.authority()}`, 'Content-Type: application/octet-stream', 'Content-Length: 4', 'Connection: close'])
  f.cleaned()
})

test('simultaneous and response-pending native sends cannot steal the winner or open another socket', async t => {
  const server = await peer(t, 'hold'), f = await installation(t, server.endpoint)
  const first = sendNativeTelemetry(f.store, f.report, server.endpoint)
  const duplicate = await sendNativeTelemetry(f.store, f.report, server.endpoint)
  assert.deepEqual(duplicate, { outcome: 'suppressed', encrypted_bytes_charged: 0 })
  await server.entered
  assert.deepEqual(await sendNativeTelemetry(f.store, f.report, server.endpoint), duplicate)
  server.release()
  assert.equal((await first).outcome, 'delivered'); assert.equal(server.connections(), 1)
  f.cleaned()
})

for (const mode of ['stall_handshake', 'hold']) test(`Python opt-out cancels a native ${mode} attempt`, async t => {
  const server = await peer(t, mode), f = await installation(t, server.endpoint)
  const pending = sendNativeTelemetry(f.store, f.report, server.endpoint)
  await server.entered
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
  await server.entered
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
  const server = await peer(t), endpoint = new TelemetryEndpoint('wrong.invalid', '127.0.0.1', server.endpoint.port)
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

test('the five-second native deadline closes a silent TLS peer', async t => {
  const server = await peer(t, 'stall_handshake'), f = await installation(t, server.endpoint), start = performance.now()
  const result = await sendNativeTelemetry(f.store, f.report, server.endpoint)
  assert.ok(['deadline', 'suppressed'].includes(result.outcome))
  assert.ok(performance.now() - start >= 4500 && performance.now() - start < 5700)
  assert.equal(server.requests.length, 0)
  f.cleaned()
})

test('only the exact disclosed HTTPS destination and a literal address are accepted', async t => {
  const server = await peer(t), f = await installation(t, server.endpoint)
  const invalid = new TelemetryEndpoint('private.invalid', 'localhost', server.endpoint.port)
  assert.equal((await sendNativeTelemetry(f.store, f.report, invalid)).outcome, 'suppressed')
  assert.equal(server.connections(), 0)
  f.cleaned()
})
