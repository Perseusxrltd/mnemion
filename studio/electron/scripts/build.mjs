import { readFileSync, writeFileSync, rmSync, copyFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const check = spawnSync(process.execPath, [resolve(root, 'node_modules/typescript/bin/tsc'), '-p', resolve(root, 'tsconfig.json')], { stdio: 'inherit' })
if (check.status !== 0) process.exit(check.status || 1)
const probe = spawnSync(process.env.MNEMION_BUILD_PYTHON || (process.platform === 'win32' ? 'python' : 'python3'),
  ['-m', 'deploy.build_telemetry_network', '--arch', process.arch, '--output', resolve(root, 'dist/telemetry-network.node')],
  { cwd: resolve(root, '../..'), stdio: 'inherit', windowsHide: true })
if (probe.status !== 0) process.exit(probe.status || 1)
if (process.platform === 'win32') {
  const privacy = spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
    '-File', resolve(root, 'scripts/build-telemetry-private-store.ps1'), '-Architecture', process.arch,
    '-Destination', resolve(root, 'dist/telemetry-private-store.exe')], { stdio: 'inherit', windowsHide: true })
  if (privacy.status !== 0) process.exit(privacy.status || 1)
}
copyFileSync(resolve(root, 'native/windows-updates.json'), resolve(root, 'dist/windows-updates.json'))
for (const name of ['disclosure', 'catalog', 'desktop-origins', 'wire-v2', 'transport-route']) {
  copyFileSync(resolve(root, `../../mnemion/product_telemetry/${name}.json`), resolve(root, `dist/telemetry-${name}.json`))
}
// Sandboxed Electron preloads use CommonJS even though the main process is ESM.
const preload = ts.transpileModule(readFileSync(resolve(root, 'preload.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
})
writeFileSync(resolve(root, 'dist/preload.cjs'), preload.outputText)
rmSync(resolve(root, 'dist/preload.js'), { force: true })
const kit = spawnSync(process.execPath, [resolve(root, '../../deploy/build_recovery_kit.mjs'), ...(process.argv.includes('--generate-recovery-kit') ? [] : ['--check'])], { stdio: 'inherit' })
if (kit.status !== 0) process.exit(kit.status || 1)
