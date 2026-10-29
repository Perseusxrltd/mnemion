import assert from 'node:assert/strict'
import { chmodSync, existsSync, linkSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import { clearUpdateRelaunch, consumeUpdateRelaunch, rememberUpdateRelaunch } from '../dist/update-relaunch.js'

const version = '4.46.52', now = 1_800_000_000_000
function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), 'mnemion-update-relaunch-'))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  return { root, path: join(root, 'desktop-update-relaunch.json') }
}

test('a completed update preserves either presentation exactly once', t => {
  const { root, path } = fixture(t)
  for (const background of [true, false]) {
    rememberUpdateRelaunch(path, version, background, now)
    assert.equal(consumeUpdateRelaunch(path, version, now + 60_000), background)
    assert.equal(consumeUpdateRelaunch(path, version, now + 60_001), null)
    assert.deepEqual(readdirSync(root), [])
  }
})

test('an unsuccessful update cannot hide a launch of the previous or a later version', t => {
  const { path } = fixture(t)
  for (const other of ['4.46.51', '4.46.53']) {
    rememberUpdateRelaunch(path, version, true, now)
    assert.equal(consumeUpdateRelaunch(path, other, now), null)
    assert.equal(consumeUpdateRelaunch(path, version, now), null)
  }
})

test('stale, future, oversized or malformed records cannot change normal startup', t => {
  const { path } = fixture(t)
  const valid = { format: 1, version, background: true, createdAt: now }
  const values = [
    '{broken', ' '.repeat(513), JSON.stringify(null), JSON.stringify([]),
    ...[{ ...valid, createdAt: now - 3_600_001 }, { ...valid, createdAt: now + 1 },
      { ...valid, createdAt: 'now' }, { ...valid, background: 'true' },
      { ...valid, format: 2 }, { ...valid, command: 'never execute' }].map(value => JSON.stringify(value)),
  ]
  for (const value of values) {
    writeFileSync(path, value, { mode: 0o600 })
    assert.equal(consumeUpdateRelaunch(path, version, now), null)
    assert.equal(existsSync(path), false)
  }
})

test('a symbolic link is refused without changing its target', { skip: process.platform === 'win32' }, t => {
  const { root, path } = fixture(t)
  const target = join(root, 'unrelated.json')
  rememberUpdateRelaunch(target, version, true, now)
  const original = readFileSync(target)
  symlinkSync(target, path)
  assert.equal(consumeUpdateRelaunch(path, version, now), null)
  assert.deepEqual(readFileSync(target), original)
})

test('a hard link is refused without consuming its other name', t => {
  const { root, path } = fixture(t)
  const target = join(root, 'unrelated.json')
  rememberUpdateRelaunch(target, version, true, now)
  const original = readFileSync(target)
  linkSync(target, path)
  assert.equal(consumeUpdateRelaunch(path, version, now), null)
  assert.deepEqual(readFileSync(target), original)
})

test('unprotected POSIX files cannot become startup instructions', { skip: process.platform === 'win32' }, t => {
  const { path } = fixture(t)
  rememberUpdateRelaunch(path, version, true, now)
  chmodSync(path, 0o644)
  assert.equal(consumeUpdateRelaunch(path, version, now), null)
})

test('cleanup never recursively removes an unexpected directory', t => {
  const { path } = fixture(t)
  mkdirSync(path)
  const child = join(path, 'retain.txt')
  writeFileSync(child, 'retain')
  assert.equal(consumeUpdateRelaunch(path, version, now), null)
  assert.equal(clearUpdateRelaunch(path), false)
  assert.equal(readFileSync(child, 'utf8'), 'retain')
})

test('write failure exposes a fixed diagnostic and no temporary state', t => {
  const { root, path } = fixture(t)
  mkdirSync(path)
  assert.throws(() => rememberUpdateRelaunch(path, version, true, now),
    { message: 'The app could not preserve its update restart state' })
  assert.deepEqual(readdirSync(root), ['desktop-update-relaunch.json'])
})
