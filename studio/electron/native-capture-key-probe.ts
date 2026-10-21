/** Lost saved keys in the existing disposable, two-launch capture journey. */
import type { BrowserWindow } from 'electron'
import { createHash } from 'node:crypto'
import { readFile, rm, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { callNativeOperator as call } from './native-operator-probe.js'
import { inRenderer, pauseSource, sourceStatus } from './native-capture-probe.js'

const hash = (value: Buffer) => createHash('sha256').update(value).digest('hex')
const heldPath = (probe: string) => join(dirname(probe), 'native-capture-held-keys.private.json')
const sourceRoot = () => join(process.env.MNEMION_STUDIO_USER_DATA!, 'mnemion-desktop-sources')

async function evidence(id: string) {
  const root = sourceRoot()
  return { database: hash(await readFile(join(root, 'inbox-' + id, 'inbox.sqlite3'))),
    enrollment: hash(await readFile(join(root, 'inbox-enrollment-' + id + '.json'))) }
}

async function unchanged(id: string, expected: { database: string; enrollment: string }) {
  const actual = await evidence(id)
  if (actual.database !== expected.database || actual.enrollment !== expected.enrollment) throw new Error('A lost-key control changed accepted evidence or its enrollment.')
}

export async function holdNativeCaptureKeys(id: string, probe: string) {
  if ((await sourceStatus(id)).source.enabled) throw new Error('Pause the private fixture before simulating key loss.')
  const path = join(sourceRoot(), 'sources.json'), document = JSON.parse(await readFile(path, 'utf8'))
  const source = document.sources.find((item: any) => item.id === id)
  if (!source?.sealed_key || !source.sealed_inbox_key) throw new Error('The fixture has no original protected keys to preserve.')
  const held = { id, sealed_key: source.sealed_key, sealed_inbox_key: source.sealed_inbox_key, ...await evidence(id) }
  // Preserve the exact original ciphertext before the destructive fixture edit.
  await writeFile(heldPath(probe), JSON.stringify(held), { mode: 0o600, flag: 'wx' })
  delete source.sealed_key
  source.sealed_inbox_key = '%unavailable-protected-inbox%'
  await writeFile(path, JSON.stringify(document), { mode: 0o600 })
  // The controller still caches the original keys. Pause must write only its
  // flag using the current disk record, never restore that cached ciphertext.
  await pauseSource(id)
  const paused = JSON.parse(await readFile(path, 'utf8')).sources.find((item: any) => item.id === id)
  if (paused.enabled || paused.sealed_key !== undefined || paused.sealed_inbox_key !== source.sealed_inbox_key) throw new Error('Pausing after key loss replaced saved private material.')
  await unchanged(id, held)
}

export async function restoreNativeCaptureKeys(window: BrowserWindow, id: string, connector: string, probe: string) {
  const held = JSON.parse(await readFile(heldPath(probe), 'utf8'))
  if (held.id !== id) throw new Error('The lost-key fixture belongs to a different source.')
  const current = await sourceStatus(id)
  if (current.source.enabled) throw new Error('The lost-key source resumed during app restart.')
  await inRenderer(window, `await selectConnection(${JSON.stringify(connector)});await until(()=>card()?.querySelector('.ws-badge')?.textContent==='Paused','Lost keys prevented the source controls from reopening');`)
  let refused = false
  try { await call('source.pause', { id, expected_revision: current.view.revision, enabled: true }) }
  catch { refused = true }
  if (!refused || (await sourceStatus(id)).source.enabled) throw new Error('Missing keys were accepted for a new source start.')
  await unchanged(id, held)
  const path = join(sourceRoot(), 'sources.json'), document = JSON.parse(await readFile(path, 'utf8'))
  const source = document.sources.find((item: any) => item.id === id)
  if (!source || source.sealed_key !== undefined || source.sealed_inbox_key !== '%unavailable-protected-inbox%') throw new Error('The lost-key evidence changed before explicit recovery.')
  source.sealed_key = held.sealed_key; source.sealed_inbox_key = held.sealed_inbox_key
  await writeFile(path, JSON.stringify(document), { mode: 0o600 })
  // Re-read only the exact recovered ciphertext through the ordinary pause path.
  await pauseSource(id)
  const recovered = JSON.parse(await readFile(path, 'utf8')).sources.find((item: any) => item.id === id)
  if (recovered.enabled || recovered.sealed_key !== held.sealed_key || recovered.sealed_inbox_key !== held.sealed_inbox_key) throw new Error('Exact-key recovery changed the protected source.')
  await unchanged(id, held)
  await discardHeldCaptureKeys(probe)
  return { nativeCaptureKeyLossControlsAfterRestart: true, nativeCaptureLostKeysRefuseResume: true,
    nativeCaptureOriginalKeysRestoreAcceptedEvidence: true }
}

export async function discardHeldCaptureKeys(probe: string) {
  await rm(heldPath(probe))
}
