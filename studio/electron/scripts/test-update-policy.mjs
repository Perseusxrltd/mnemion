import assert from 'node:assert/strict'
import { test } from 'node:test'
import { canRestartForUpdate, desktopExec, updateChannel } from '../dist/update-policy.js'

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
