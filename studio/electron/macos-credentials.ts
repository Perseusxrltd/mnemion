import { app } from 'electron'
import { spawn } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { CredentialProcess } from './credential-process.js'
import { boundedCredentialCipher } from './workspace-cipher.js'

const helper = new CredentialProcess(() => {
  const directory = mkdtempSync(join(app.getPath('temp'), 'mnemion-keychain-'))
  const environment: NodeJS.ProcessEnv = { MNEMION_KEYCHAIN_USER_DATA: directory }
  for (const name of ['HOME', 'PATH', 'TMPDIR', 'USER', 'LOGNAME', 'SHELL', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ', '__CF_USER_TEXT_ENCODING']) {
    if (process.env[name] !== undefined) environment[name] = process.env[name]
  }
  try {
    const child = spawn(process.execPath, [
      ...(!app.isPackaged ? [app.getAppPath()] : []), '--mnemion-keychain-helper',
      '--user-data-dir=' + directory,
    ], { stdio: ['pipe', 'pipe', 'pipe'], env: environment })
    child.once('close', () => { try { rmSync(directory, { recursive: true, force: true }) } catch { /* OS temp cleanup can retry. */ } })
    return child
  } catch (error) { rmSync(directory, { recursive: true, force: true }); throw error }
})

export const macosCredentialCipher = boundedCredentialCipher(helper)
export const macosCredentialMemory = () => helper.memoryBytes

// before-quit can be cancelled while database/update drains finish. The helper
// remains usable until final will-quit, including after an aborted update.
if (process.platform === 'darwin') app.on('will-quit', () => helper.close())
