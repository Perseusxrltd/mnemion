import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'
import { root, packageJson } from './platform-artifacts.mjs'

export function verifyNativeResources(resources) {
  const python = process.env.MNEMION_ENGINE_PYTHON || resolve(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
  const result = spawnSync(python, ['-m', 'deploy.native_resources', '--resources', resources,
    '--platform', { linux: 'linux', darwin: 'macos', win32: 'windows' }[process.platform], '--arch', process.arch, '--version', packageJson.version],
  { cwd: root, encoding: 'utf8', timeout: 120_000, maxBuffer: 1024 * 1024 })
  if (result.error || result.status !== 0) throw new Error(`Native resource verification failed: ${result.error?.message || result.stderr}`)
  return JSON.parse(result.stdout)
}
