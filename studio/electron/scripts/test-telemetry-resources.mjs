import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { copyTelemetryResources, telemetryResourceEntries } from './telemetry-resources.mjs'
import { telemetryWireResource } from '../dist/telemetry-resources.js'

const source = resolve(dirname(fileURLToPath(import.meta.url)), '../../../mnemion/product_telemetry')
function directory(t) {
  const path = mkdtempSync(join(tmpdir(), 'mnemion-telemetry-resources-'))
  t.after(() => rmSync(path, { recursive: true, force: true }))
  return path
}

test('a clean telemetry build supplies every resource required for packaging and sending', t => {
  const destination = directory(t)
  copyTelemetryResources(source, destination)
  const entries = telemetryResourceEntries(destination)
  assert.deepEqual(entries.filter(item => !existsSync(item.path)), [])
  assert.ok(entries.some(item => item.path === join(destination, telemetryWireResource)))
  const wire = JSON.parse(readFileSync(join(destination, telemetryWireResource), 'utf8'))
  assert.equal(telemetryWireResource, `telemetry-wire-v${wire.version}.json`)
})

test('a retired wire file cannot satisfy the active packaged-resource requirement', t => {
  const destination = directory(t)
  copyTelemetryResources(source, destination)
  rmSync(join(destination, telemetryWireResource))
  writeFileSync(join(destination, 'telemetry-wire-v0.json'), '{}')
  assert.deepEqual(telemetryResourceEntries(destination).filter(item => !existsSync(item.path))
    .map(item => item.path), [join(destination, telemetryWireResource)])
})

test('incremental builds remove retired wire formats and preserve unrelated resources', t => {
  const destination = directory(t)
  writeFileSync(join(destination, 'telemetry-wire-v0.json'), '{}')
  writeFileSync(join(destination, 'unrelated.json'), 'preserved')
  copyTelemetryResources(source, destination)
  assert.equal(existsSync(join(destination, 'telemetry-wire-v0.json')), false)
  assert.equal(existsSync(join(destination, telemetryWireResource)), true)
  assert.equal(readFileSync(join(destination, 'unrelated.json'), 'utf8'), 'preserved')
})
