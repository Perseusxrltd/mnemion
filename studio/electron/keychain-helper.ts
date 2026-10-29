// Same signed executable as Studio, so the helper has no separate keychain
// identity. Electron safeStorage ciphertext stays the same. OS consent runs
// outside the UI process and cannot pin its native teardown.
import { app, safeStorage } from 'electron'
import { lstatSync } from 'node:fs'
import { isAbsolute } from 'node:path'
import { serveCredentialRequests } from './credential-process.js'

const profile = process.env.MNEMION_KEYCHAIN_USER_DATA
if (process.platform !== 'darwin' || !profile || !isAbsolute(profile)) process.exit(1)
const info = lstatSync(profile)
if (!info.isDirectory() || info.isSymbolicLink() || (info.mode & 0o077) || info.uid !== process.getuid?.()) process.exit(1)
app.setPath('userData', profile)
app.disableHardwareAcceleration()
app.commandLine.appendSwitch('disable-gpu')
// No windows, tray, service listener, saved credentials or database. If the
// parent disappears, kill this disposable process even during native consent.
const abort = () => { process.kill(process.pid, 'SIGKILL') }
process.on('SIGTERM', abort)
process.stdin.on('end', abort).on('error', abort)
app.whenReady().then(() => {
  app.setActivationPolicy('prohibited')
  app.dock?.hide()
  serveCredentialRequests({
    available: () => safeStorage.isAsyncEncryptionAvailable(),
    encrypt: value => safeStorage.encryptStringAsync(value),
    decrypt: async value => (await safeStorage.decryptStringAsync(value)).result,
  }, process.stdin, process.stdout,
  () => app.getAppMetrics().reduce((sum, metric) => sum + metric.memory.workingSetSize * 1024, 0), abort)
}).catch(abort)
