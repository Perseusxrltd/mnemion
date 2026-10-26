#!/usr/bin/env node
import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'

// CUSTOM_DMGBUILD_PATH is electron-builder's supported tool override. These
// archive pins match dmg-builder 26.15.3; only the CLI detach budget changes.
const require = createRequire(import.meta.url)
const { downloadBuilderToolset } = require('app-builder-lib/out/util/electronGet')
if (process.platform !== 'darwin' || !['x64', 'arm64'].includes(process.arch)) {
  throw new Error('The Mnemion dmgbuild wrapper requires an Intel or Apple Silicon Mac')
}
const arch = process.arch === 'arm64' ? 'arm64' : 'x86_64'
const directory = await downloadBuilderToolset({
  releaseName: 'dmg-builder@1.2.5',
  filenameWithExt: `dmgbuild-bundle-${arch}-75c8a6c.tar.gz`,
  checksums: {
    'dmgbuild-bundle-arm64-75c8a6c.tar.gz': '793404d0c96687e27d5ee40a668d498c92e36a64d6c2906df511031adb33cbeb',
    'dmgbuild-bundle-x86_64-75c8a6c.tar.gz': '1664972f9cc2d6e8fce3b63e42cd30078aff602669c5856939c4519921200433',
  },
})
const child = spawn(resolve(directory, 'dmgbuild'), ['--detach-retries', '12', ...process.argv.slice(2)], {
  stdio: 'inherit',
})
const forward = signal => child.kill(signal)
process.on('SIGINT', forward)
process.on('SIGTERM', forward)
child.once('error', error => {
  console.error(error)
  process.exitCode = 1
})
child.once('close', (code, signal) => {
  process.removeListener('SIGINT', forward)
  process.removeListener('SIGTERM', forward)
  // Preserve the vendor's failure or cancellation; never accept an incomplete DMG.
  if (signal) process.kill(process.pid, signal)
  else process.exitCode = code ?? 1
})
