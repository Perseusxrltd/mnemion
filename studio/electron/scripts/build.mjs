import { readFileSync, writeFileSync, rmSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const check = spawnSync(process.execPath, [resolve(root, 'node_modules/typescript/bin/tsc'), '-p', resolve(root, 'tsconfig.json')], { stdio: 'inherit' })
if (check.status !== 0) process.exit(check.status || 1)
// Sandboxed Electron preloads use CommonJS even though the main process is ESM.
const preload = ts.transpileModule(readFileSync(resolve(root, 'preload.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
})
writeFileSync(resolve(root, 'dist/preload.cjs'), preload.outputText)
rmSync(resolve(root, 'dist/preload.js'), { force: true })
