import assert from 'node:assert/strict'
import childProcess from 'node:child_process'
import { EventEmitter } from 'node:events'
import { readFileSync } from 'node:fs'
import { syncBuiltinESMExports } from 'node:module'
import { PassThrough } from 'node:stream'
import { test } from 'node:test'
import { LocalWorkspace, portOptions, localDiagnostic, remoteOptions, remoteSnapshot } from '../dist/local-workspace.js'
import { companyOptions, companySnapshot, companyDiscoveryResult } from '../dist/local-company-protocol.js'
import { vaultOptions, vaultSnapshot, vaultKeyId, vaultKeyResult } from '../dist/local-vault-protocol.js'

const { version } = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'))
const root = '/private/test-workspace'
const settle = () => new Promise(resolve => setImmediate(resolve))
const policy = revision => ({ format: 1, revision, settings: { mode: 'manual', limit_mib: 512 } })
const info = revision => ({ event: 'status', configured: true, data_directory: root, engine_version: version,
  resources: { memory_bytes: 4 * 1024 ** 3, available_disk_bytes: 8 * 1024 ** 3 }, memory_policy: policy(revision) })
const addressChange = { workspace_id: '00000000-0000-4000-8000-000000000001', expected_port: 17400, port: null }
const addressInfo = port => ({ ...info('first'), settings: { workspace_id: addressChange.workspace_id, port, database_port: 17401 } })
const sharing = (revision = 'not-configured', mode = 'disabled') => ({ revision, mode,
  public_url: mode === 'disabled' ? null : 'https://memory.example.test', personal_sign_in: true,
  has_ngrok_authtoken: false, repairable: true, state: mode === 'disabled' ? 'disabled' : 'unchecked', message: 'Fixture host status' })
const sharingInfo = (revision = 'not-configured', mode = 'disabled') => ({ ...addressInfo(17400), remote_access: sharing(revision, mode) })
const sharingChange = { workspace_id: addressChange.workspace_id, expected_revision: 'not-configured',
  mode: 'proxy', public_url: 'https://memory.example.test', personal_sign_in: true, ngrok_authtoken: null }
const savedSharingRevision = '00000000-0000-4000-8000-000000000009'
const companyProvider = { id: 'company', name: 'Company account', issuer: 'https://identity.example.test/company',
  authorization_url: 'https://identity.example.test/company/auth', token_url: 'https://identity.example.test/company/token',
  jwks_url: 'https://identity.example.test/company/keys', client_id: 'mnemion-client', session_seconds: 28800 }
const companyChange = { workspace_id: addressChange.workspace_id, expected_revision: 'not-configured', expected_remote_revision: savedSharingRevision,
  action: 'save', provider: companyProvider, client_secret: 'private-company-secret-sentinel' }
const companyInfo = (revision = 'not-configured', providers = []) => ({ ...sharingInfo(savedSharingRevision, 'proxy'), company_access: {
  revision, providers, state: providers.length ? 'configured' : 'disabled', repairable: true, has_custom_ca: false,
  message: 'Company settings fixture', callback_uri: 'https://memory.example.test/company/callback',
} })
const savedCompanyInfo = () => companyInfo('00000000-0000-4000-8000-000000000010', [{ ...companyProvider, has_client_secret: true }])
const vaultKey = 'mnv_' + Buffer.alloc(32, 7).toString('base64url')
const vaultRevision = '00000000-0000-4000-8000-000000000012'
const vaultChange = { workspace_id: addressChange.workspace_id, expected_revision: 'not-configured',
  action: 'configure', enabled: true, mcp_enabled: false, recovery_key: vaultKey, key_saved: true }
const vaultInfo = (configured = false) => ({ ...addressInfo(17400), vault_access: {
  revision: configured ? vaultRevision : 'not-configured', state: configured ? 'configured' : 'not_configured',
  repairable: true, enabled: configured, mcp_enabled: false, key_id: configured ? vaultKeyId(vaultKey) : null,
  message: 'Private vault fixture',
} })

test('vault handoffs reject unreviewed instructions and credentials in public status', () => {
  assert.deepEqual(vaultOptions(vaultChange), vaultChange)
  assert.throws(() => vaultOptions({ ...vaultChange, execute: 'unreviewed-command' }))
  assert.throws(() => vaultOptions({ ...vaultChange, key_saved: false }))
  assert.throws(() => vaultOptions({ ...vaultChange, recovery_key: 'mnv_' + 'b'.repeat(43) }))
  assert.throws(() => vaultSnapshot({ ...vaultInfo(true).vault_access, recovery_key: vaultKey }))
  assert.deepEqual(vaultSnapshot(vaultInfo(true).vault_access), vaultInfo(true).vault_access)
  const request = { workspace_id: addressChange.workspace_id, expected_revision: vaultRevision }
  const result = { workspace_id: request.workspace_id, revision: vaultRevision, key_id: vaultKeyId(vaultKey), recovery_key: vaultKey }
  assert.deepEqual(vaultKeyResult(result, request), result)
  assert.throws(() => vaultKeyResult({ ...result, revision: savedSharingRevision }, request))
  assert.throws(() => vaultKeyResult({ ...result, key_id: '0'.repeat(32) }, request))
})

test('company controls reject credentials in status and unsupported host instructions', () => {
  assert.deepEqual(companyOptions(companyChange), companyChange)
  assert.throws(() => companyOptions({ ...companyChange, execute: 'unreviewed-command' }))
  assert.throws(() => companyOptions({ ...companyChange, provider: { ...companyProvider, token_url: 'https://identity.example.test/token?credential=private' } }))
  assert.throws(() => companyOptions({ ...companyChange, ca_pem: '-----BEGIN PRIVATE KEY-----' }))
  assert.throws(() => companyOptions({ ...companyChange, client_secret: 'x'.repeat(2049) }))
  assert.throws(() => companyOptions({ ...companyChange, clear_client_secret: true }))
  assert.deepEqual(companySnapshot(savedCompanyInfo().company_access), savedCompanyInfo().company_access)
  assert.throws(() => companySnapshot({ ...savedCompanyInfo().company_access, client_secret: 'private-sentinel' }))
  assert.throws(() => companySnapshot({ ...savedCompanyInfo().company_access, providers: [{ ...companyProvider, has_client_secret: true, client_secret: 'private-sentinel' }] }))
  assert.throws(() => companyDiscoveryResult({ ...companyChange, issuer: companyProvider.issuer }, { ...companyChange, issuer: companyProvider.issuer }))
})

test('remote controls accept only explicit HTTPS routes and never return provider credentials', () => {
  assert.equal(remoteOptions({ ...sharingChange, public_url: 'https://memory.example.test/mcp' }).public_url, 'https://memory.example.test')
  for (const public_url of ['http://memory.example.test', 'https://user:secret@memory.example.test', 'https://memory.example.test/private', 'https://memory.example.test/?secret=value', 'https://memory.example.test/#secret']) {
    assert.throws(() => remoteOptions({ ...sharingChange, public_url }))
  }
  assert.throws(() => remoteOptions({ ...sharingChange, executable: 'unreviewed-command' }))
  assert.throws(() => remoteSnapshot({ ...sharing(), ngrok_authtoken: 'private-provider-sentinel' }))
  assert.deepEqual(remoteSnapshot(sharing()), sharing())
})

test('setup diagnostics admit bounded code locations and refuse private provider detail', () => {
  const diagnostic = { category: 'database', sqlstate: '08001', locations: [{ module: 'mnemion.local_database', function: 'start', line: 1 }] }
  assert.deepEqual(localDiagnostic(diagnostic), diagnostic)
  assert.notEqual(localDiagnostic(diagnostic), diagnostic)
  for (const input of [null, [], { ...diagnostic, message: 'private provider error' }, { ...diagnostic, sqlstate: 'private' },
    { ...diagnostic, errno: -1 }, { ...diagnostic, locations: Array(9).fill(diagnostic.locations[0]) },
    { ...diagnostic, locations: [{ ...diagnostic.locations[0], module: '/private/path' }] },
    { ...diagnostic, locations: [{ ...diagnostic.locations[0], source: 'private memory' }] }]) {
    assert.throws(() => localDiagnostic(input), /Invalid setup diagnostic/)
  }
})

class Command extends EventEmitter {
  stdin = new PassThrough()
  stdout = new PassThrough()
  stderr = new PassThrough()
  closed = false
  constructor(action) { super(); this.action = action }
  reply(value) { this.stdout.write(JSON.stringify(value)); this.finish() }
  event(value) { this.stdout.write(JSON.stringify(value) + '\n') }
  finish(code = 0) { if (!this.closed) { this.closed = true; this.emit('close', code) } }
  kill() { this.finish(); return true }
}

function fixture(t) {
  const commands = []
  t.mock.method(childProcess, 'spawn', (_executable, args) => {
    const command = new Command(args[1]); commands.push(command); return command
  })
  syncBuiltinESMExports()
  const host = new LocalWorkspace({ executable: process.execPath, database: process.execPath, root, version, environment: {} }, () => {})
  t.after(async () => {
    const close = host.close()
    await settle()
    for (const command of commands) command.finish()
    await close
    t.mock.restoreAll()
    syncBuiltinESMExports()
  })
  return { commands, host, last: () => commands.at(-1) }
}

async function running(f) {
  const start = f.host.start()
  f.last().reply(info('first'))
  await start
  const engine = f.last()
  engine.event({ event: 'ready', endpoint: 'http://127.0.0.1:17400', credential: 'mnm_' + 'a'.repeat(48),
    workspace_id: '00000000-0000-4000-8000-000000000001', tenant_id: '00000000-0000-4000-8000-000000000003', engine_version: version })
  f.last().reply(info('first'))
  await settle()
  return engine
}

test('an update waits for backup cancellation and database shutdown before replacing the runtime', async t => {
  const f = fixture(t)
  const engine = await running(f)
  const work = f.host.runBackup('backup', { workspace_id: addressChange.workspace_id, destination: '/separate/backups' })
  const cancelled = assert.rejects(work, /cancelled/)
  const helper = f.last()
  await assert.rejects(f.host.start(), /recovery operation/)
  await assert.rejects(f.host.changeRemote(sharingChange), /operation|changes|finishing/)
  let complete = false
  const stopping = f.host.stopForUpdate().then(value => { complete = true; return value })
  await settle()
  assert.equal(complete, false)
  assert.equal(engine.stdin.writableEnded, false)
  assert.equal(f.host.status.backup.state, 'cancelling')
  helper.event({ event: 'cancelled' })
  helper.finish()
  await cancelled
  await settle()
  assert.equal(engine.stdin.writableEnded, true)
  assert.equal(complete, false)
  engine.finish()
  await settle()
  if (f.last().action === 'status') f.last().reply(info('first'))
  assert.equal(await stopping, true)
  assert.equal(f.host.status.backup.state, 'cancelled')
})

test('recovery results stay private until the matching runtime has finished successfully', async t => {
  const f = fixture(t)
  const work = f.host.runBackup('backup-inspect', { source: '/separate/ledger.enc', recovery_key: 'private-input-sentinel' })
  const helper = f.last()
  const inspection = { kind: 'ledger', key_id: 'a'.repeat(24), encrypted_bytes: 100, sha256: 'b'.repeat(64),
    authenticated: true, ledger_at: new Date().toISOString(), tenant_count: 1, deletion_count: 1, private_key: 'private-output-sentinel' }
  helper.event({ event: 'backup_inspection', engine_version: version, inspection })
  assert.equal(f.host.backupActive, true)
  assert.equal(f.host.status.backup.state, 'running')
  helper.finish()
  const result = await work
  assert.equal(result.deletion_count, 1)
  assert.equal(result.private_key, undefined)
  assert.ok(!JSON.stringify(f.host.status).includes('sentinel'))
  assert.equal(f.host.backupActive, false)

  const mismatch = f.host.runBackup('backup-inspect', { source: '/separate/ledger.enc' })
  const denied = assert.rejects(mismatch, /invalid recovery result/)
  f.last().event({ event: 'backup_inspection', engine_version: '0.0.0', inspection })
  f.last().finish()
  await denied
})

test('excessive recovery output cancels the helper without reporting success or stopping the host', async t => {
  const f = fixture(t)
  await running(f)
  const work = f.host.runBackup('backup', { workspace_id: addressChange.workspace_id })
  const denied = assert.rejects(work, /too large/)
  f.last().stdout.write(Buffer.alloc(1024 * 1024 + 1, 32))
  assert.equal(f.host.status.backup.state, 'cancelling')
  assert.equal(f.host.status.state, 'running')
  f.last().finish()
  await denied
  assert.equal(f.host.status.backup.state, 'error')
})

test('a recovery click waits for the welcome screen status refresh before starting its helper', async t => {
  const f = fixture(t)
  const status = f.host.inspect()
  const work = f.host.runBackup('backup-inspect', { source: '/separate/ledger.enc' })
  assert.equal(f.last().action, 'status')
  f.last().reply(info('first'))
  await status
  await settle()
  assert.equal(f.last().action, 'backup-inspect')
  f.last().event({ event: 'backup_inspection', engine_version: version, inspection: {
    kind: 'ledger', key_id: 'a'.repeat(24), encrypted_bytes: 100, sha256: 'b'.repeat(64),
    authenticated: true, ledger_at: new Date().toISOString(), tenant_count: 1, deletion_count: 1,
  } })
  f.last().finish()
  assert.equal((await work).authenticated, true)
})

test('remote changes drain the old host before writing and reopen the same local workspace', async t => {
  const f = fixture(t)
  const engine = await running(f)
  const changed = f.host.changeRemote(sharingChange)
  f.last().reply(sharingInfo())
  await settle()
  assert.equal(f.host.status.state, 'stopping')
  assert.equal(f.host.busy, true)
  assert.equal(f.commands.filter(command => command.action === 'remote').length, 0)
  engine.finish()
  await settle()
  assert.equal(f.last().action, 'remote')
  f.last().reply(sharingInfo(savedSharingRevision, 'proxy'))
  const result = await changed
  assert.equal(result.state, 'starting')
  assert.equal(result.info.settings.workspace_id, sharingChange.workspace_id)
  assert.equal(f.commands.filter(command => command.action === 'run').length, 2)
  assert.equal(result.info.remote_access.revision, savedSharingRevision)
})

test('an explicit stop during a remote settings change prevents its automatic reopen', async t => {
  const f = fixture(t)
  const engine = await running(f)
  const changed = f.host.changeRemote(sharingChange)
  f.last().reply(sharingInfo())
  await settle()
  const stopped = f.host.stop()
  engine.finish()
  await settle()
  assert.equal(f.last().action, 'remote')
  f.last().reply(sharingInfo(savedSharingRevision, 'proxy'))
  await changed
  assert.equal(await stopped, true)
  assert.equal(f.host.status.state, 'stopped')
  assert.equal(f.commands.filter(command => command.action === 'run').length, 1)
})

test('a stale remote form cannot stop the running host or overwrite another operator', async t => {
  const f = fixture(t)
  await running(f)
  const changed = f.host.changeRemote(sharingChange)
  const refused = assert.rejects(changed, /settings changed/)
  f.last().reply(sharingInfo(savedSharingRevision, 'proxy'))
  await refused
  assert.equal(f.host.status.state, 'running')
  assert.equal(f.commands.filter(command => command.action === 'remote').length, 0)
})

test('company setup drains the same host and reopens only after a confirmed private save', async t => {
  const f = fixture(t)
  const engine = await running(f)
  const change = f.host.changeCompany(companyChange)
  f.last().reply(companyInfo())
  await settle()
  assert.equal(f.host.status.state, 'stopping')
  assert.equal(f.commands.filter(command => command.action === 'company').length, 0)
  engine.finish(); await settle()
  assert.equal(f.last().action, 'company')
  f.last().reply(savedCompanyInfo())
  const result = await change
  assert.equal(result.state, 'starting')
  assert.equal(result.info.settings.workspace_id, addressChange.workspace_id)
  assert.equal(result.info.company_access.providers[0].has_client_secret, true)
  assert.ok(!JSON.stringify(result).includes(companyChange.client_secret))
  assert.equal(f.commands.filter(command => command.action === 'run').length, 2)
})

test('vault setup drains the host and reopens after the private key save without disclosing it', async t => {
  const f = fixture(t)
  const engine = await running(f)
  const change = f.host.changeVault(vaultChange)
  f.last().reply(vaultInfo()); await settle()
  assert.equal(f.host.status.state, 'stopping')
  assert.equal(f.commands.filter(command => command.action === 'vault').length, 0)
  engine.finish(); await settle()
  assert.equal(f.last().action, 'vault')
  f.last().reply(vaultInfo(true))
  const result = await change
  assert.equal(result.state, 'starting')
  assert.equal(result.info.vault_access.key_id, vaultKeyId(vaultKey))
  assert.ok(!JSON.stringify(result).includes(vaultKey))
  assert.equal(f.commands.filter(command => command.action === 'run').length, 2)
})

test('stale vault settings cannot stop the host or replace another operator key', async t => {
  const f = fixture(t)
  await running(f)
  const refused = assert.rejects(f.host.changeVault(vaultChange), /settings changed/)
  f.last().reply(vaultInfo(true)); await refused
  assert.equal(f.host.status.state, 'running')
  assert.equal(f.commands.filter(command => command.action === 'vault').length, 0)
})

test('explicit stop waits for vault key configuration and prevents automatic reopen', async t => {
  const f = fixture(t)
  const engine = await running(f)
  const change = f.host.changeVault(vaultChange)
  f.last().reply(vaultInfo()); await settle()
  const stop = f.host.stop()
  engine.finish(); await settle()
  f.last().reply(vaultInfo(true))
  await change
  assert.equal(await stop, true)
  assert.equal(f.host.status.state, 'stopped')
  assert.equal(f.commands.filter(command => command.action === 'run').length, 1)
})

test('explicit key recovery verifies the current workspace and never enters host status', async t => {
  const f = fixture(t)
  await running(f)
  const request = { workspace_id: addressChange.workspace_id, expected_revision: vaultRevision }
  const key = { workspace_id: request.workspace_id, revision: vaultRevision, key_id: vaultKeyId(vaultKey), recovery_key: vaultKey }
  const reveal = f.host.revealVaultKey(request)
  assert.equal(f.last().action, 'vault-key')
  f.last().reply({ event: 'vault_key', engine_version: version, key })
  assert.deepEqual(await reveal, key)
  assert.ok(!JSON.stringify(f.host.status).includes(vaultKey))
  const refused = assert.rejects(f.host.revealVaultKey(request), /could not be verified/)
  f.last().reply({ event: 'vault_key', engine_version: version, key: { ...key, workspace_id: savedSharingRevision } })
  await refused
  assert.equal(f.host.status.state, 'running')
})

test('a changed company or HTTPS revision cannot stop a running host', async t => {
  const f = fixture(t)
  await running(f)
  for (const observed of [savedCompanyInfo(), { ...companyInfo(), remote_access: sharing('00000000-0000-4000-8000-000000000011', 'proxy') }]) {
    const refused = assert.rejects(f.host.changeCompany(companyChange), /settings changed/)
    f.last().reply(observed)
    await refused
    assert.equal(f.host.status.state, 'running')
    assert.equal(f.commands.filter(command => command.action === 'company').length, 0)
  }
})

test('an explicit stop waits for company settings and prevents automatic reopen', async t => {
  const f = fixture(t)
  const engine = await running(f)
  const change = f.host.changeCompany(companyChange)
  f.last().reply(companyInfo()); await settle()
  const stop = f.host.stop()
  engine.finish(); await settle()
  f.last().reply(savedCompanyInfo())
  await change
  assert.equal(await stop, true)
  assert.equal(f.host.status.state, 'stopped')
  assert.equal(f.commands.filter(command => command.action === 'run').length, 1)
})

test('unconfirmed company configuration cannot replace the known settings', async t => {
  const f = fixture(t)
  const inspect = f.host.inspect(); f.last().reply(companyInfo()); await inspect
  const refused = assert.rejects(f.host.changeCompany(companyChange), /could not be confirmed/)
  f.last().reply(companyInfo()); await settle()
  f.last().reply(companyInfo('00000000-0000-4000-8000-000000000010', [{ ...companyProvider, client_id: 'different-client', has_client_secret: true }]))
  await refused
  assert.deepEqual(f.host.status.info.company_access.providers, [])
})

test('company discovery retains a running host, binds the reply and excludes overlapping writes', async t => {
  const f = fixture(t)
  await running(f)
  const request = { workspace_id: companyChange.workspace_id, expected_revision: 'not-configured', expected_remote_revision: savedSharingRevision, issuer: companyProvider.issuer }
  const discovery = f.host.discoverCompany(request)
  assert.equal(f.last().action, 'company-discover')
  await assert.rejects(f.host.changeCompany(companyChange), /operation/)
  const result = { ...request, authorization_url: companyProvider.authorization_url, token_url: companyProvider.token_url, jwks_url: companyProvider.jwks_url }
  f.last().reply({ event: 'company_discovery', engine_version: version, discovery: result })
  assert.deepEqual(await discovery, result)
  assert.equal(f.host.status.state, 'running')
  assert.equal(f.commands.filter(command => command.action === 'run').length, 1)
  const refused = assert.rejects(f.host.discoverCompany(request), /current request/)
  f.last().reply({ event: 'company_discovery', engine_version: version, discovery: { ...result, expected_revision: savedSharingRevision } })
  await refused
})

test('a company setup click waits for the harmless readiness inspection after restart', async t => {
  const f = fixture(t)
  await running(f)
  const inspect = f.host.inspect()
  const request = { workspace_id: companyChange.workspace_id, expected_revision: 'not-configured', expected_remote_revision: savedSharingRevision, issuer: companyProvider.issuer }
  const discovery = f.host.discoverCompany(request)
  assert.equal(f.last().action, 'status')
  f.last().reply(companyInfo()); await inspect; await settle()
  assert.equal(f.last().action, 'company-discover')
  f.last().reply({ event: 'company_discovery', engine_version: version, discovery: { ...request, authorization_url: companyProvider.authorization_url, token_url: companyProvider.token_url, jwks_url: companyProvider.jwks_url } })
  await discovery
  assert.equal(f.host.status.state, 'running')
})

test('private check requests use the current workspace and never restart its engine', async t => {
  const f = fixture(t)
  await running(f)
  const inspection = f.host.inspect()
  f.last().reply(sharingInfo(savedSharingRevision, 'proxy'))
  await inspection
  const checked = f.host.checkRemote({ workspace_id: sharingChange.workspace_id, expected_revision: savedSharingRevision })
  assert.equal(f.last().action, 'remote-check')
  f.last().reply(sharingInfo(savedSharingRevision, 'proxy'))
  await checked
  assert.equal(f.host.status.state, 'running')
  assert.equal(f.commands.filter(command => command.action === 'run').length, 1)
  await assert.rejects(f.host.checkRemote({ workspace_id: sharingChange.workspace_id, expected_revision: 'not-configured' }), /settings changed/)
})

test('remote saved connections do not start or inspect a local engine', async t => {
  const f = fixture(t)
  await f.host.prepareSavedConnection('https://memory.example.test', addressChange.workspace_id, true)
  assert.deepEqual(f.commands, [])
})

test('a paused managed host preserves the operator choice before saved authentication', async t => {
  const f = fixture(t)
  const prepared = f.host.prepareSavedConnection('http://127.0.0.1:17400', '00000000-0000-4000-8000-000000000003', false)
  const denied = assert.rejects(prepared, /paused/)
  f.last().reply(addressInfo(17400))
  await denied
  assert.deepEqual(f.commands.map(command => command.action), ['status'])
})

test('saved authentication waits for verified local readiness and the correct tenant', async t => {
  const f = fixture(t)
  let ready = false
  const prepared = f.host.prepareSavedConnection('http://127.0.0.1:17400', '00000000-0000-4000-8000-000000000003', true).then(() => { ready = true })
  f.last().reply(addressInfo(17400))
  await settle()
  f.last().reply(addressInfo(17400))
  await settle()
  const engine = f.last()
  assert.equal(engine.action, 'run')
  assert.equal(ready, false)
  engine.event({ event: 'ready', endpoint: 'http://127.0.0.1:17400', credential: 'mnm_' + 'a'.repeat(48),
    workspace_id: addressChange.workspace_id, tenant_id: '00000000-0000-4000-8000-000000000003', engine_version: version })
  f.last().reply(addressInfo(17400))
  await prepared
  assert.equal(ready, true)
  const wrongTenant = f.host.prepareSavedConnection('http://127.0.0.1:17400', addressChange.workspace_id, true)
  const denied = assert.rejects(wrongTenant, /another workspace/)
  f.last().reply(addressInfo(17400))
  await denied
})

test('closing during inspection prevents a delayed workspace start', async t => {
  const f = fixture(t)
  const rejected = assert.rejects(f.host.start(), /closing|stopping/)
  assert.equal(f.host.active, true)
  assert.equal(f.host.busy, true)
  const close = f.host.close()
  f.last().reply(info('first'))
  assert.equal(await close, true)
  await rejected
  assert.deepEqual(f.commands.map(command => command.action), ['status'])
  assert.equal(f.host.active, false)
  await assert.rejects(f.host.inspect(), /closing/)
})

test('a stopped local address change is bounded and cannot accept a listener host', () => {
  assert.deepEqual(portOptions(addressChange), addressChange)
  for (const change of [{ host: '0.0.0.0' }, { port: true }, { port: '7893' }, { port: 80 }, { port: 65536 }, { workspace_id: 'not-a-workspace' }]) {
    assert.throws(() => portOptions({ ...addressChange, ...change }), /valid local address/)
  }
})

test('an address save blocks startup and another writer and finishes before an update stop', async t => {
  const f = fixture(t)
  const change = f.host.changePort(addressChange)
  assert.equal(f.last().action, 'port')
  assert.equal(f.host.busy, true)
  await assert.rejects(f.host.start(), /address is being saved/)
  await assert.rejects(f.host.changeMemory({ mode: 'auto', limit_mib: null }), /address is being saved/)
  await assert.rejects(f.host.changePort(addressChange), /wait for other changes/)
  let finished = false
  const stop = f.host.stopForUpdate().then(result => { finished = true; return result })
  await settle()
  assert.equal(finished, false)
  f.last().reply(addressInfo(17402))
  assert.equal((await change).info.settings.port, 17402)
  assert.equal(await stop, true)
  await f.host.cancelUpdateStop()
  assert.equal(f.host.status.state, 'stopped')
  assert.deepEqual(f.commands.map(command => command.action), ['port'])
})

test('a running local workspace refuses an address change', async t => {
  const f = fixture(t)
  await running(f)
  await assert.rejects(f.host.changePort(addressChange), /Pause the local workspace/)
  assert(!f.commands.some(command => command.action === 'port'))
})

test('a runtime failure remains busy until process cleanup finishes, then permits address repair', async t => {
  const f = fixture(t)
  const engine = await running(f)
  engine.event({ event: 'error', code: 'port_in_use', message: 'Another program is using this workspace address.' })
  assert.equal(f.host.status.state, 'stopping')
  assert.equal(f.host.busy, true)
  await assert.rejects(f.host.changePort(addressChange), /Pause the local workspace/)
  assert(!f.commands.some(command => command.action === 'port'))
  engine.finish()
  f.last().reply(addressInfo(17400))
  await settle()
  assert.equal(f.host.status.state, 'error')
  assert.equal(f.host.status.errorCode, 'port_in_use')
  assert.equal(f.host.busy, false)
  const repaired = f.host.changePort(addressChange)
  f.last().reply(addressInfo(17402))
  const status = await repaired
  assert.equal(status.state, 'stopped')
  assert.equal(status.info.settings.port, 17402)
  assert.equal(status.errorCode, undefined)
})

test('inspection waits for an address save before reading the current settings', async t => {
  const f = fixture(t)
  const change = f.host.changePort(addressChange)
  const inspection = f.host.inspect()
  await settle()
  assert.deepEqual(f.commands.map(command => command.action), ['port'])
  f.last().reply(addressInfo(17402))
  await change
  await settle()
  assert.deepEqual(f.commands.map(command => command.action), ['port', 'status'])
  f.last().reply(addressInfo(17402))
  assert.equal((await inspection).settings.port, 17402)
})

test('a closing app drains an address save and refuses later mutations', async t => {
  const f = fixture(t)
  const change = f.host.changePort({ ...addressChange, port: 17402 })
  const close = f.host.close()
  await assert.rejects(f.host.changePort(addressChange), /closing|stopping/)
  f.last().reply(addressInfo(17402))
  await change
  assert.equal(await close, true)
  assert.equal(f.host.active, false)
})

test('an unconfirmed address response cannot replace the displayed workspace settings', async t => {
  const f = fixture(t)
  const inspect = f.host.inspect()
  f.last().reply(addressInfo(17400))
  await inspect
  const rejected = assert.rejects(f.host.changePort({ ...addressChange, port: 17402 }), /could not be confirmed/)
  f.last().reply({ ...addressInfo(17402), settings: { workspace_id: '00000000-0000-4000-8000-000000000002', port: 17402, database_port: 17401 } })
  await rejected
  assert.equal(f.host.status.info.settings.port, 17400)
  assert.equal(f.host.status.info.settings.workspace_id, addressChange.workspace_id)
})

test('an update stop waits for an in-flight RAM save and blocks later changes', async t => {
  const f = fixture(t)
  const save = f.host.changeMemory({ mode: 'manual', limit_mib: 512, expected_revision: 'first' })
  f.last().reply(info('first'))
  await settle()
  assert.equal(f.last().action, 'memory')
  assert.equal(f.host.busy, true)
  await assert.rejects(f.host.changeMemory({ mode: 'auto', limit_mib: null }), /already being saved/)
  let stopped = false
  const stop = f.host.stop().then(value => { stopped = true; return value })
  await settle()
  assert.equal(stopped, false)
  await assert.rejects(f.host.start(), /stopping/)
  f.last().reply({ event: 'memory_policy', policy: policy('second') })
  assert.equal((await save).info.memory_policy.revision, 'second')
  assert.equal(await stop, true)
  assert.equal(f.host.active, false)
  assert.equal(f.host.busy, false)
})

test('closing while a RAM change waits for inspection never launches the writer', async t => {
  const f = fixture(t)
  const rejected = assert.rejects(f.host.changeMemory({ mode: 'auto', limit_mib: null }), /closing|stopping/)
  const close = f.host.close()
  f.last().reply(info('first'))
  assert.equal(await close, true)
  await rejected
  assert.deepEqual(f.commands.map(command => command.action), ['status'])
})

test('a timed-out close retains access and allows restarting after the engine finishes', async t => {
  const f = fixture(t)
  const engine = await running(f)
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const close = f.host.close()
  await settle()
  t.mock.timers.tick(90_000)
  assert.equal(await close, false)
  const inspect = f.host.inspect()
  f.last().reply(info('first'))
  await inspect
  engine.finish()
  f.last().reply(info('first'))
  await settle()
  const restart = f.host.start()
  f.last().reply(info('first'))
  assert.equal((await restart).state, 'starting')
  assert.equal(f.commands.filter(command => command.action === 'run').length, 2)
})

test('agent RAM changes refresh the policy revision and coalesce status reads', async t => {
  const f = fixture(t)
  const engine = await running(f)
  const before = f.commands.length
  const memory = { revision: 'second', enforcement: 'cooperative', scope: 'local_engine_database_and_reported_desktop',
    state: 'normal', target_bytes: 512, used_bytes: 100, engine_bytes: 60, database_bytes: 20, desktop_bytes: 20,
    effective_hardware_bytes: 4096, available_hardware_bytes: 2048 }
  engine.event({ event: 'resources', memory })
  engine.event({ event: 'resources', memory })
  assert.equal(f.commands.length, before + 1)
  f.last().reply(info('second'))
  await settle()
  assert.equal(f.host.status.info.memory_policy.revision, 'second')
  engine.event({ event: 'resources', memory })
  assert.equal(f.commands.length, before + 1)
})

const damaged = token => ({ ...info('first'), memory_policy: null, memory_recovery: {
  code: 'memory_policy_damaged', message: 'The saved RAM policy cannot be understood.', repair_token: token,
} })

test('damaged RAM status stays inspectable and blocks startup until explicit repair', async t => {
  const f = fixture(t)
  const start = assert.rejects(f.host.start(), /Repair the saved RAM budget/)
  f.last().reply(damaged('a'.repeat(64)))
  await start
  assert.equal(f.host.status.info.configured, true)
  assert.equal(f.host.status.info.memory_recovery.repair_token, 'a'.repeat(64))
  assert.deepEqual(f.commands.map(command => command.action), ['status'])
  const save = f.host.changeMemory({ mode: 'manual', limit_mib: 512, repair_token: 'a'.repeat(64) })
  f.last().reply(damaged('a'.repeat(64)))
  await settle()
  assert.equal(f.last().action, 'memory-repair')
  f.last().reply({ event: 'memory_policy', policy: policy('repaired') })
  assert.equal((await save).info.memory_recovery, null)
  assert.equal(f.host.status.info.memory_policy.revision, 'repaired')
})

test('an update stop waits for an explicit repair just as for an ordinary RAM save', async t => {
  const f = fixture(t)
  const save = f.host.changeMemory({ mode: 'manual', limit_mib: 512, repair_token: 'a'.repeat(64) })
  f.last().reply(damaged('a'.repeat(64)))
  await settle()
  assert.equal(f.last().action, 'memory-repair')
  let stopped = false
  const stop = f.host.stop().then(value => { stopped = true; return value })
  await settle()
  assert.equal(stopped, false)
  f.last().reply({ event: 'memory_policy', policy: policy('repaired') })
  await save
  assert.equal(await stop, true)
  assert.equal(f.host.busy, false)
})

test('stale repair reports the conflict and refreshing exposes the new policy state', async t => {
  const f = fixture(t)
  const save = assert.rejects(f.host.changeMemory({ mode: 'auto', limit_mib: null, repair_token: 'a'.repeat(64) }), /changed after inspection/)
  f.last().reply(damaged('b'.repeat(64)))
  await settle()
  f.last().reply({ event: 'error', code: 'memory_policy_changed', message: 'The RAM policy changed after inspection. Refresh before repairing it.' })
  await save
  const refresh = f.host.inspect()
  f.last().reply(info('restored'))
  assert.equal((await refresh).memory_policy.revision, 'restored')
  assert.equal(f.host.status.info.memory_recovery, undefined)
})

test('live policy damage is detected even when the last valid revision has not changed', async t => {
  const f = fixture(t)
  const engine = await running(f)
  const memory = { revision: 'first', reason: 'policy_unavailable', enforcement: 'cooperative', scope: 'local_engine_database_and_reported_desktop',
    state: 'paused', target_bytes: 512, used_bytes: 100, engine_bytes: 60, database_bytes: 20, desktop_bytes: 20,
    effective_hardware_bytes: 4096, available_hardware_bytes: 2048 }
  const before = f.commands.length
  engine.event({ event: 'resources', memory })
  assert.equal(f.commands.length, before + 1)
  f.last().reply(damaged('a'.repeat(64)))
  await settle()
  assert.equal(f.host.status.info.memory_recovery.code, 'memory_policy_damaged')
  engine.event({ event: 'resources', memory })
  assert.equal(f.commands.length, before + 1)
})

test('repair rejects invalid tokens and conflicting revision fields before spawning', async t => {
  const f = fixture(t)
  for (const extra of [{ repair_token: 'bad' }, { repair_token: 'a'.repeat(64), expected_revision: 'first' }]) {
    await assert.rejects(f.host.changeMemory({ mode: 'auto', limit_mib: null, ...extra }), /Choose automatic/)
  }
  assert.equal(f.commands.length, 0)
})

test('cancelling an update preserves a workspace that was already paused', async t => {
  const f = fixture(t)
  const inspect = f.host.inspect()
  f.last().reply(info('first'))
  await inspect
  assert.equal(await f.host.stopForUpdate(), true)
  await f.host.cancelUpdateStop()
  assert.deepEqual(f.commands.map(command => command.action), ['status'])
})

test('failed host shutdown blocks updates and keeps its diagnostic until a clean restart and stop', async t => {
  const f = fixture(t)
  const engine = await running(f)
  const stop = f.host.stopForUpdate()
  await settle()
  engine.event({ event: 'error', code: 'database_identity', message: 'The database process changed; it was not stopped.' })
  engine.finish(1)
  assert.equal(await stop, false)
  assert.equal(f.host.status.state, 'error')
  assert.equal(f.host.status.errorCode, 'database_identity')
  if (f.last().action === 'status') f.last().reply(info('first'))
  await settle()
  assert.equal(await f.host.stopForUpdate(), false)
  const restarted = await running(f)
  const clean = f.host.stop()
  await settle(); restarted.finish()
  assert.equal(await clean, true)
  assert.equal(f.host.status.state, 'stopped')
})

test('an unexplained nonzero exit cannot confirm an intentional database stop', async t => {
  const f = fixture(t)
  const engine = await running(f)
  const stop = f.host.stop()
  await settle(); engine.finish(1)
  assert.equal(await stop, false)
  assert.equal(f.host.status.state, 'error')
})

test('cancelling an update reopens its previously running workspace exactly once', async t => {
  const f = fixture(t)
  const engine = await running(f)
  const stop = f.host.stopForUpdate()
  await settle()
  engine.finish()
  assert.equal(await stop, true)
  const resume = f.host.cancelUpdateStop()
  const duplicate = f.host.cancelUpdateStop()
  f.last().reply(info('first'))
  await Promise.all([resume, duplicate])
  assert.equal(f.commands.filter(command => command.action === 'run').length, 2)
})

test('a cancelled update resumes after a slow stop, unless the user explicitly stops it', async t => {
  for (const explicitStop of [false, true]) {
    const f = fixture(t)
    const engine = await running(f)
    t.mock.timers.enable({ apis: ['setTimeout'] })
    const stop = f.host.stopForUpdate()
    await settle()
    t.mock.timers.tick(90_000)
    assert.equal(await stop, false)
    t.mock.timers.reset()
    await f.host.cancelUpdateStop()
    const userStop = explicitStop ? f.host.stop() : null
    await settle()
    engine.finish()
    if (userStop) await userStop
    if (f.last().action === 'status') f.last().reply(info('first'))
    await settle()
    if (f.last().action === 'status' && !f.last().closed) f.last().reply(info('first'))
    await settle()
    assert.equal(f.commands.filter(command => command.action === 'run').length, explicitStop ? 1 : 2)
    for (const command of f.commands) command.finish()
    await f.host.close()
  }
})
