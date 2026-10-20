/** Render the existing Studio mark once for every OS; no network or image service. */
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { dirname, resolve, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

const directory = dirname(fileURLToPath(import.meta.url))
const output = resolve(directory, '../frontend/public')
const source = await readFile(join(directory, 'mnemion.svg'), 'utf8')
// OS menu bars supply their own background and tint template images themselves.
const symbol = source.replace(/\s*<rect[^>]+\/>/, '')
const monochrome = symbol.replace(/#[a-f0-9]{6}/gi, '#000000')
const assets = new Map()
const png = async (svg, size) => sharp(Buffer.from(svg), { density: 192 }).resize(size, size).png({ compressionLevel: 9, adaptiveFiltering: false }).toBuffer()
const image = async size => png(size <= 32 ? source.replace('stroke-width="1.6"', 'stroke-width="2"') : source, size)

assets.set('mnemion.svg', Buffer.from(source))
assets.set('mnemion-symbol.svg', Buffer.from(symbol))
assets.set('icon.png', await image(1024))
assets.set('icon-16.png', await image(16))
assets.set('icon-32.png', await image(32))
assets.set('icon-180.png', await image(180))
assets.set('icon-tray.png', await image(32))
assets.set('icon-tray@2x.png', await image(64))
assets.set('icon-trayTemplate.png', await png(monochrome, 20))
assets.set('icon-trayTemplate@2x.png', await png(monochrome, 40))

// Modern Windows ICO supports lossless PNG entries; include actual small sizes
// rather than relying on Explorer to shrink a single large bitmap.
const sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
const bitmaps = await Promise.all(sizes.map(image))
const header = Buffer.alloc(6 + sizes.length * 16)
header.writeUInt16LE(1, 2); header.writeUInt16LE(sizes.length, 4)
let offset = header.length
for (const [index, size] of sizes.entries()) {
  const entry = 6 + index * 16
  header[entry] = header[entry + 1] = size === 256 ? 0 : size
  header.writeUInt16LE(1, entry + 4); header.writeUInt16LE(32, entry + 6)
  header.writeUInt32LE(bitmaps[index].length, entry + 8); header.writeUInt32LE(offset, entry + 12)
  offset += bitmaps[index].length
}
assets.set('icon.ico', Buffer.concat([header, ...bitmaps]))

const entries = []
for (const [type, size] of [['icp4', 16], ['icp5', 32], ['icp6', 64], ['ic07', 128], ['ic08', 256], ['ic09', 512], ['ic10', 1024], ['ic11', 32], ['ic12', 64], ['ic13', 256], ['ic14', 512]]) {
  const bitmap = await image(size)
  const entry = Buffer.alloc(8)
  entry.write(type); entry.writeUInt32BE(8 + bitmap.length, 4)
  entries.push(entry, bitmap)
}
const icnsHeader = Buffer.alloc(8)
icnsHeader.write('icns'); icnsHeader.writeUInt32BE(8 + entries.reduce((sum, part) => sum + part.length, 0), 4)
assets.set('icon.icns', Buffer.concat([icnsHeader, ...entries]))

await mkdir(output, { recursive: true })
for (const [name, content] of assets) await writeFile(join(output, name), content)
// Preserve the historical documentation asset URL with the same current mark.
const aliases = { 'assets/mnemion_logo.png': 'icon.png', 'mnemion/assets/connector-icon.png': 'icon.png' }
for (const [path, asset] of Object.entries(aliases)) {
  await mkdir(dirname(resolve(directory, '../..', path)), { recursive: true })
  await writeFile(resolve(directory, '../..', path), assets.get(asset))
}
await writeFile(join(directory, 'assets.json'), JSON.stringify({
  source: 'studio/branding/mnemion.svg',
  source_sha256: createHash('sha256').update(source).digest('hex'),
  renderer: `sharp ${sharp.versions.sharp}`,
  aliases,
  files: Object.fromEntries([...assets].map(([name, content]) => [name, { bytes: content.length, sha256: createHash('sha256').update(content).digest('hex') }])),
}, null, 2) + '\n')
console.log(`Rendered ${assets.size} Mnemion assets from the existing Studio logo.`)
