import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, rmSync, writeFileSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import { refreshLinuxLoginEntry } from '../dist/linux-startup.js'

test('an AppImage update retains OS startup opt-outs and only changes its launch path', () => {
  const directory = mkdtempSync(join(tmpdir(), 'mnemion-startup-'))
  const path = join(directory, 'mnemion.desktop')
  const original = '[Desktop Entry]\nType=Application\nName=Mnemion Studio\nExec="/home/User/Apps with spaces/Mnemion-Studio-4.0.3-linux-x86_64.AppImage" --background\nHidden=true\nX-GNOME-Autostart-enabled=false\n[Desktop Action Custom]\nExec=/custom/action\n'
  try {
    writeFileSync(path, original)
    assert.equal(refreshLinuxLoginEntry(path, '/home/User/Apps with spaces/Mnemion-Studio-4.0.4-linux-x86_64.AppImage'), true)
    assert.equal(readFileSync(path, 'utf8'), original.replace('4.0.3', '4.0.4'))
    assert.equal(refreshLinuxLoginEntry(path, '/home/User/Apps with spaces/Mnemion-Studio-4.0.4-linux-x86_64.AppImage'), false)
    writeFileSync(path, '[Desktop Entry]\nExec=/custom/company-wrapper --background\n')
    assert.equal(refreshLinuxLoginEntry(path, '/Apps/Mnemion.AppImage'), false)
    assert.equal(readFileSync(path, 'utf8'), '[Desktop Entry]\nExec=/custom/company-wrapper --background\n')
    rmSync(path)
    assert.equal(refreshLinuxLoginEntry(path, '/Apps/Mnemion.AppImage'), false)
    assert.equal(existsSync(path), false)
  } finally { rmSync(directory, { recursive: true, force: true }) }
})
