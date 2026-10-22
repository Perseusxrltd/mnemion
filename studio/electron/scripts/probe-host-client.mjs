/** Test driver: real native engine and protected profile, no production state. */
import { createCipheriv, createDecipheriv, createHash, randomBytes } from 'node:crypto'
import { HostProfiles } from '../dist/host-profiles.js'
import { sourceProcess } from '../dist/desktop-source-process.js'
import { hostMessages } from '../dist/host-control-messages.js'

let raw = ''
for await (const chunk of process.stdin) { raw += chunk; if (Buffer.byteLength(raw) > 32768) throw new Error('Bounded fixture input required') }
const input = JSON.parse(raw)
const key = createHash('sha256').update('Disposable host-client fixture: ' + input.root).digest()
const cipher = {
  available: () => true,
  encrypt: value => { const iv = randomBytes(12), aes = createCipheriv('aes-256-gcm', key, iv); return Buffer.concat([iv, aes.update(value), aes.final(), aes.getAuthTag()]) },
  decrypt: value => { const aes = createDecipheriv('aes-256-gcm', key, value.subarray(0, 12)); aes.setAuthTag(value.subarray(-16)); return Buffer.concat([aes.update(value.subarray(12, -16)), aes.final()]).toString() },
}
const manager = new HostProfiles(input.root, cipher, sourceProcess({ executable: input.python,
  prefix: ['-m', 'mnemion.service.cli'], command: 'desktop-host', root: input.root,
  privateRoots: [], environment: { ...process.env, PYTHONPATH: input.source }, messages: hostMessages, deadlineMs: 30000 }))
try {
  let result
  if (input.action === 'create') result = await manager.create('Desktop custodian fixture')
  else if (input.action === 'enroll') result = await manager.enroll(input.id, input.connection, true)
  else if (input.action === 'inspect') result = await manager.inspect(input.id)
  else if (input.action === 'request') result = await manager.request(input.id, input.request)
  else if (input.action === 'status') result = await manager.status()
  else throw new Error('Unknown fixture action')
  process.stdout.write(JSON.stringify({ ok: true, result }) + '\n')
} catch (error) {
  process.stdout.write(JSON.stringify({ ok: false, error: error.message }) + '\n')
  process.exitCode = 2
} finally { await manager.close() }
