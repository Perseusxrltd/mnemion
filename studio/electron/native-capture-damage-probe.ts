/** Real private-file failures must preserve accepted evidence and local pause. */
import type { BrowserWindow } from 'electron'
import { readFile, rename, stat, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { callNativeOperator as call } from './native-operator-probe.js'
import { inRenderer, pauseSource, sourceStatus, until } from './native-capture-probe.js'
import { captureMessages } from './capture-messages.js'
import type { NativeCaptureRelay } from './native-capture-relay.js'

export async function verifyNativeCaptureDamage(window: BrowserWindow, id: string, connector: string, relay: NativeCaptureRelay) {
  const root = join(process.env.MNEMION_STUDIO_USER_DATA!, 'mnemion-desktop-sources')
  const marker = join(root, 'inbox-enrollment-' + id + '.json'), database = join(root, 'inbox-' + id, 'inbox.sqlite3')
  const savedKey = async () => JSON.parse(await readFile(join(root, 'sources.json'), 'utf8')).sources.find((source: any) => source.id === id)?.sealed_inbox_key
  const key = await savedKey(), posts = relay.pages.length
  if (!key || (await stat(database)).size > 16 * 1024 * 1024) throw new Error('Use the bounded disposable capture fixture for damage validation.')
  async function runHealthy() {
    const before = await sourceStatus(id), previous = before.source.activity.finished_at
    if (before.source.enabled) throw new Error('Pause the fixture before its next damaged-file case.')
    await call('source.pause', { id, expected_revision: before.view.revision, enabled: true })
    await until(async () => {
      relay.check()
      const { source } = await sourceStatus(id), report = source.activity.report?.capture
      return source.activity.phase !== 'scanning' && source.activity.finished_at !== previous &&
        report?.pending_events === 1 && report.stored_events === 1 && report.forgotten_events === 2 &&
        report.reason_code === 'capture_delivery_unavailable'
    }, 'The original accepted queue did not reopen before its damage test.')
  }
  const cases = [
    { path: marker, missing: true, app: true, reason: 'capture_enrollment_missing', flag: 'nativeCaptureMissingEnrollmentStillPauses' },
    { path: marker, missing: false, app: false, reason: 'capture_binding_mismatch', flag: 'nativeCaptureDamagedEnrollmentStillPauses' },
    { path: database, missing: true, app: true, reason: 'capture_inbox_missing', flag: 'nativeCaptureMissingDatabasePreservesEvidence' },
    { path: database, missing: false, app: false, reason: 'capture_storage_unavailable', flag: 'nativeCaptureDamagedDatabasePreservesEvidence' },
  ] as const
  const receipt: Record<string, boolean> = {}
  for (const item of cases) {
    await runHealthy()
    const original = await readFile(item.path), originalDatabase = await readFile(database), originalMarker = await readFile(marker)
    const held = item.path + '.capture-test-held'
    if (await stat(held).then(() => true, () => false)) throw new Error('An earlier damaged-file fixture remains; preserve it for inspection.')
    const damaged = Buffer.from(item.path === marker ? '{"damaged_fixture":true}\n' : 'damaged inbox fixture\n')
    if (item.missing) await rename(item.path, held)
    else await writeFile(item.path, damaged)
    try {
      const before = await sourceStatus(id), finished = before.source.activity.finished_at
      await call('source.sync', { id, expected_revision: before.view.revision })
      await until(async () => {
        const { source } = await sourceStatus(id)
        return source.activity.phase === 'attention' && source.activity.finished_at !== finished &&
          source.activity.reason_code === item.reason && source.activity.durability === 'saved'
      }, 'The damaged native inbox did not stop with its specific durable failure: ' + item.reason)
      if (item.app) {
        await inRenderer(window, `
          await selectConnection(${JSON.stringify(connector)});await click('Pause on this computer');
          await until(async()=>{const source=(await window.mnemion.sourceStatus()).sources.find(s=>s.id===${JSON.stringify(id)});return source?.enabled===false&&card()?.querySelector('.ws-badge')?.textContent==='Paused';},'The real app could not pause the damaged source');
        `)
      } else await pauseSource(id)
      const paused = await sourceStatus(id)
      if (paused.source.enabled || paused.source.activity.last_failure?.reason_code !== item.reason || await savedKey() !== key) throw new Error('Pausing a damaged source changed its key or lost its failure record.')
      if (item.missing) {
        if (await stat(item.path).then(() => true, () => false) || !(await readFile(held)).equals(original)) throw new Error('A missing initialized capture file was recreated or replaced.')
      } else if (!(await readFile(item.path)).equals(damaged)) throw new Error('A damaged capture file was overwritten during pause.')
      if (item.path !== database && !(await readFile(database)).equals(originalDatabase) ||
          item.path !== marker && !(await readFile(marker)).equals(originalMarker)) throw new Error('A damaged-file attempt changed its accepted evidence or enrollment.')
      if (item.path === marker) {
        let refused = false
        try { await call('source.pause', { id, expected_revision: paused.view.revision, enabled: true }) }
        catch (error) { refused = error instanceof Error && error.message.endsWith(captureMessages[item.reason]) }
        if (!refused || (await sourceStatus(id)).source.enabled) throw new Error('Local pause bypassed validation of the missing or damaged capture enrollment.')
      }
      receipt[item.flag] = true
    } finally {
      try { if ((await sourceStatus(id)).source.enabled) await pauseSource(id) }
      finally {
        // Restore only the exact private fixture bytes saved before this case.
        // A successful recovery must reopen the accepted inbox, never reset it.
        if (item.missing) await rename(held, item.path)
        else await writeFile(item.path, original)
      }
    }
  }
  await runHealthy(); await pauseSource(id)
  relay.check()
  if (relay.pages.length !== posts || await savedKey() !== key) throw new Error('Recovering the matching private files repeated delivery or replaced the inbox key.')
  return { ...receipt, nativeCaptureMatchingFilesReopenAcceptedQueue: true }
}
