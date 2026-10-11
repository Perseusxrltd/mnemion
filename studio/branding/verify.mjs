/** Packaging checks committed renders without installing the image renderer. */
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const directory = dirname(fileURLToPath(import.meta.url))
const root = resolve(directory, '../..')
const digest = path => createHash('sha256').update(readFileSync(path)).digest('hex')

export function verifyBranding(builtDirectory) {
  const manifest = JSON.parse(readFileSync(resolve(directory, 'assets.json'), 'utf8'))
  if (digest(resolve(root, manifest.source)) !== manifest.source_sha256) {
    throw new Error('The Mnemion logo changed. Run npm --prefix studio/branding ci && npm --prefix studio/branding run build.')
  }
  for (const [name, asset] of Object.entries(manifest.files)) {
    for (const folder of [resolve(directory, '../frontend/public'), ...(builtDirectory ? [builtDirectory] : [])]) {
      if (digest(resolve(folder, name)) !== asset.sha256) throw new Error(`Outdated Mnemion brand asset: ${name} in ${folder}`)
    }
  }
  for (const [path, asset] of Object.entries(manifest.aliases)) {
    if (digest(resolve(root, path)) !== manifest.files[asset].sha256) throw new Error(`Outdated Mnemion brand alias: ${path}`)
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  verifyBranding(process.argv[2] ? resolve(process.argv[2]) : undefined)
  console.log('Mnemion brand assets match the canonical logo.')
}
