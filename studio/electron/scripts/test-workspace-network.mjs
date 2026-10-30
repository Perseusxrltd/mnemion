import assert from 'node:assert/strict'
import test from 'node:test'
import { inspect } from 'node:util'
import { workspaceBoundaryFetch, workspaceNetworkFailure, workspaceSignInDeadline } from '../dist/workspace-network.js'

const secret = 'password-super-secret-value'
const signInUnknown = 'The workspace could not confirm this sign-in request. Check the connection and sign in again.'
const identityUnknown = 'The workspace could not be reached. Check its address and your network or VPN. If an agent hosts it, use the host’s operator controls to check that its computer and network connection are running.'

function coded(code, message = 'transport failure ' + secret) {
  return Object.assign(new Error(message), { code, hostname: secret, address: secret })
}

function safe(error) {
  assert.equal(error.cause, undefined)
  assert.equal(JSON.stringify(error).includes(secret), false)
  assert.equal(inspect(error).includes(secret), false)
  assert.equal(inspect(error).includes('PRIVATE_SENTINEL'), false)
  assert.equal(error.message.includes(secret), false)
  assert.equal(error.message.includes('PRIVATE_SENTINEL'), false)
  assert.ok(error.message.length > 20)
}

test('known transport codes select fixed classes and drop private details', () => {
  const cases = [
    [coded('ENOTFOUND'), 'sign-in', /address did not resolve/],
    [coded('CERT_HAS_EXPIRED'), 'sign-in', /server certificate and the device clock/],
    [coded('ERR_PROXY_CONNECTION_FAILED'), 'identity', /network proxy did not complete/],
    [coded('ETIMEDOUT'), 'sign-in', /timed out before it could be confirmed/],
    [coded('ECONNREFUSED'), 'identity', /refused, reset, or closed/],
    [coded('ERR_TOO_MANY_REDIRECTS'), 'sign-in', /redirect was refused/],
    [Object.assign(new TypeError('fetch failed'), { cause: coded('ENOTFOUND', 'getaddrinfo ENOTFOUND ' + secret) }), 'sign-in', /address did not resolve/],
    [new Error('net::ERR_CERT_AUTHORITY_INVALID'), 'identity', /server certificate and the device clock/],
    [Object.assign(new Error(secret), { name: 'ConnectTimeoutError' }), 'sign-in', /timed out before it could be confirmed/],
  ]
  for (const [input, boundary, pattern] of cases) {
    const error = workspaceNetworkFailure(input, boundary)
    assert.match(error.message, pattern)
    assert.doesNotMatch(error.message, /certificate checks off|turn certificate|disable/i)
    safe(error)
  }
  assert.equal(workspaceNetworkFailure(coded('ENOTFOUND'), 'sign-in').message.startsWith('The workspace could not confirm this sign-in request.'), true)
  assert.equal(workspaceNetworkFailure(coded('ECONNRESET'), 'identity').message.startsWith('The workspace could not be reached.'), true)
})

test('actual timeout shapes are recognized and unknown sign-in stays uncertain', () => {
  const timeout = workspaceNetworkFailure(new DOMException('PRIVATE_SENTINEL', 'TimeoutError'), 'sign-in')
  assert.match(timeout.message, /timed out before it could be confirmed/)
  safe(timeout)
  const named = workspaceNetworkFailure(Object.assign(new Error('The operation was aborted due to timeout ' + secret), { name: 'TimeoutError' }), 'identity')
  assert.match(named.message, /connection timed out/)
  safe(named)
  const aborted = workspaceNetworkFailure(new DOMException('PRIVATE_SENTINEL', 'AbortError'), 'sign-in')
  assert.equal(aborted.message, signInUnknown)
  safe(aborted)
  assert.equal(workspaceNetworkFailure(new Error(secret), 'sign-in').message, signInUnknown)
  assert.equal(workspaceNetworkFailure({ message: 'ENOTFOUND ' + secret }, 'identity').message, identityUnknown)
})

test('hostile and oversized errors cannot choose a class or escape', () => {
  const getter = workspaceNetworkFailure({ get code() { throw new Error('PRIVATE_SENTINEL_GETTER') } }, 'sign-in')
  assert.equal(getter.message, signInUnknown)
  safe(getter)
  const proxy = workspaceNetworkFailure(new Proxy({}, { get() { throw new Error('PRIVATE_SENTINEL_GETTER') } }), 'identity')
  assert.equal(proxy.message, identityUnknown)
  safe(proxy)
  const inherited = workspaceNetworkFailure({ name: 'constructor' }, 'sign-in')
  assert.equal(inherited.message, signInUnknown)
  safe(inherited)
  const errors = [coded('ENOTFOUND'), coded('ENOTFOUND'), coded('ENOTFOUND'), coded('ENOTFOUND'), coded('CERT_HAS_EXPIRED')]
  const mixed = workspaceNetworkFailure({ errors }, 'sign-in')
  assert.equal(mixed.message, signInUnknown)
  assert.doesNotMatch(mixed.message, /did not resolve|certificate/)
  safe(mixed)
  const bounded = workspaceNetworkFailure({ errors: [coded('ENOTFOUND'), coded('ENOTFOUND'), coded('ENOTFOUND'), coded('ENOTFOUND')] }, 'sign-in')
  assert.match(bounded.message, /address did not resolve/)
  const conflict = workspaceNetworkFailure({ errors: [coded('ENOTFOUND'), coded('CERT_HAS_EXPIRED')] }, 'identity')
  assert.equal(conflict.message, identityUnknown)
  safe(conflict)
})

test('accessors, malformed aggregates and oversized tokens stay unknown without reading private fields', () => {
  let getterCalls = 0
  for (const field of ['code', 'message', 'name', 'cause', 'errors']) {
    const input = field === 'cause' || field === 'errors' ? coded('ENOTFOUND') : { cause: coded('ENOTFOUND') }
    Object.defineProperty(input, field, { get() { getterCalls++; return 'PRIVATE_SENTINEL' } })
    const result = workspaceNetworkFailure(input, 'sign-in')
    assert.equal(result.message, signInUnknown, field)
    safe(result)
  }
  const timeout = new DOMException('PRIVATE_SENTINEL', 'TimeoutError')
  Object.defineProperty(timeout, 'name', { get() { getterCalls++; return 'TimeoutError' } })
  assert.equal(workspaceNetworkFailure(timeout, 'sign-in').message, signInUnknown)
  assert.equal(getterCalls, 0)
  for (const errors of [{}, 'PRIVATE_SENTINEL', [coded('ENOTFOUND'), null], new Array(2)]) {
    assert.equal(workspaceNetworkFailure({ code: 'ENOTFOUND', errors }, 'sign-in').message, signInUnknown)
  }
  const trapped = new Proxy({}, { getOwnPropertyDescriptor() { throw new Error('PRIVATE_SENTINEL') } })
  const result = workspaceNetworkFailure(trapped, 'identity')
  assert.equal(result.message, identityUnknown)
  safe(result)
  assert.equal(workspaceNetworkFailure(new Error('net::ERR_' + 'A'.repeat(4096)), 'sign-in').message, signInUnknown)
  assert.equal(workspaceNetworkFailure({ name: 'AbortError', cause: coded('ENOTFOUND') }, 'sign-in').message, signInUnknown)
})

test('password deliveries wait 60 seconds and other sign-in calls stay at 20', () => {
  assert.equal(workspaceSignInDeadline('login'), 60_000)
  assert.equal(workspaceSignInDeadline('invitations/accept'), 60_000)
  for (const operation of ['refresh', 'logout', 'invitations/preview', 'company/configuration', 'company/start', 'company/finish', 'login-again', 'Login']) {
    assert.equal(workspaceSignInDeadline(operation), 20_000, operation)
  }
  assert.equal(workspaceSignInDeadline({ toString() { return 'login' } }), 20_000)
})

test('the boundary calls the fetcher once, preserves status and request mode, and drops private failures', async () => {
  let calls = 0
  const response = await workspaceBoundaryFetch(async (_url, options) => {
    calls++
    assert.equal(options.cache, 'no-store')
    assert.equal(options.redirect, 'error')
    assert.equal(options.credentials, 'omit')
    assert.equal(options.method, 'POST')
    return new Response('not-a-login', { status: 503 })
  }, 'https://memory.example/organization/v1/sign-in/login', {
    method: 'POST', redirect: 'follow', credentials: 'include', cache: 'reload', body: JSON.stringify({ password: secret }),
  }, 'sign-in')
  assert.equal(calls, 1)
  assert.equal(response.status, 503)
  assert.equal(await response.text(), 'not-a-login')

  calls = 0
  await assert.rejects(workspaceBoundaryFetch(async () => {
    calls++
    throw coded('ECONNRESET', 'socket reset ' + secret)
  }, 'https://memory.example/organization/v1/me', {
    redirect: 'follow', credentials: 'include', headers: { Authorization: 'Bearer ' + secret },
  }, 'identity'), error => {
    assert.match(error.message, /refused, reset, or closed/)
    assert.equal(error.message.startsWith('The workspace could not be reached.'), true)
    safe(error)
    return true
  })
  assert.equal(calls, 1)

  calls = 0
  await assert.rejects(workspaceBoundaryFetch(() => {
    calls++
    throw { get code() { throw new Error('PRIVATE_SENTINEL_GETTER') } }
  }, 'https://memory.example/organization/v1/sign-in/login', { method: 'POST', body: secret }, 'sign-in'), error => {
    assert.equal(error.message, signInUnknown)
    safe(error)
    return true
  })
  assert.equal(calls, 1)
})
