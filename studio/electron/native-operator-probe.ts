/** Private installed-gate operator checks. The outer hosting probe validates its profile. */
import { app, type BrowserWindow } from 'electron'
import { spawn } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import type { BackupConfiguration, LocalStatus } from '../shared/local-workspace.js'

function call(action: string, input: Record<string, unknown> = {}, workspace?: string | null, requestId: string = randomUUID()): Promise<any> {
  const executable = !app.isPackaged && process.env.MNEMION_LOCAL_ENGINE ? process.env.MNEMION_LOCAL_ENGINE :
    join(process.resourcesPath, 'engine', process.platform === 'win32' ? 'mnemion-engine.exe' : 'mnemion-engine')
  const directory = join(process.env.MNEMION_STUDIO_USER_DATA!, 'mnemion-desktop-control')
  return new Promise((resolve, reject) => {
    const child = spawn(executable, ['desktop-control', '--control-directory', directory, '--timeout', '180'], {
      stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true,
    })
    let output = '', failed = false
    const timer = setTimeout(() => { failed = true; child.kill(); reject(new Error('The installed operator client timed out.')) }, 200000)
    child.stderr.resume()
    child.stdin.on('error', () => {})
    child.stdout.on('data', bytes => {
      output += bytes.toString('utf8')
      if (Buffer.byteLength(output) > 300000) { failed = true; child.kill(); reject(new Error('The installed operator client returned excessive output.')) }
    })
    child.on('error', () => { failed = true; reject(new Error('The installed operator client could not start.')) })
    child.on('close', code => {
      clearTimeout(timer)
      if (failed) return
      try {
        const value = JSON.parse(output)
        if (![0, 1].includes(code!) || typeof value.ok !== 'boolean' || value.request_id !== requestId) throw new Error()
        resolve(value)
      } catch { reject(new Error('The installed operator client did not return a bounded matching result.')) }
    })
    child.stdin.end(JSON.stringify({ action, input, request_id: requestId,
      ...(workspace !== undefined ? { expected_workspace_id: workspace } : {}) }))
  })
}

async function success(action: string, input: Record<string, unknown> = {}, workspace?: string | null, id?: string): Promise<any> {
  const result = await call(action, input, workspace, id)
  if (!result.ok) throw new Error(`Installed operator ${action} failed: ${result.message ?? result.error}`)
  return result.result
}

export { success as callNativeOperator }

async function ui(window: BrowserWindow, expression: string): Promise<void> {
  await window.webContents.executeJavaScript(`(async()=>{
    const end = Date.now() + 90000;
    while(Date.now() < end){if(await (${expression}))return;await new Promise(r=>setTimeout(r,100));}
    throw new Error('The desktop did not reflect its local operator change.');
  })()`)
}

export async function verifyNativeOperator(window: BrowserWindow, phase: string): Promise<Record<string, boolean>> {
  await ui(window, `(async()=>{ const s = await window.mnemion.localStatus(); if(s.operator?.state === 'unavailable')throw new Error(s.operator.message); return s.operator?.state === 'ready'; })()`)
  const status = await success('status') as LocalStatus
  const workspace = status.info?.settings?.workspace_id
  if (!workspace || status.operator?.state !== 'ready') throw new Error('The installed operator did not identify its live local workspace.')
  const catalog = await success('catalog')
  if (catalog.scope !== 'owning_os_account' || !catalog.operations['backup.configure']?.workspace || !catalog.operations['recovery.use']) throw new Error('The desktop operator catalog is incomplete.')
  const appStatus = await success('app.status')
  if (appStatus.version !== app.getVersion() || appStatus.platform !== process.platform ||
      typeof appStatus.preferences?.automaticUpdates !== 'boolean' || typeof appStatus.managed !== 'boolean' ||
      appStatus.regular_check_seconds?.minimum !== 21600 || !catalog.operations['app.update-restart']) {
    throw new Error('The installed operator could not inspect this app’s update policy.')
  }
  if (phase === 'backup-capture') {
    const initial = (await success('backup.status')).configuration as BackupConfiguration
    const settings = { expected_revision: initial.revision, destination: initial.destination, enabled: false,
      snapshot_hours: initial.snapshot_hours, ledger_minutes: initial.ledger_minutes, key_saved: true }
    const id = randomUUID()
    const paused = await success('backup.configure', settings, workspace, id)
    if (paused.configuration.enabled || !paused.configuration.protected_key) throw new Error('Operator schedule pause lost its protected key.')
    await ui(window, `(async()=>{ const view = await window.mnemion.localBackupStatus(); const label = [...document.querySelectorAll('.ws-backup-panel label')].find(e=>e.textContent.includes('Back up automatically'));return view.configuration?.enabled === false && label?.querySelector('input')?.checked === false; })()`)
    const repeated = await success('backup.configure', settings, workspace, id)
    if (repeated.configuration.revision !== paused.configuration.revision) throw new Error('A retried operator request configured backups twice.')
    const stale = await call('backup.configure', settings, workspace)
    const wrong = await call('backup.configure', { ...settings, expected_revision: paused.configuration.revision }, randomUUID())
    if (stale.ok || wrong.ok) throw new Error('A stale operator observation changed the local backup policy.')
    const resumed = await success('backup.configure', { ...settings, expected_revision: paused.configuration.revision, enabled: true }, workspace)
    if (!resumed.configuration.enabled || !resumed.configuration.protected_key) throw new Error('The operator could not resume the protected schedule.')
    await ui(window, `(async()=>{const view=await window.mnemion.localBackupStatus();return view.configuration?.enabled===true;})()`)
    const fixture = JSON.parse(await readFile(join(dirname(process.env.MNEMION_STUDIO_USER_DATA!), 'native-backup-fixture.json'), 'utf8'))
    const ledger = await success('backup.run', { ledger_only: true }, workspace)
    const snapshot = await success('backup.inspect', { source: fixture.snapshot.file, recovery_key: fixture.key }, workspace)
    const inspectedLedger = await success('backup.inspect', { source: ledger.ledger.file, recovery_key: fixture.key }, workspace)
    if (!snapshot.authenticated || !snapshot.archive_verified || !inspectedLedger.authenticated || snapshot.sha256 !== fixture.snapshot.sha256) throw new Error('Operator inspection did not authenticate the selected recovery files.')
    const recovered = await success('backup.restore', { source: fixture.snapshot.file, ledger_source: ledger.ledger.file,
      recovery_key: fixture.key, snapshot_sha256: snapshot.sha256, ledger_sha256: inspectedLedger.sha256,
      primary_tenant_id: fixture.tenantId, trusted_backup_confirmed: true }, workspace)
    const unchanged = await success('status') as LocalStatus
    if (!recovered.receipt.keys_rotated || !recovered.receipt.external_connections_require_review || recovered.receipt.source_workspace_id !== workspace || unchanged.info?.settings?.workspace_id !== workspace) throw new Error('The operator restore did not preserve the original host and reset access.')
    return { nativeOperatorPipe: true, nativeAppUpdateStatus: true, operatorScheduleAndUiAgree: true, operatorRetryDoesNotRepeat: true,
      operatorStaleIdentityRefused: true, operatorRefreshesLedger: true, operatorInspectsEncryptedFiles: true, operatorRestoresIndependentCopy: true }
  }
  if (phase === 'backup-resume') {
    const copies = await success('recovery.list')
    const copy = copies.find((item: any) => item.receipt.source_workspace_id === workspace)
    if (!copy) throw new Error('The operator could not discover the verified recovery copy.')
    await ui(window, 'window.mnemion.updateSafety()')
    await window.webContents.executeJavaScript(`(()=>{const input=document.createElement('textarea');input.id='native-operator-draft';document.body.append(input);input.value='Unsaved disposable draft';input.dispatchEvent(new Event('input',{bubbles:true}));})()`)
    try {
      const refused = await call('recovery.use', { id: copy.id }, workspace)
      if (refused.ok || !refused.message?.includes('Save or discard edits')) throw new Error('A local operator discarded an unsaved desktop draft.')
      if ((await success('status')).info?.settings?.workspace_id !== workspace) throw new Error('Refusing an unsaved draft still switched its workspace.')
    } finally { await window.webContents.executeJavaScript("document.getElementById('native-operator-draft')?.remove()") }
    await ui(window, 'window.mnemion.updateSafety()')
    const selected = await success('recovery.use', { id: copy.id }, workspace) as LocalStatus
    if (selected.preferences?.recoveryRoot !== copy.id || selected.info?.settings?.workspace_id !== copy.receipt.workspace_id) throw new Error('The operator did not select the verified copy.')
    await ui(window, `(async()=>{const s=await window.mnemion.localStatus();const w=await window.mnemion.workspaceStatus();return s.state==='running' && s.preferences?.recoveryRoot===${JSON.stringify(copy.id)} && !!w.active && !!document.querySelector('.ws-workspace-name');})()`)
    await ui(window, 'window.mnemion.updateSafety()')
    const returned = await success('recovery.use', { id: null }, copy.receipt.workspace_id) as LocalStatus
    if (returned.preferences?.recoveryRoot || returned.info?.settings?.workspace_id !== workspace) throw new Error('The operator did not preserve the original workspace selection.')
    await ui(window, `(async()=>{const s=await window.mnemion.localStatus();const w=await window.mnemion.workspaceStatus();return s.state==='running' && !s.preferences?.recoveryRoot && !!w.active && !!document.querySelector('.ws-workspace-name');})()`)
    return { nativeOperatorPipe: true, nativeAppUpdateStatus: true, operatorRecoverySelection: true, operatorOriginalSelection: true, operatorPreservesUnsavedDraft: true }
  }
  return { nativeOperatorPipe: true, nativeAppUpdateStatus: true }
}
