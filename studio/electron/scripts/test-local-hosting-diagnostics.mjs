import assert from 'node:assert/strict'
import { test } from 'node:test'
import { workspaceOpenDiagnostic, workspaceOpenError, workspaceOpenFailure } from '../dist/local-hosting-diagnostics.js'

const fixture = { route: 'workspace', view: 'local_setup', localState: 'running', localSelected: 'no',
  authenticated: 'no', identityMatches: 'unknown', openControl: 'enabled', error: 'unreachable' }
const failure = value => 'Error: Installed workspace open failed: ' + JSON.stringify(value)
const secret = 'PRIVATE_SENTINEL_CREDENTIAL_https://private.invalid/workspace'

test('installed-open diagnostics distinguish authenticated initial-read failures from failed sign-in', () => {
  assert.deepEqual(workspaceOpenFailure(failure(fixture)), fixture)
  const authenticated = { ...fixture, view: 'error', authenticated: 'yes', identityMatches: 'yes', openControl: 'absent', error: 'timeout' }
  assert.deepEqual(workspaceOpenFailure(failure(authenticated)), authenticated)
  assert.notEqual(workspaceOpenFailure(failure(authenticated)).authenticated, fixture.authenticated)
})

test('arbitrary renderer fields, values, nesting and malformed reports never enter the public artifact', () => {
  for (const key of Object.keys(fixture)) {
    for (const replacement of [secret, { value: secret }, [secret], null, true, 99]) {
      const value = { ...fixture, [key]: replacement }
      assert.throws(() => workspaceOpenDiagnostic(value), error => !error.message.includes(secret))
      assert.equal(workspaceOpenFailure(failure(value)), undefined)
    }
    const missing = { ...fixture }; delete missing[key]
    assert.equal(workspaceOpenFailure(failure(missing)), undefined)
  }
  for (const value of [{ ...fixture, credential: secret }, [fixture], null, secret]) {
    assert.equal(workspaceOpenFailure(failure(value)), undefined)
  }
  for (const value of [failure(fixture) + '\n' + secret, 'Error: ' + secret, failure({ ...fixture, error: secret.repeat(500) })]) {
    assert.equal(workspaceOpenFailure(value), undefined)
  }
})

test('private error text becomes only a fixed classification, including through the renderer function source', () => {
  const inRenderer = Function('return (' + workspaceOpenError.toString() + ')')()
  for (const [message, expected] of [
    ['The workspace could not be reached. ' + secret, 'unreachable'],
    ['The workspace is not ready. ' + secret, 'not_ready'],
    ['This key is expired, revoked or does not grant workspace access. ' + secret, 'access'],
    ['This address did not return a Mnemion workspace identity. ' + secret, 'identity'],
    ['Another workspace connection was selected. ' + secret, 'selection'],
    ['Wait for the local workspace checks to finish before opening it. ' + secret, 'busy'],
    ['EPERM: ' + secret, 'file_access'],
    ['TimeoutError: ' + secret, 'timeout'],
    [secret, 'other'], ['', 'none'], [null, 'none'], [secret.repeat(500), 'other'],
  ]) {
    assert.equal(workspaceOpenError(message), expected)
    assert.equal(inRenderer(message), expected)
    assert.ok(!JSON.stringify(workspaceOpenFailure(failure({ ...fixture, error: inRenderer(message) }))).includes(secret))
  }
})
