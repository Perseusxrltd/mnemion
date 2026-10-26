import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { test } from 'node:test'

function freshRuntime(source, internalBindings = false) {
  const result = spawnSync(process.execPath, [
    ...(internalBindings ? ['--expose-internals'] : []), '--input-type=module', '-e', source,
  ], { env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' }, encoding: 'utf8', timeout: 15000, maxBuffer: 256 * 1024 })
  assert.equal(result.status, 0, result.stderr || result.error?.message || result.stdout)
  return JSON.parse(result.stdout.trim())
}

test('loading the telemetry sender leaves the bundled TLS authorities unloaded', () => {
  const target = new URL('../dist/telemetry-transport.js', import.meta.url).href
  const result = freshRuntime(`
    import assert from 'node:assert/strict'
    import { createRequire } from 'node:module'
    const require = createRequire(import.meta.url)
    // A fresh child avoids a prior test's TLS cache. Node's internal test
    // binding observes the native getter; production never uses this hook.
    const binding = require('internal/test/binding').internalBinding('crypto')
    const original = binding.getBundledRootCertificates
    assert.equal(typeof original, 'function', 'The cold-import hook must be supported')
    let reads = 0
    binding.getBundledRootCertificates = function (...args) { reads++; return original.apply(this, args) }
    await import(${JSON.stringify(target)})
    const duringImport = reads
    assert.ok(require('node:tls').rootCertificates.length > 0)
    assert.equal(reads, 1, 'Explicit root access must validate the instrumentation')
    console.log(JSON.stringify({ bundled_reads_during_import: duringImport, positive_control_reads: reads }))
    assert.equal(duringImport, 0, 'Telemetry import must not materialize the general certificate list')
  `, true)
  assert.equal(result.bundled_reads_during_import, 0)
  assert.equal(result.positive_control_reads, 1)
})

test('absent company policy avoids exceptions while every fresh restriction still applies', () => {
  const target = new URL('../dist/telemetry-store.js', import.meta.url).href
  const result = freshRuntime(`
    import assert from 'node:assert/strict'
    import { createRequire } from 'node:module'
    import { tmpdir } from 'node:os'
    import { join } from 'node:path'
    const require = createRequire(import.meta.url), fs = require('node:fs')
    const root = fs.mkdtempSync(join(tmpdir(), 'mnemion-policy-cold-'))
    const file = join(root, 'company.json'), lstat = fs.lstatSync
    let reads = 0, missingExceptions = 0
    fs.lstatSync = function (path, ...args) {
      if (path === file) reads++
      try { return lstat.call(this, path, ...args) }
      catch (error) { if (path === file && error.code === 'ENOENT') missingExceptions++; throw error }
    }
    try {
      const { NativeTelemetryStore, nativeTelemetryDefinitions } = await import(${JSON.stringify(target)})
      const { disclosure, catalog } = nativeTelemetryDefinitions()
      const store = new NativeTelemetryStore(root, disclosure, catalog, file)
      for (let i = 0; i < 32; i++) assert.deepEqual(store.company(), { enabled: true, groups: disclosure.metric_groups })
      const duringReads = missingExceptions
      assert.equal(reads, 32, 'Each policy check must still examine the current file')
      assert.throws(() => fs.lstatSync(file), { code: 'ENOENT' })
      assert.equal(missingExceptions, duringReads + 1, 'Explicit throwing stat validates the hook')
      fs.writeFileSync(file, JSON.stringify({ schema_version: 1, enabled: false, metric_groups: [] }))
      assert.deepEqual(store.company(), { enabled: false, groups: [] })
      fs.writeFileSync(file, '{broken')
      assert.deepEqual(store.company(), { enabled: false, groups: [] })
      fs.rmSync(file)
      fs.mkdirSync(file)
      assert.deepEqual(store.company(), { enabled: false, groups: [] })
      const blockedParent = join(root, 'not-a-directory')
      fs.writeFileSync(blockedParent, '')
      const blocked = new NativeTelemetryStore(root, disclosure, catalog, join(blockedParent, 'company.json'))
      assert.deepEqual(blocked.company(), { enabled: false, groups: [] }, 'ENOTDIR cannot become an absent policy')
      console.log(JSON.stringify({ missing_policy_reads: 32, missing_exceptions: duringReads, fresh_restrictions_applied: true }))
      assert.equal(duringReads, 0, 'Missing optional company policy must not allocate exceptions')
    } finally { fs.rmSync(root, { recursive: true, force: true }) }
  `)
  assert.equal(result.missing_exceptions, 0)
  assert.equal(result.fresh_restrictions_applied, true)
})
