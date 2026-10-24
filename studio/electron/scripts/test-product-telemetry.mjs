import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, rm, access } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import { ProductTelemetry } from '../dist/product-telemetry.js'
import { telemetryMessages } from '../dist/product-telemetry.js'
import { sourceProcess } from '../dist/desktop-source-process.js'

const repository = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const python = process.env.MNEMION_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3')

test('desktop controls and an independent native process retain the same offline opt-out', async () => {
  const temporary = await mkdtemp(join(tmpdir(), 'mnemion-telemetry-'))
  const root = join(temporary, 'private choice')
  const environment = { ...process.env, PYTHONPATH: repository, PYTHONNOUSERSITE: '1' }
  const control = new ProductTelemetry(sourceProcess({ executable: python,
    prefix: ['-m', 'mnemion.service.cli'], command: 'telemetry', root,
    privateRoots: [], environment, deadlineMs: 20000, messages: telemetryMessages }))
  try {
    const initial = await control.execute('telemetry.status')
    assert.equal(initial.effective_enabled, false)
    assert.equal(initial.reason, 'disclosure_required')
    await assert.rejects(access(root))
    const disabled = await control.execute('telemetry.configure', { enabled: false, expected_revision: 0 })
    assert.equal(disabled.reason, 'user_disabled')
    const observed = spawnSync(python, ['-m', 'mnemion.service.cli', 'telemetry', '--root', root], {
      input: JSON.stringify({ action: 'status' }), env: environment, encoding: 'utf8', timeout: 20000,
    })
    assert.equal(observed.status, 0, 'native status exited successfully')
    assert.equal(observed.stderr, '')
    assert.deepEqual(JSON.parse(observed.stdout).result, disabled)
    await assert.rejects(control.execute('telemetry.configure', { enabled: true, expected_revision: 0 }), /changed in another process/)
    const preview = await control.execute('telemetry.preview')
    assert.equal(preview.transport_available, false)
    assert.equal(preview.outbound_bytes, 0)
    assert.equal(preview.status.user_enabled, false)
  } finally { await rm(temporary, { recursive: true, force: true }) }
})

test('telemetry controls reject arbitrary action and payload before invoking a native helper', async () => {
  let calls = 0
  const control = new ProductTelemetry(async () => { calls++; return {} })
  await assert.rejects(control.execute('workspace.connect', {}), /documented product telemetry/)
  await assert.rejects(control.execute('telemetry.status', { api_key: 'PRIVATE_SENTINEL' }), /unsupported input fields/)
  assert.equal(calls, 0)
})
