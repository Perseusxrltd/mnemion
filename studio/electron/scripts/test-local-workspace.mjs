import assert from 'node:assert/strict'
import childProcess from 'node:child_process'
import { EventEmitter } from 'node:events'
import { readFileSync } from 'node:fs'
import { syncBuiltinESMExports } from 'node:module'
import { PassThrough } from 'node:stream'
import { test } from 'node:test'
import { LocalWorkspace } from '../dist/local-workspace.js'

const { version } = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'))
const root = '/private/test-workspace'
const settle = () => new Promise(resolve => setImmediate(resolve))
const policy = revision => ({ format: 1, revision, settings: { mode: 'manual', limit_mib: 512 } })
const info = revision => ({ event: 'status', configured: true, data_directory: root, engine_version: version,
  resources: { memory_bytes: 4 * 1024 ** 3, available_disk_bytes: 8 * 1024 ** 3 }, memory_policy: policy(revision) })

class Command extends EventEmitter {
  stdin = new PassThrough()
  stdout = new PassThrough()
  stderr = new PassThrough()
  closed = false
  constructor(action) { super(); this.action = action }
  reply(value) { this.stdout.write(JSON.stringify(value)); this.finish() }
  event(value) { this.stdout.write(JSON.stringify(value) + '\n') }
  finish() { if (!this.closed) { this.closed = true; this.emit('close', 0) } }
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
    workspace_id: '00000000-0000-4000-8000-000000000001', engine_version: version })
  f.last().reply(info('first'))
  await settle()
  return engine
}

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
