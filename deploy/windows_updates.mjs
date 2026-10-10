/** Sign/verify full Windows installers without an OS publisher certificate. */
import { createHash, createPrivateKey, createPublicKey, sign, verify } from 'node:crypto'
import { createReadStream, lstatSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const releaseBase = 'https://github.com/Perseusxrltd/mnemion/releases'
const args = process.argv.slice(2)
const command = args.shift()
function option(name, fallback) {
  const index = args.indexOf(name)
  return index === -1 ? fallback : args[index + 1]
}
function checkedBase64(value, length) {
  if (typeof value !== 'string') throw new Error('Invalid signing data')
  const raw = Buffer.from(value, 'base64')
  if (raw.toString('base64') !== value || (length !== undefined && raw.length !== length)) throw new Error('Invalid signing data')
  return raw
}
async function sha512(path) {
  const hash = createHash('sha512')
  for await (const bytes of createReadStream(path, { highWaterMark: 1024 * 1024 })) hash.update(bytes)
  return hash.digest('base64')
}
try {
  if (!['sign', 'verify'].includes(command)) throw new Error('Use sign or verify')
  const architecture = option('--arch', process.arch)
  const directory = resolve(option('--artifacts', join(root, 'dist-electron')))
  const version = JSON.parse(readFileSync(join(root, 'studio/electron/package.json'), 'utf8')).version
  if (!['x64', 'arm64'].includes(architecture)
    || !/^(0|[1-9]\d{0,7})\.(0|[1-9]\d{0,7})\.(0|[1-9]\d{0,7})$/.test(version)
    || Number(version.split('.')[0]) < 4) throw new Error('Invalid stable release target')
  const trust = JSON.parse(readFileSync(join(root, 'studio/electron/native/windows-updates.json'), 'utf8'))
  if (trust.schema !== 1 || trust.algorithm !== 'ed25519') throw new Error('Invalid update trust configuration')
  const publicKey = createPublicKey({ key: Buffer.concat([Buffer.from('302a300506032b6570032100', 'hex'), checkedBase64(trust.publicKey, 32)]), type: 'spki', format: 'der' })
  const filename = `Mnemion-Studio-${version}-windows-${architecture}.exe`
  const installer = join(directory, filename)
  const before = lstatSync(installer)
  if (!before.isFile() || before.isSymbolicLink() || before.size < 40 * 1024 ** 2 || before.size > 1024 ** 3) throw new Error('Missing or unsafe Windows installer')
  const payload = { schema: 1, application: 'com.perseusxr.mnemion-studio', platform: 'windows', architecture,
    version, filename, url: `${releaseBase}/download/v${version}/${filename}`, size: before.size, sha512: await sha512(installer) }
  const after = lstatSync(installer)
  if (after.isSymbolicLink() || before.size !== after.size || before.ino !== after.ino || before.mtimeMs !== after.mtimeMs) throw new Error('Installer changed while hashing')
  const feed = join(directory, `latest-${architecture}-windows.json`)
  if (command === 'sign') {
    const encoded = process.env.MNEMION_WINDOWS_UPDATE_PRIVATE_KEY
    delete process.env.MNEMION_WINDOWS_UPDATE_PRIVATE_KEY
    const privateKey = createPrivateKey({ key: checkedBase64(encoded), type: 'pkcs8', format: 'der' })
    if (privateKey.asymmetricKeyType !== 'ed25519'
      || !createPublicKey(privateKey).export({ type: 'spki', format: 'der' }).equals(publicKey.export({ type: 'spki', format: 'der' }))) throw new Error('Signing key does not match the installed public key')
    const raw = Buffer.from(JSON.stringify(payload))
    writeFileSync(feed, JSON.stringify({ schema: 1, payload: raw.toString('base64'), signature: sign(null, raw, privateKey).toString('base64') }) + '\n')
  }
  const stat = lstatSync(feed)
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 16 * 1024) throw new Error('Unsafe update manifest')
  const envelope = JSON.parse(readFileSync(feed, 'utf8'))
  if (envelope.schema !== 1 || Object.keys(envelope).sort().join(',') !== 'payload,schema,signature') throw new Error('Unsupported signed envelope')
  const raw = checkedBase64(envelope.payload)
  if (!verify(null, raw, publicKey, checkedBase64(envelope.signature, 64))) throw new Error('Windows update signature is invalid')
  const metadata = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw))
  if (Object.keys(metadata).sort().join(',') !== Object.keys(payload).sort().join(',')
    || Object.keys(payload).some(key => payload[key] !== metadata[key])) throw new Error('Signed manifest disagrees with the release installer')
  // Keep per-platform checksums complete after adding the authenticated feed.
  if (command === 'sign') {
    const checksumFile = join(directory, `SHA256SUMS-win32-${architecture}.txt`)
    const existing = readFileSync(checksumFile, 'utf8').split('\n').filter(line => line && !line.endsWith(`  latest-${architecture}-windows.json`))
    existing.push(`${createHash('sha256').update(readFileSync(feed)).digest('hex')}  latest-${architecture}-windows.json`)
    writeFileSync(checksumFile, existing.join('\n') + '\n')
  }
  console.log(JSON.stringify({ platform: 'windows', architecture, version, manifest: `latest-${architecture}-windows.json`, verified: true, osPublisherCertificateRequired: false }))
} catch {
  // Do not include input, private-key parser errors or request URLs in build logs.
  console.error('Windows update signing/verification failed: check the release files, public key and protected signing secret.')
  process.exitCode = 1
}
