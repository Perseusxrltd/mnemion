import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isolatedPreviewDiagnostic } from '../dist/native-capture-diagnostics.js'

test('the isolated preview diagnostic redacts environment values before its output bound', () => {
  const credential = 'fixture-secret-' + 'a'.repeat(900)
  const output = isolatedPreviewDiagnostic('native loader: ' + credential + ' failed', { TOKEN: credential }, [])
  assert.match(output, /native loader:/)
  assert.match(output, /failed/)
  assert.ok(!output.includes('fixture-secret'))
  assert.ok(output.length <= 600)
})

test('the isolated preview diagnostic removes credentials, URLs and private native paths', () => {
  const output = isolatedPreviewDiagnostic(
    'warning Bearer small-secret https://name:password@example.test/api /Users/Private/Library/runtime.dylib C:\\Users\\Private\\runtime.dll mnm_examplekey',
    {}, [],
  )
  for (const hidden of ['small-secret', 'password', 'example.test', 'Private', 'runtime.dylib', 'runtime.dll', 'mnm_examplekey']) {
    assert.ok(!output.includes(hidden), hidden)
  }
  assert.match(output, /warning/)
})

test('the isolated preview diagnostic removes terminal control codes and private fixture values', () => {
  const output = isolatedPreviewDiagnostic('\x1b[31mloader failed\x1b[0m\n\x00fixture-identifier', {}, ['fixture-identifier'])
  assert.match(output, /loader failed/)
  assert.ok(!output.includes('fixture-identifier'))
  assert.ok(!/[\x00-\x1f\x7f]/.test(output))
})

test('the isolated preview diagnostic bounds unknown native messages and opaque values', () => {
  const output = isolatedPreviewDiagnostic('native warning: ' + 'b'.repeat(64) + ' '.repeat(700), {}, [])
  assert.ok(output.length <= 600)
  assert.ok(!output.includes('b'.repeat(40)))
  assert.match(output, /native warning:/)
})
