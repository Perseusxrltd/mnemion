import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'
import { root, packageJson } from './platform-artifacts.mjs'

export function verifyNativeResources(resources, sourceRoot = undefined) {
  const python = process.env.MNEMION_ENGINE_PYTHON || resolve(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
  const args = ['-m', 'deploy.native_resources', '--resources', resources,
    '--platform', { linux: 'linux', darwin: 'macos', win32: 'windows' }[process.platform], '--arch', process.arch, '--version', packageJson.version]
  // Ordinary packaging omits the root and hashes this module's own tree.
  // A resource package passes the source directory this driver prepared.
  if (sourceRoot !== undefined) {
    if (typeof sourceRoot !== 'string' || sourceRoot.length === 0) {
      throw new Error('Native resource verification requires the prepared source')
    }
    args.push('--source-root', sourceRoot)
  }
  const result = spawnSync(python, args, { cwd: root, encoding: 'utf8', timeout: 120_000, maxBuffer: 1024 * 1024 })
  if (result.error || result.status !== 0) throw new Error(`Native resource verification failed: ${result.error?.message || result.stderr}`)
  return JSON.parse(result.stdout)
}
