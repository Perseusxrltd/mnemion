import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import fs from 'node:fs/promises'
import { syncBuiltinESMExports } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import { replaceFile } from '../dist/atomic-file.js'

const nativePlatform = process.platform, rename = fs.rename

async function fixture(t) {
  const directory = await fs.mkdtemp(join(tmpdir(), 'mnemion atomic équipe '))
  t.after(() => fs.rm(directory, { recursive: true, force: true }))
  const destination = join(directory, 'state.json'), temporary = join(directory, 'replacement.tmp')
  await fs.writeFile(destination, 'previous complete document')
  await fs.writeFile(temporary, 'next complete document')
  return { destination, temporary }
}

async function withRename(t, platform, implementation, run) {
  const descriptor = Object.getOwnPropertyDescriptor(process, 'platform')
  const mock = t.mock.method(fs, 'rename', implementation)
  Object.defineProperty(process, 'platform', { ...descriptor, value: platform })
  syncBuiltinESMExports()
  try { return await run() }
  finally {
    mock.mock.restore()
    syncBuiltinESMExports()
    Object.defineProperty(process, 'platform', descriptor)
  }
}

for (const code of ['EPERM', 'EACCES', 'EBUSY']) {
  test(`Windows ${code} sharing failures keep both complete files until replacement succeeds`, async t => {
    const f = await fixture(t)
    let calls = 0
    await withRename(t, 'win32', async (...paths) => {
      assert.deepEqual(paths, [f.temporary, f.destination])
      assert.equal(await fs.readFile(f.destination, 'utf8'), 'previous complete document')
      assert.equal(await fs.readFile(f.temporary, 'utf8'), 'next complete document')
      if (++calls < 3) throw Object.assign(new Error('sharing lock'), { code })
      return rename(...paths)
    }, () => replaceFile(f.temporary, f.destination))
    assert.equal(calls, 3)
    assert.equal(await fs.readFile(f.destination, 'utf8'), 'next complete document')
    await assert.rejects(fs.stat(f.temporary), { code: 'ENOENT' })
  })
}

test('a lasting Windows lock stops with the original error and never removes either complete file', async t => {
  const f = await fixture(t), error = Object.assign(new Error('sharing lock persists'), { code: 'EPERM' })
  let calls = 0
  await withRename(t, 'win32', async () => { calls++; throw error },
    () => assert.rejects(replaceFile(f.temporary, f.destination), thrown => thrown === error))
  assert.equal(calls, 11)
  assert.equal(await fs.readFile(f.destination, 'utf8'), 'previous complete document')
  assert.equal(await fs.readFile(f.temporary, 'utf8'), 'next complete document')
})

for (const [platform, code] of [['win32', 'ENOENT'], ['win32', 'ENOSPC'], ['linux', 'EPERM'], ['darwin', 'EACCES']]) {
  test(`${platform} ${code} fails immediately without replacement fallback`, async t => {
    const f = await fixture(t), error = Object.assign(new Error('not a Windows sharing failure'), { code })
    let calls = 0
    await withRename(t, platform, async () => { calls++; throw error },
      () => assert.rejects(replaceFile(f.temporary, f.destination), thrown => thrown === error))
    assert.equal(calls, 1)
    assert.equal(await fs.readFile(f.destination, 'utf8'), 'previous complete document')
  })
}

test('cancellation during a Windows sharing wait preserves the previous file and stops attempts', async t => {
  const f = await fixture(t), controller = new AbortController()
  let calls = 0
  await withRename(t, 'win32', async () => {
    calls++
    setImmediate(() => controller.abort())
    throw Object.assign(new Error('sharing lock'), { code: 'EPERM' })
  }, () => assert.rejects(replaceFile(f.temporary, f.destination, controller.signal), { name: 'AbortError' }))
  assert.equal(calls, 1)
  assert.equal(await fs.readFile(f.destination, 'utf8'), 'previous complete document')
  assert.equal(await fs.readFile(f.temporary, 'utf8'), 'next complete document')
})

test('already cancelled replacement does not attempt a filesystem change', async t => {
  const f = await fixture(t), controller = new AbortController()
  controller.abort()
  let calls = 0
  await withRename(t, 'win32', async () => { calls++ },
    () => assert.rejects(replaceFile(f.temporary, f.destination, controller.signal), { name: 'AbortError' }))
  assert.equal(calls, 0)
  assert.equal(await fs.readFile(f.destination, 'utf8'), 'previous complete document')
})

test('a real Windows reader denying delete sharing can release the file before atomic replacement', {
  skip: nativePlatform !== 'win32', timeout: 30_000,
}, async t => {
  const f = await fixture(t)
  const script = '$ErrorActionPreference="Stop"; $f=[IO.File]::Open($env:MNEMION_RENAME_LOCK_FILE,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite); try { [Console]::Out.WriteLine("locked"); [Console]::Out.Flush(); [Console]::ReadLine() | Out-Null } finally { $f.Dispose() }'
  const child = spawn('powershell.exe', ['-NoLogo', '-NoProfile', '-NonInteractive', '-Command', script], {
    env: { ...process.env, MNEMION_RENAME_LOCK_FILE: f.destination }, windowsHide: true,
    stdio: ['pipe', 'pipe', 'pipe'], signal: t.signal,
  })
  let stderr = '', output = '', sharingFailures = 0
  child.stderr.on('data', value => { stderr = (stderr + value).slice(-1024) })
  const closed = new Promise(resolve => child.once('close', (code, signal) => resolve({ code, signal })))
  const ready = new Promise((resolve, reject) => {
    child.once('error', reject)
    child.once('close', () => reject(new Error(`Reader exited before locking: ${stderr}`)))
    child.stdout.on('data', value => {
      output = (output + value).slice(-1024)
      if (output.includes('locked\n') || output.includes('locked\r\n')) resolve()
    })
  })
  try {
    await ready
    await withRename(t, 'win32', async (...paths) => {
      try { return await rename(...paths) }
      catch (error) {
        assert.ok(['EPERM', 'EACCES', 'EBUSY'].includes(error.code))
        sharingFailures++
        if (sharingFailures === 1) child.stdin.end('\n')
        throw error
      }
    }, () => replaceFile(f.temporary, f.destination))
    assert.ok(sharingFailures > 0, 'the actual OS must deny replacement while its reader holds the file')
    assert.deepEqual(await closed, { code: 0, signal: null })
    assert.equal(await fs.readFile(f.destination, 'utf8'), 'next complete document')
    await assert.rejects(fs.stat(f.temporary), { code: 'ENOENT' })
  } finally {
    if (child.exitCode === null) child.kill()
    await closed
  }
})
