/** Keep OS consent waits outside the main event loop and bound pending work. */
import type { CredentialCipher } from './workspace-store.js'

interface AsyncSecureStorage {
  available(): Promise<boolean>
  encrypt(value: string): Promise<Buffer>
  decrypt(value: Buffer): Promise<string>
}

const LOCKED = 'The operating system secure store is locked or waiting for approval. Unlock it and retry. You can connect for this session without remembering the key.'

export function boundedCredentialCipher(
  storage: AsyncSecureStorage,
  { checkTimeoutMs = 2000, operationTimeoutMs = 15000 } = {},
): CredentialCipher {
  let checking: Promise<boolean> | undefined
  let working: Promise<unknown> | undefined

  function deadline<T>(operation: Promise<T>, milliseconds: number): Promise<T> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(LOCKED)), milliseconds)
      operation.then(value => { clearTimeout(timer); resolve(value) }, () => {
        clearTimeout(timer); reject(new Error(LOCKED))
      })
    })
  }

  async function available(): Promise<boolean> {
    if (!checking) {
      const pending = Promise.resolve().then(() => storage.available()).then(value => value === true, () => false)
      checking = pending
      // A timed-out native request may still await OS consent. Share that one
      // request until it settles instead of accumulating callbacks/prompts.
      void pending.then(() => { if (checking === pending) checking = undefined })
    }
    try { return await deadline(checking, checkTimeoutMs) } catch { return false }
  }

  async function operation<T>(action: () => Promise<T>): Promise<T> {
    if (!await available() || working) throw new Error(LOCKED)
    const pending = Promise.resolve().then(action)
    working = pending
    const finished = () => { if (working === pending) working = undefined }
    void pending.then(finished, finished)
    return deadline(pending, operationTimeoutMs)
  }

  return {
    available,
    encrypt: async value => {
      const encrypted = await operation(() => storage.encrypt(value))
      if (!Buffer.isBuffer(encrypted) || !encrypted.length || encrypted.length > 16384) throw new Error(LOCKED)
      return encrypted
    },
    decrypt: async value => {
      const decrypted = await operation(() => storage.decrypt(value))
      if (typeof decrypted !== 'string' || Buffer.byteLength(decrypted) > 16384) throw new Error(LOCKED)
      return decrypted
    },
  }
}
