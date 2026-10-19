import assert from 'node:assert/strict'
import { test } from 'node:test'
import { InstallerProgressWindow } from './installer-progress.mjs'

const process = (cpu = 20, written = 1024) => ({ ProcessId: 10, CreationDate: 'fixture',
  KernelModeTime: 2, UserModeTime: cpu, ReadTransferCount: 2048, WriteTransferCount: written })

test('a live but stalled installer and a missing observation still expire at four minutes', () => {
  for (const observation of [undefined, [], [process()]]) {
    const window = new InstallerProgressWindow(100)
    for (const at of [120_100, 150_100, 180_100, 210_100, 240_100]) window.observe(at, observation)
    assert.equal(window.expired(240_099), undefined)
    assert.equal(window.expired(240_100), 'no_installer_progress')
  }
})

test('measured extraction progress permits a slow install, with a two-minute stall limit', () => {
  const window = new InstallerProgressWindow(0)
  window.observe(120_000, [process()])
  window.observe(210_000, [process(30, 2048)])
  assert.equal(window.expired(240_000), undefined)
  window.observe(300_000, [process(30, 4096)])
  assert.equal(window.expired(419_999), undefined)
  assert.equal(window.expired(420_000), 'no_installer_progress')
})

test('even continuous CPU or IO activity cannot extend the ten-minute hard limit', () => {
  const window = new InstallerProgressWindow(0)
  for (let at = 120_000; at <= 600_000; at += 30_000) window.observe(at, [process(at)])
  assert.equal(window.expired(599_999), undefined)
  assert.equal(window.expired(600_000), 'maximum_duration')
})
