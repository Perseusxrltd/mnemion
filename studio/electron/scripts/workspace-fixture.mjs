import { createCipheriv, createDecipheriv, randomBytes, randomUUID } from 'node:crypto'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { WorkspaceStore } from '../dist/workspace-store.js'

// Native gates exercise Electron safeStorage. This authenticated cipher tests
// persistence and concurrency without depending on a developer's keychain.
export async function workspaceFixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'mnemion-workspace-store-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  const key = randomBytes(32)
  const cipher = {
    unlocked: true,
    available() { return this.unlocked },
    encrypt(value) {
      const nonce = randomBytes(12)
      const encrypt = createCipheriv('aes-256-gcm', key, nonce)
      const ciphertext = Buffer.concat([encrypt.update(value, 'utf8'), encrypt.final()])
      return Buffer.concat([nonce, encrypt.getAuthTag(), ciphertext])
    },
    decrypt(value) {
      const decrypt = createDecipheriv('aes-256-gcm', key, value.subarray(0, 12))
      decrypt.setAuthTag(value.subarray(12, 28))
      return Buffer.concat([decrypt.update(value.subarray(28)), decrypt.final()]).toString('utf8')
    },
  }
  const directory = join(root, 'workspaces')
  const identity = { principal_id: randomUUID(), tenant_id: randomUUID(), name: 'Test user', tenant_name: 'Test team', administrator: false }
  return { root, directory, path: join(directory, 'connections.json'), identity, cipher, store: new WorkspaceStore(directory, cipher) }
}

export const fixtureCredential = 'fixture_' + 'token'.repeat(8)
