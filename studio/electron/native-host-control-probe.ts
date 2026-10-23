/** Real packaged UI, agent pipe and SSH peer; the peer never runs a memory service. */
import { app, type BrowserWindow } from 'electron'
import { readFile, stat } from 'node:fs/promises'
import { join } from 'node:path'
import { callNativeOperator } from './native-operator-probe.js'

async function view(window: BrowserWindow, expression: string): Promise<any> {
  return window.webContents.executeJavaScript(`(async () => {
    const end = Date.now() + 20000;
    while (Date.now() < end) {
      const value = await (${expression});
      if (value) return value;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error('The native host-control view did not complete its expected action');
  })()`)
}

export async function verifyNativeHostControl(window: BrowserWindow): Promise<Record<string, unknown> | null> {
  const path = process.env.MNEMION_STUDIO_WORKSPACE_PROBE
  if (!path || !process.env.MNEMION_STUDIO_SMOKE_FILE || process.env.MNEMION_STUDIO_HOSTING_PROBE) return null
  if ((await stat(path)).size > 16384) throw new Error('Invalid host-client fixture configuration')
  const config = JSON.parse(await readFile(path, 'utf8'))
  if (!['save', 'resume'].includes(config.phase) || typeof config.credential !== 'string' ||
      !/^[A-Za-z0-9_-]{32,128}$/.test(config.credential) || typeof config.endpoint !== 'string' ||
      !/^http:\/\/127\.0\.0\.1:\d{1,5}\/organization$/.test(config.endpoint)) throw new Error('Invalid native loopback peer')
  await window.webContents.executeJavaScript("location.hash = '/hosts'")
  await view(window, "document.querySelector('.ws-host-page h1')?.textContent.includes('Host controls') && !document.querySelector('.ws-host-progress')")
  const initial = await callNativeOperator('host.profiles')
  if (!initial.secure_storage) {
    let refused = false
    try { await callNativeOperator('host.create', { name: 'Locked native host login' }) } catch { refused = true }
    if (!refused || (await callNativeOperator('host.profiles')).profiles.length) throw new Error('An unavailable keychain stored a host login')
    return { phase: config.phase, available: false, plaintextFallbackRefused: true, nativeAgentPipe: true }
  }
  const name = 'Native protected host operator'
  if (config.phase === 'save') {
    if (initial.profiles.length) throw new Error('Native host fixture requires a clean profile')
    await window.webContents.executeJavaScript(`(() => {
      const label = [...document.querySelectorAll('.ws-host-page label')].find(item => item.textContent.includes('New device or agent name'));
      const input = label?.querySelector('input');
      if (!input) throw new Error('Native host creation field is missing');
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, ${JSON.stringify(name)});
      input.dispatchEvent(new Event('input', { bubbles: true }));
    })()`)
    await view(window, `(() => {
      const button = [...document.querySelectorAll('.ws-host-page button')].find(item => item.textContent.trim() === 'Create host login');
      if (!button || button.disabled) return false;
      button.click(); return true;
    })()`)
    const profile = await view(window, `(async () => (await window.mnemion.hostControl('host.profiles')).profiles.find(item => item.name === ${JSON.stringify(name)}))()`)
    const response = await fetch(config.endpoint + '/_fixture/host', {
      method: 'POST', headers: { Authorization: 'Bearer ' + config.credential, 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, public_key: profile.public_key, role: 'operator', expires_at: null }),
      signal: AbortSignal.timeout(18000),
    })
    if (!response.ok) throw new Error('The native loopback peer could not enroll the public key')
    const connection = await response.json()
    await view(window, "document.querySelector('.ws-host-page textarea') && !document.querySelector('.ws-host-progress')")
    await window.webContents.executeJavaScript(`(() => {
      const field = document.querySelector('.ws-host-page textarea');
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(field, ${JSON.stringify(JSON.stringify(connection))});
      field.dispatchEvent(new Event('input', { bubbles: true }));
    })()`)
    await view(window, `(() => {
      const box = [...document.querySelectorAll('.ws-host-page label')].find(item => item.textContent.includes('I verified this host and server fingerprint'))?.querySelector('input');
      if (!box) return false; if (!box.checked) box.click(); return true;
    })()`)
    await view(window, `(() => {
      const button = [...document.querySelectorAll('.ws-host-page button')].find(item => item.textContent.trim() === 'Save host connection');
      if (!button || button.disabled) return false; button.click(); return true;
    })()`)
    await view(window, "[...document.querySelectorAll('.ws-host-page dd')].some(item => item.textContent === 'operator') && !document.querySelector('.ws-host-progress')")
    const observed = await callNativeOperator('host.inspect', { id: profile.id })
    if (!observed.status.ok || observed.status.result.operator.role !== 'operator' ||
        observed.status.result.service.running !== false || !observed.status.result.service.native_transport_fixture) throw new Error('The native host client did not authenticate independently of a memory API')
    const schema = await callNativeOperator('host.schema')
    if (!schema.roles.operator.includes('backup.create') || !schema.roles.operator.includes('backup.verify')) throw new Error('The packaged native agent is missing backup operations')
    let unapprovedBackupRefused = false
    try {
      await callNativeOperator('host.request', { id: profile.id, request: {
        protocol: 1, host_id: connection.host_id, request_id: crypto.randomUUID(), action: 'backup.create',
        issued_at: new Date().toISOString(), valid_until: new Date(Date.now() + 600000).toISOString(),
        configuration_sha256: observed.status.result.service.backups.configuration_sha256,
        approve_backup_transfer: false,
      } })
    } catch { unapprovedBackupRefused = true }
    if (!unapprovedBackupRefused || (await callNativeOperator('host.profiles')).profiles[0].last_operation) throw new Error('An unapproved native backup request was recorded')
    await view(window, `(() => {
      const section = document.querySelector('[aria-labelledby="host-backups-heading"]');
      const box = section?.querySelector('input[type=checkbox]');
      const create = [...(section?.querySelectorAll('button') ?? [])].find(item => item.textContent === 'Create encrypted backup');
      const verify = [...(section?.querySelectorAll('button') ?? [])].find(item => item.textContent === 'Verify stored copy');
      return !!(box && !box.checked && create?.disabled && verify?.disabled && section.querySelector('tbody tr'));
    })()`)
    await window.webContents.executeJavaScript(`document.querySelector('[aria-labelledby="host-backups-heading"] input[type=checkbox]').click()`)
    await view(window, `(() => {
      const buttons = [...document.querySelectorAll('[aria-labelledby="host-backups-heading"] button')];
      return buttons.length === 2 && buttons.every(button => !button.disabled);
    })()`)
    await window.webContents.executeJavaScript(`document.querySelector('[aria-labelledby="host-backups-heading"] input[type=checkbox]').click()`)
    await window.webContents.executeJavaScript(`(() => {
      const box = [...document.querySelectorAll('.ws-host-page label')].find(item => item.textContent.includes('I approve service changes and possible interruption'))?.querySelector('input');
      if (!box) throw new Error('Native host service approval is missing'); box.click();
    })()`)
    await view(window, `(() => {
      const button = [...document.querySelectorAll('.ws-host-page button')].find(item => item.textContent.trim() === 'Stop memory service');
      if (!button || button.disabled) return false; button.click(); return true;
    })()`)
    const saved = await view(window, `(async () => {
      const item = (await window.mnemion.hostControl('host.profiles')).profiles.find(item => item.id === ${JSON.stringify(profile.id)});
      return item?.last_operation?.phase === 'queued' && item;
    })()`)
    await view(window, `!document.querySelector('.ws-host-progress') &&
      [...document.querySelectorAll('.ws-host-page code')].some(item => item.textContent === ${JSON.stringify(saved.last_operation.request.request_id)})`)
    const raw = await readFile(join(app.getPath('userData'), 'mnemion-host-logins', 'hosts.json'), 'utf8')
    if (raw.includes('PRIVATE KEY') || !JSON.parse(raw).profiles[0].sealed || JSON.stringify(saved).includes('sealed')) throw new Error('Native host key storage or public projection failed')
    return { phase: 'save', available: true, nativeAgentPipe: true, actualSetupControls: true,
      pinnedSSHAuthenticated: true, memoryAPIAbsent: true, protectedKeySaved: true, savedRequest: saved.last_operation.request,
      backupApprovalControls: true, backupSchemaAvailable: true, unapprovedBackupRequestRefused: true,
      profileId: saved.id, hostId: connection.host_id, actualQueuedRequestVisible: true, queuedServiceEffectsExecuted: false }
  }
  const original = config.host
  if (!original || typeof original.profileId !== 'string' || !original.savedRequest?.request_id ||
      initial.profiles.length !== 1 || initial.profiles[0].id !== original.profileId) throw new Error('The real app restart lost its independent host login')
  const inspected = await callNativeOperator('host.inspect', { id: original.profileId })
  if (!inspected.status.ok || inspected.status.result.host_id !== original.hostId || !inspected.operation?.ok ||
      inspected.operation.result.operation_id !== original.savedRequest.request_id || inspected.operation.result.phase !== 'queued') throw new Error('The installed host key did not reopen and inspect the original operation')
  const denied = await callNativeOperator('host.request', { id: original.profileId, request: {
    protocol: 1, host_id: original.hostId, request_id: crypto.randomUUID(), action: 'operators.list',
  } })
  if (denied.ok || denied.error?.code !== 'host_access_denied') throw new Error('A native operator accessed custodian-only controls')
  let refused = false
  try { await callNativeOperator('host.forget', { id: original.profileId, confirm: true }) } catch { refused = true }
  if (!refused) throw new Error('The native agent discarded an outstanding host request without approval')
  await view(window, "!document.querySelector('.ws-host-progress')")
  await window.webContents.executeJavaScript(`(() => {
    const details = [...document.querySelectorAll('.ws-host-page details')].find(item => item.querySelector('summary')?.textContent === 'Remove this login from this device');
    if (!details) throw new Error('Native host removal controls are missing');
    details.open = true;
    const boxes = [...details.querySelectorAll('input[type=checkbox]')];
    if (boxes.length !== 2) throw new Error('Native outstanding-request acknowledgement is missing');
    for (const box of boxes) if (!box.checked) box.click();
  })()`)
  await view(window, `(() => {
    const button = [...document.querySelectorAll('.ws-host-page button')].find(item => item.textContent.trim() === 'Remove saved login');
    if (!button || button.disabled) return false; button.click(); return true;
  })()`)
  await view(window, "(async () => (await window.mnemion.hostControl('host.profiles')).profiles.length === 0)()")
  const records = await callNativeOperator('host.recoveries')
  if (records.records.length !== 1) throw new Error('The installed client did not retain its recovery request')
  const recovery = await callNativeOperator('host.recovery', { id: records.records[0].id })
  if (JSON.stringify(recovery.profile.last_operation.request) !== JSON.stringify(original.savedRequest) ||
      JSON.stringify(recovery).includes('PRIVATE KEY') || JSON.stringify(recovery).includes('sealed')) throw new Error('The native public recovery document changed or exposed its private key')
  await view(window, `!document.querySelector('.ws-host-progress') &&
    [...document.querySelectorAll('.ws-host-page code')].some(item => item.textContent === ${JSON.stringify(original.savedRequest.request_id)}) &&
    [...document.querySelectorAll('.ws-host-page h2')].some(item => item.textContent === 'Retained recovery requests')`)
  return { phase: 'resume', available: true, nativeAgentPipe: true, actualSetupControls: true,
    pinnedSSHAuthenticated: true, memoryAPIAbsent: true, protectedKeyReopenedAfterAppRestart: true,
    originalRequestInspectedWithoutReplay: true, custodianBoundaryEnforced: true,
    removalRequiresOutstandingApproval: true, publicRecoveryRequestRetained: true, actualRecoveryRequestVisible: true, queuedServiceEffectsExecuted: false }
}
