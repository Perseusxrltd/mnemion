import assert from 'node:assert/strict'
import { test } from 'node:test'
import { EventEmitter } from 'node:events'
import { PassThrough } from 'node:stream'
import { MacUpdateBridge, parseMacUpdateEvent } from '../dist/macos-updates.js'

test('native update messages reject malformed data and keep errors out of the UI', () => {
  assert.deepEqual(parseMacUpdateEvent('{"state":"error","reason":"https://private.invalid/token"}'), { state: 'error' })
  for (const line of ['null', '[]', '{}', '{"state":"shell"}', '{"state":"ready"}',
    '{"state":"ready","version":"4.0.1-rc1"}', '{"state":"downloading","percent":101}',
    '{"state":"downloading","percent":-1}', 'x'.repeat(2049)]) {
    assert.throws(() => parseMacUpdateEvent(line))
  }
})

function fixture() {
  const child = new EventEmitter()
  child.stdout = new PassThrough()
  child.stderr = new PassThrough()
  child.stdin = new PassThrough()
  const commands = []
  child.stdin.on('data', chunk => commands.push(chunk.toString()))
  const events = []
  const bridge = new MacUpdateBridge('/Synthetic.app/Contents/MacOS/MnemionUpdater', event => events.push(event), () => child)
  return { child, bridge, commands, events }
}

test('a verified download never installs until the parent approves', async () => {
  const { child, bridge, commands } = fixture()
  const check = bridge.check()
  assert.equal(bridge.install(), false)
  child.stdout.write('{"state":"ready","version":"4.0.1"}\n')
  await check
  assert.deepEqual(commands, [])
  assert.equal(bridge.install(), true)
  assert.equal(bridge.install(), false)
  assert.deepEqual(commands, ['install\n'])
  child.emit('close', 0)
})

test('pause during download suppresses a racing ready message and waits for cleanup', async () => {
  const { child, bridge, commands, events } = fixture()
  const check = bridge.check()
  let finished = false
  const cancelled = bridge.cancel().then(value => { finished = true; return value })
  child.stdout.write('{"state":"ready","version":"4.0.1"}\n')
  await Promise.resolve()
  assert.equal(finished, false)
  assert.equal(bridge.install(), false)
  assert.deepEqual(commands, ['cancel\n'])
  assert.equal(events.some(event => event.state === 'ready'), false)
  child.emit('close', 0)
  assert.equal(await cancelled, true)
  await check
  assert.equal(bridge.active, false)
})

test('oversized native output cancels without installing or forwarding data', async () => {
  const { child, bridge, commands, events } = fixture()
  const check = bridge.check()
  child.stdout.write('x'.repeat(3000))
  assert.deepEqual(commands, ['cancel\n'])
  assert.deepEqual(events, [{ state: 'error' }])
  child.emit('close', 0)
  await check
})
