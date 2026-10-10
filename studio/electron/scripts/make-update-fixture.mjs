// Repack a disposable copy, retaining the actual compiled DesktopUpdates class.
import { extractAll, createPackageWithOptions, getRawHeader } from '@electron/asar'
import { readFileSync, writeFileSync, copyFileSync, mkdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createHash } from 'node:crypto'

const [resources, directory] = process.argv.slice(2)
const archive = join(resources, 'app.asar')
mkdirSync(directory, { recursive: false })
extractAll(archive, directory)
const path = join(directory, 'package.json')
const manifest = JSON.parse(readFileSync(path, 'utf8'))
manifest.main = 'update-fixture.mjs'
writeFileSync(path, JSON.stringify(manifest))
copyFileSync(join(dirname(fileURLToPath(import.meta.url)), 'update-fixture.mjs'), join(directory, 'update-fixture.mjs'))
await createPackageWithOptions(directory, archive, {})
console.log(createHash('sha256').update(getRawHeader(archive).headerString).digest('hex'))
