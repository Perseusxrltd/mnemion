import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { finishResourceCleanup, performOwnedInstall } from './installed-resource-report.mjs'

test('verification and partial installer failures stay owned for cleanup', async () => {
  const root = mkdtempSync(join(tmpdir(), 'owned-resource-'))
  const installations = []
  const productRan = []
  const first = join(root, 'verified')
  const created = join(root, 'created')
  const partial = join(root, 'partial')
  await performOwnedInstall(installations, { id: 1, directory: first, package: 'inactive' }, {
    refusePreexisting: async () => {},
    installProduct: async () => {
      productRan.push(1)
      mkdirSync(first)
      writeFileSync(join(first, 'Mnemion Studio.exe'), 'product')
    },
    verify: async () => 'runtime',
  })
  await assert.rejects(() => performOwnedInstall(installations, { id: 2, directory: created, package: 'active' }, {
    refusePreexisting: async () => {},
    installProduct: async () => {
      productRan.push(2)
      mkdirSync(created)
      writeFileSync(join(created, 'Mnemion Studio.exe'), 'product')
    },
    verify: async () => { throw new Error('native resources missing') },
  }))
  await assert.rejects(() => performOwnedInstall(installations, { id: 3, directory: partial, package: 'inactive' }, {
    refusePreexisting: async () => {},
    installProduct: async () => {
      productRan.push(3)
      mkdirSync(partial)
      writeFileSync(join(partial, 'partial-product'), 'product')
      throw new Error('installer stopped after creating the product')
    },
    verify: async () => { throw new Error('verify must not run') },
  }))
  const beforeRefusal = installations.length
  let refusedInstaller = false
  await assert.rejects(() => performOwnedInstall(installations, { id: 4, directory: join(root, 'preexisting'), package: 'active' }, {
    refusePreexisting: async () => { throw new Error('Refusing to modify an existing Mnemion installation') },
    installProduct: async () => { refusedInstaller = true },
    verify: async () => {},
  }))
  assert.equal(installations.length, beforeRefusal)
  assert.equal(refusedInstaller, false)
  assert.deepEqual(installations.map(item => item.state), ['verified', 'verification_failed', 'installer_failed'])
  assert.deepEqual(productRan, [1, 2, 3])
  const calls = []
  const failures = finishResourceCleanup(installations, new Set(), item => {
    calls.push(item.id)
    assert.equal(item.directory.startsWith(root), true)
    if (item.id === 2) throw new Error(item.directory)
    rmSync(item.directory, { recursive: true, force: true })
  })
  assert.deepEqual(calls, [1, 2, 3])
  assert.deepEqual(failures, ['uninstall_failed'])
  rmSync(root, { recursive: true, force: true })
})
