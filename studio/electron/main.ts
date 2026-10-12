// Await loading so lifecycle handlers are installed before Electron is ready.
if (process.argv.includes('--mnemion-keychain-helper')) {
  await import('./keychain-helper.js')
} else {
  await import('./application.js')
}
export {}
