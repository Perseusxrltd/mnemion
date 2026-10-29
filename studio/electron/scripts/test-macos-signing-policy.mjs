import assert from 'node:assert/strict'
import { test } from 'node:test'
import { validateAdhocLaunchPolicy } from './macos-signing-policy.mjs'

const signature = 'CodeDirectory v=20500 size=900 flags=0x10002(adhoc,runtime) hashes=1+7 location=embedded\nSignature=adhoc\nTeamIdentifier=not set\n'
const entitlements = { 'com.apple.security.cs.allow-jit': true, 'com.apple.security.cs.disable-library-validation': true }

test('a valid on-disk signature alone does not qualify an ad-hoc Electron launch', () => {
  assert.throws(() => validateAdhocLaunchPolicy(signature, { 'com.apple.security.cs.allow-jit': true }), /library-validation/)
  assert.equal(validateAdhocLaunchPolicy(signature, entitlements).hardened_runtime, true)
})

test('Mac launch compatibility cannot silently turn off hardened runtime or add entitlements', () => {
  for (const description of [signature.replace('adhoc,runtime', 'adhoc'), signature.replace('Signature=adhoc', 'Signature=unknown'),
    signature.replace('TeamIdentifier=not set', 'TeamIdentifier=EXAMPLE'), signature + 'x'.repeat(65536)]) {
    assert.throws(() => validateAdhocLaunchPolicy(description, entitlements), /hardened runtime/)
  }
  for (const value of [null, [], {}, { ...entitlements, 'com.apple.security.get-task-allow': true },
    { ...entitlements, 'com.apple.security.cs.allow-jit': 'true' },
    { ...entitlements, 'com.apple.security.cs.disable-library-validation': false }]) {
    assert.throws(() => validateAdhocLaunchPolicy(signature, value), /reviewed/)
  }
})
