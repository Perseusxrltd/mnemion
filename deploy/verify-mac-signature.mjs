// Release verification only. Installed Macs use Sparkle's native verifier.
import { createPublicKey, verify } from 'node:crypto'
import { readFileSync, lstatSync } from 'node:fs'

const [archive, publicValue, signatureValue] = process.argv.slice(2)
const stat = lstatSync(archive)
if (!stat.isFile() || stat.size < 1 || stat.size > 1024 * 1024 * 1024) throw new Error('Invalid archive size or type')
const raw = Buffer.from(publicValue, 'base64')
const signature = Buffer.from(signatureValue, 'base64')
if (raw.length !== 32 || signature.length !== 64
  || raw.toString('base64') !== publicValue || signature.toString('base64') !== signatureValue) throw new Error('Invalid signing metadata')
const publicKey = createPublicKey({ key: Buffer.concat([Buffer.from('302a300506032b6570032100', 'hex'), raw]), format: 'der', type: 'spki' })
if (!verify(null, readFileSync(archive), publicKey, signature)) throw new Error('Update archive signature does not match the installed public key')
