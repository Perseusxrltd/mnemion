import assert from 'node:assert/strict'
import { test } from 'node:test'
import { canRestartForUpdate, desktopExec, updateChannel, updateRestartBlocker } from '../dist/update-policy.js'

const ready = { enabled: true, downloaded: true, idleSeconds: 600, focused: false, visible: true, minimized: false, safe: true, busy: false }
test('automatic restart requires an idle, clean session with no active transfer', () => {
  assert.equal(canRestartForUpdate(ready), true)
  for (const change of [{ enabled: false }, { downloaded: false }, { idleSeconds: 599 },
    { idleSeconds: NaN }, { focused: true }, { safe: false }, { busy: true }]) {
    assert.equal(canRestartForUpdate({ ...ready, ...change }), false)
  }
})
test('stale focus on a minimized or hidden window does not block a safe idle restart', () => {
  for (const window of [{ focused: true, visible: true, minimized: true }, { focused: true, visible: false, minimized: false },
    { focused: true, visible: false, minimized: true }]) {
    assert.equal(canRestartForUpdate({ ...ready, ...window }), true)
    for (const guard of [{ enabled: false }, { downloaded: false }, { idleSeconds: 599 },
      { idleSeconds: NaN }, { safe: false }, { busy: true }]) {
      assert.equal(canRestartForUpdate({ ...ready, ...window, ...guard }), false)
    }
  }
  assert.equal(canRestartForUpdate({ ...ready, focused: true, visible: true, minimized: false }), false)
})
test('a user-requested restart does not require leaving the computer idle or hiding the app', () => {
  const workingAtComputer = { ...ready, idleSeconds: 0, focused: true }
  assert.equal(canRestartForUpdate(workingAtComputer), false)
  assert.equal(canRestartForUpdate(workingAtComputer, true), true)
  // The request is scoped to that call; the next automatic tick stays guarded.
  assert.equal(canRestartForUpdate(workingAtComputer), false)
  for (const guard of [{ enabled: false }, { downloaded: false }, { safe: false }, { busy: true }]) {
    assert.equal(canRestartForUpdate({ ...workingAtComputer, ...guard }, true), false)
  }
})
test('a locked desktop does not preserve active window focus or bypass work and inactivity guards', () => {
  const locked = { ...ready, focused: true, locked: true }
  assert.equal(canRestartForUpdate(locked), true)
  for (const guard of [{ enabled: false }, { downloaded: false }, { idleSeconds: 599 },
    { idleSeconds: NaN }, { idleSeconds: Infinity }, { safe: false }, { busy: true }, { locked: false }]) {
    assert.equal(canRestartForUpdate({ ...locked, ...guard }), false)
  }
})
test('restart diagnostics identify blockers without weakening either restart path', () => {
  const cases = [
    [{ enabled: false }, 'disabled'], [{ downloaded: false }, 'not-downloaded'],
    [{ busy: true }, 'busy'], [{ safe: false }, 'work'],
    [{ focused: true }, 'focused'], [{ idleSeconds: 599 }, 'inactivity'],
    [{ idleSeconds: NaN }, 'inactivity'], [{ idleSeconds: Infinity }, 'inactivity'],
  ]
  for (const [change, reason] of cases) {
    assert.equal(updateRestartBlocker({ ...ready, ...change }), reason)
    assert.equal(updateRestartBlocker({ ...ready, ...change }, true),
      ['focused', 'inactivity'].includes(reason) ? null : reason)
  }
  assert.equal(updateRestartBlocker({ ...ready, focused: true, busy: true, safe: false }, true), 'busy')
  assert.equal(updateRestartBlocker({ ...ready, focused: true, safe: false }, true), 'work')
  assert.equal(updateRestartBlocker(ready), null)
})
test('architectures have separate stable update feeds', () => {
  assert.equal(updateChannel('x64'), 'latest-x64')
  assert.equal(updateChannel('arm64'), 'latest-arm64')
  assert.throws(() => updateChannel('../latest'))
})
test('Linux login entry protects paths with spaces, quotes and field codes', () => {
  assert.equal(desktopExec('/home/user/My App%U.AppImage'), '"/home/user/My App%%U.AppImage" --background')
  assert.equal(desktopExec('/home/"$`\\.AppImage'), '"/home/\\"\\$\\`\\\\.AppImage" --background')
  assert.throws(() => desktopExec('/bin/app\nExec=bad'))
  assert.throws(() => desktopExec('relative'))
})
