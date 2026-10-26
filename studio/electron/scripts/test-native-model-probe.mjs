import assert from 'node:assert/strict'
import { test } from 'node:test'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { createConnection } from 'node:net'
import { verifyNativeModels } from '../dist/native-model-probe.js'
import { ModelSetupFailure, modelSetupDiagnostic, modelSetupFailure } from '../dist/native-model-diagnostics.js'

const secret = 'PRIVATE_FIXTURE_CREDENTIAL_https://private.invalid/team'
const engine = { category: 'database', database_reason: 'connection_closed', locations: [
  { module: 'mnemion.local_database', function: 'provision', line: 361 },
] }

test('model setup artifacts retain only closed phases, conditions and validated engine diagnostics', () => {
  const report = new ModelSetupFailure('save_embedding', 'restart_error', {
    state: 'stopping', stage: 'access', diagnostic: engine, message: secret,
  })
  assert.deepEqual(modelSetupFailure(String(report)), report.diagnostic)
  assert.ok(!String(report).includes(secret))
  for (const key of Object.keys(report.diagnostic)) {
    for (const value of [secret, { text: secret }, [secret], null]) {
      const changed = { ...report.diagnostic, [key]: value }
      assert.throws(() => modelSetupDiagnostic(changed))
      assert.equal(modelSetupFailure('Error: Installed model setup failed: ' + JSON.stringify(changed)), undefined)
    }
  }
  assert.equal(modelSetupFailure(String(report) + '\n' + secret), undefined)
  assert.equal(modelSetupFailure('Error: Installed model setup failed: ' + JSON.stringify({ ...report.diagnostic, message: secret })), undefined)
})

async function fixture(t, failAt) {
  const directory = await mkdtemp(join(tmpdir(), 'mnemion-model-probe-test-'))
  t.after(() => rm(directory, { recursive: true, force: true }))
  const providers = []
  const actions = []
  let stopped = false
  let origin
  const status = () => ({ state: stopped ? 'stopping' : 'running', stage: stopped ? 'access' : 'ready',
    ...(stopped ? { errorCode: 'setup_failed', message: secret, diagnostic: engine } : {}),
    info: { data_directory: directory, settings: { workspace_id: '11111111-1111-4111-8111-111111111111' },
      model_access: { revision: String(actions.length), providers: providers.map(({ api_key, ...provider }) => ({ ...provider, has_api_key: !!api_key })) } },
  })
  const call = async (action, input) => {
    if (action === 'status') return status()
    assert.equal(action, 'local.models')
    actions.push(input.action)
    if (input.action === 'save') {
      origin = new URL(input.provider.profile.endpoint).origin
      providers.push({ ...input.provider, api_key: input.api_key })
      if (failAt === 'restart') stopped = true
    } else {
      if (failAt === 'restart' || failAt === 'cleanup') throw new Error('Cleanup hid the earlier error: ' + secret)
      const index = providers.findIndex(provider => provider.profile.id === input.profile_id)
      assert.notEqual(index, -1)
      if (failAt !== 'retained') providers.splice(index, 1)
    }
    await writeFile(join(directory, 'model-providers.json'), JSON.stringify({ providers }), { mode: 0o600 })
    return status()
  }
  const window = { webContents: { executeJavaScript: async script => {
    if (script === 'window.location.hash') return '/workspace/memories'
    if (script.includes('return {embedding:')) return {
      embedding: { profiles: providers.filter(p => p.kind === 'embedding').map(p => ({ id: p.profile.id, registered: true })) },
      librarian: { items: providers.filter(p => p.kind === 'librarian').map(p => ({ id: p.profile.id })) },
      settings: { enabled: false },
    }
    return true
  } } }
  return { window, call, actions, providers, origin: () => origin }
}

async function assertListenerClosed(origin) {
  const url = new URL(origin)
  const socket = createConnection({ host: url.hostname, port: Number(url.port) })
  try {
    const result = await new Promise(resolve => {
      socket.setTimeout(2000, () => resolve('timeout'))
      socket.once('connect', () => resolve('connected'))
      socket.once('error', error => resolve(error.code))
    })
    assert.equal(result, 'ECONNREFUSED')
  } finally { socket.destroy() }
}

test('the first startup error survives without another mutation or a cleanup timeout', { timeout: 5000 }, async t => {
  const f = await fixture(t, 'restart')
  await assert.rejects(verifyNativeModels(f.window, f.call), error => {
    const report = modelSetupFailure(String(error))
    assert.deepEqual(report, { phase: 'save_embedding', reason: 'restart_error', state: 'stopping', stage: 'access',
      cleanup: 'not_started', engineDiagnostic: engine })
    assert.ok(!String(error).includes(secret))
    return true
  })
  assert.deepEqual(f.actions, ['save'])
  await assertListenerClosed(f.origin())
})

test('successful enrollment still requires removing both private test profiles', { timeout: 5000 }, async t => {
  const f = await fixture(t)
  const result = await verifyNativeModels(f.window, f.call)
  assert.ok(Object.values(result).every(value => value === true))
  assert.deepEqual(f.actions, ['save', 'save', 'remove', 'remove'])
  assert.equal(f.providers.length, 0)
  await assertListenerClosed(f.origin())
})

test('cleanup failure fails the check and identifies its own step without exporting the error', { timeout: 5000 }, async t => {
  const f = await fixture(t, 'cleanup')
  await assert.rejects(verifyNativeModels(f.window, f.call), error => {
    assert.deepEqual(modelSetupFailure(String(error)), { phase: 'remove_embedding', reason: 'action_failed',
      state: 'running', stage: 'ready', cleanup: 'failed' })
    assert.ok(!String(error).includes(secret))
    return true
  })
  assert.deepEqual(f.actions, ['save', 'save', 'remove'])
  await assertListenerClosed(f.origin())
})

test('a removal acknowledgement cannot pass while its private test profiles remain', { timeout: 5000 }, async t => {
  const f = await fixture(t, 'retained')
  await assert.rejects(verifyNativeModels(f.window, f.call), error => {
    const report = modelSetupFailure(String(error))
    assert.equal(report.reason, 'cleanup_profiles_remain')
    assert.equal(report.cleanup, 'failed')
    return true
  })
  assert.equal(f.providers.length, 2)
  await assertListenerClosed(f.origin())
})
