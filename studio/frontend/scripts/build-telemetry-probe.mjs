/** Compile the actual UI and its measurement entry in one disposable module graph. */
import { build } from 'vite'
import { createHash } from 'node:crypto'
import { basename, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'

const frontend = fileURLToPath(new URL('../', import.meta.url))
const root = resolve(frontend, '../../..')
if (!basename(root).startsWith('mnemion-owned-renderer-') ||
    resolve(process.env.MNEMION_STUDIO_USER_DATA ?? '.') !== root) {
  throw new Error('Disposable renderer copy required')
}
const receipt = process.argv[2]
if (!receipt) throw new Error('A build receipt path is required')
const entry = 'src/owned-memory-probe.ts'
writeFileSync(join(frontend, entry),
  "export { MnemionClient } from '@mnemion/client';\n" +
  "export { measuredStudioClient } from './workspace/measured-client';\n" +
  "export { nativeFetch } from './workspace/native';\n", { flag: 'wx' })
const directory = join(frontend, 'dist-probe')
const result = await build({
  root: frontend, configFile: join(frontend, 'vite.config.ts'), base: '/',
  build: {
    outDir: directory, manifest: true,
    rollupOptions: {
      input: { app: join(frontend, 'index.html'), probe: join(frontend, entry) },
      preserveEntrySignatures: 'strict',
    },
  },
})
const chunks = (Array.isArray(result) ? result : [result])
  .flatMap(bundle => bundle.output).filter(value => value.type === 'chunk')
const manifest = JSON.parse(readFileSync(join(directory, '.vite/manifest.json'), 'utf8'))
const probe = manifest[entry]?.file, application = manifest['index.html']?.file
if (!probe || !application || !/^assets\/[A-Za-z0-9._-]+\.js$/.test(probe)) {
  throw new Error('Compiled app and probe entries are required')
}
function dependencies(file, seen = new Set()) {
  if (seen.has(file)) return seen
  seen.add(file)
  const chunk = chunks.find(chunk => chunk.fileName === file)
  // Workspace and privacy routes are loaded lazily in the actual app. Their
  // shared modules still belong to the same compiled graph.
  for (const dependency of [...(chunk?.imports ?? []), ...(chunk?.dynamicImports ?? [])]) {
    dependencies(dependency, seen)
  }
  return seen
}
const appDependencies = dependencies(application), probeDependencies = dependencies(probe)
for (const module of ['workspace/telemetry-policy.ts', 'workspace/measured-client.ts']) {
  const matches = chunks.filter(chunk => Object.keys(chunk.modules).some(name => name.replaceAll('\\', '/').endsWith(module)))
  if (matches.length !== 1 || !appDependencies.has(matches[0].fileName) || !probeDependencies.has(matches[0].fileName)) {
    throw new Error('App and measurement entry must share their actual telemetry modules: ' + JSON.stringify({
      module, matches: matches.map(chunk => ({ file: chunk.fileName,
        app: appDependencies.has(chunk.fileName), probe: probeDependencies.has(chunk.fileName) })),
    }))
  }
}
function hashes(path, prefix = '') {
  return readdirSync(path, { withFileTypes: true }).flatMap(item => {
    const relative = prefix + item.name, full = join(path, item.name)
    return item.isDirectory() ? hashes(full, relative + '/')
      : [[relative, createHash('sha256').update(readFileSync(full)).digest('hex')]]
  })
}
writeFileSync(receipt, JSON.stringify({
  schema_version: 1, frontend: 'compiled', probe_entry: '/' + probe,
  shared_app_policy_and_client_modules: true,
  assets: Object.fromEntries(hashes(directory).sort(([left], [right]) => left.localeCompare(right))),
}, null, 2) + '\n', { flag: 'wx' })
