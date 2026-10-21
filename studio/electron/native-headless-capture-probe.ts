/** Independent capture through the installed engine, without a desktop source. */
import { app, type BrowserWindow } from 'electron'
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { createHash, randomBytes, randomUUID } from 'node:crypto'
import { mkdir, readFile, rename, rm, stat, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { StringDecoder } from 'node:string_decoder'
import { callNativeOperator as call } from './native-operator-probe.js'
import { inRenderer, until } from './native-capture-probe.js'
import { NativeCaptureRelay } from './native-capture-relay.js'
import { isolatedPreviewDiagnostic } from './native-capture-diagnostics.js'

const digest = (value: Buffer) => createHash('sha256').update(value).digest('hex')
const row = (text: string) => [
  { type: 'session_meta', payload: { id: randomUUID() } },
  { type: 'event_msg', payload: { type: 'user_message', message: text } },
].map(value => JSON.stringify(value)).join('\n') + '\n'

function diagnosticLine(line: string): string | undefined {
  // A failed packaged process can emit a Python/native traceback before its
  // JSON protocol starts. Keep only code locations and exception/dependency
  // names; never include raw lines, exception messages, locals or private paths.
  const frame = /File "(?:.*[\\/])?(mnemion(?:[\\/][a-z_][a-z0-9_]*){1,5})\.py", line ([0-9]{1,7}), in ([A-Za-z_][A-Za-z0-9_]{0,63})/.exec(line)
  if (frame) return frame[1].replaceAll('\\', '.').replaceAll('/', '.') + ':' + frame[2] + ':' + frame[3]
  const missing = /^ModuleNotFoundError: No module named '([A-Za-z_][A-Za-z0-9_.]{0,127})'$/.exec(line)
  if (missing) return 'missing_module:' + missing[1]
  const kind = /^(?:[A-Za-z_][A-Za-z0-9_]{0,63}\.)?([A-Za-z_][A-Za-z0-9_]{0,63}(?:Error|Exception|Warning))(?::|$)/.exec(line)
  if (kind) return kind[1]
  if (line === 'Traceback (most recent call last):') return 'python_traceback'
  if (/^\[PYI-[0-9]+:/.test(line)) return 'packaged_python_runtime'
  return undefined
}

function launch(config: string, environment: NodeJS.ProcessEnv, options: string[], input?: Record<string, unknown>, isolatedPreview = false) {
  const executable = !app.isPackaged && process.env.MNEMION_LOCAL_ENGINE ? process.env.MNEMION_LOCAL_ENGINE :
    join(process.resourcesPath, 'engine', process.platform === 'win32' ? 'mnemion-engine.exe' : 'mnemion-engine')
  const child = spawn(executable, ['connect', '--config', config, ...options], {
    env: environment, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true,
  }) as ChildProcessWithoutNullStreams
  const reports: any[] = [], errors: any[] = []
  const diagnostics: string[] = []
  const operation = String(input?.action ?? options[0] ?? 'scan')
  let failure: Error | undefined, size = 0
  const pending = { out: '', error: '' }
  const decoders = { out: new StringDecoder('utf8'), error: new StringDecoder('utf8') }
  const receive = (kind: 'out' | 'error', line: string) => {
    if (!line.trim()) return
    try { (kind === 'out' ? reports : errors).push(JSON.parse(line)) } catch {
      failure ??= new Error('The installed connector emitted an unstructured diagnostic (' + operation + '; ' + kind + ').')
      const diagnostic = diagnosticLine(line.trim()) ?? (isolatedPreview ?
        'isolated_preview:' + isolatedPreviewDiagnostic(line, environment, [config, executable]) : undefined)
      if (diagnostic && !diagnostics.includes(diagnostic)) diagnostics.push(diagnostic)
      if (diagnostics.length > 8) diagnostics.shift()
      // Keep the bounded tail until exit. Unstructured output still fails.
    }
  }
  const collect = (kind: 'out' | 'error', buffer: Buffer) => {
    size += buffer.length
    if (size > 1024 * 1024) { failure = new Error('The native connector exceeded its bounded diagnostic output.'); child.kill(); return }
    pending[kind] += decoders[kind].write(buffer)
    while (pending[kind].includes('\n')) {
      const end = pending[kind].indexOf('\n'), line = pending[kind].slice(0, end).trim()
      pending[kind] = pending[kind].slice(end + 1)
      receive(kind, line)
    }
  }
  child.stdout.on('data', value => collect('out', value))
  child.stderr.on('data', value => collect('error', value))
  child.stdin.on('error', () => {})
  child.stdin.end(input ? JSON.stringify(input) : undefined)
  child.on('error', () => { failure = new Error('The installed independent connector could not start.') })
  const done = new Promise<number | null>(resolve => child.on('close', code => {
    for (const kind of ['out', 'error'] as const) receive(kind, pending[kind] + decoders[kind].end())
    resolve(code)
  }))
  const check = () => {
    if (!failure) return
    const last = errors.at(-1)?.error
    const errorCode = typeof last === 'string' && /^[a-z_]{1,80}$/.test(last) ? last : 'none'
    throw new Error(failure.message + ' exit=' + child.exitCode + ' signal=' + child.signalCode +
      ' json_stdout=' + reports.length + ' json_stderr=' + errors.length + ' error=' + errorCode +
      (diagnostics.length ? ' ' + diagnostics.join(', ') : ''))
  }
  const stop = async () => {
    if (child.exitCode === null && child.signalCode === null) child.kill()
    await Promise.race([done, new Promise<never>((_, reject) => {
      const timer = setTimeout(() => reject(new Error('The independent capture process did not stop.')), 10000)
      timer.unref()
    })])
    check()
  }
  return { child, reports, errors, done, check, stop }
}

async function command(file: string, env: NodeJS.ProcessEnv, options: string[], input?: Record<string, unknown>, expected = 0, isolatedPreview = false) {
  const running = launch(file, env, options, input, isolatedPreview)
  const timer = setTimeout(() => running.child.kill(), 120000)
  try {
    const code = await running.done
    running.check()
    if (code !== expected) throw new Error('Independent capture command failed: ' + (input?.action ?? (options.join(' ') || 'scan')) + ' / ' + code + ' / ' + (running.errors.at(-1)?.error ?? 'no structured error'))
    if (expected !== 0) return running.errors.at(-1) ?? running.reports.at(-1)
    const report = running.reports.at(-1)
    if (!report || input && report.ok !== true) throw new Error('The installed connector did not return its complete command receipt.')
    return input ? report.result : report
  } finally { clearTimeout(timer); await running.stop() }
}

export async function verifyNativeHeadlessPreview(probePath: string): Promise<Record<string, unknown>> {
  // Run before creating any workspace: this fixture has no source contents,
  // enrollment, working service credential, model or remote connection.
  const base = dirname(probePath), id = randomUUID()
  const folder = join(base, 'Empty preview Équipe ' + id)
  const config = join(base, 'preview-' + id + '.json')
  const environment = { ...Object.fromEntries(Object.entries(process.env).filter(([name]) => !name.startsWith('MNEMION_'))),
    MNEMION_CAPTURE_GATE_DEVICE: 'disposable-preview-' + randomUUID() }
  await mkdir(folder, { mode: 0o700 })
  try {
    await writeFile(config, JSON.stringify({ version: 1, service_url: 'http://127.0.0.1:1',
      service_token: { env: 'MNEMION_CAPTURE_GATE_DEVICE' }, connector_id: randomUUID(),
      provider: { type: 'conversations', path: folder, capture_mode: 'messages', scope_id: 'native-empty-preview',
        name: 'Empty preview', members: [], publish_to_mapped_members: true, state_directory: 'preview-state-' + id + '/provider-state' },
      capture: { id, tenant_id: randomUUID(), principal_id: randomUUID(), source_id: randomUUID(), grant_id: randomUUID(),
        keep_accepted: true, state_directory: 'preview-state-' + id, inbox_key: { file: 'unused-inbox-' + id + '.key' },
        pending_limit_mib: 32, history_limit_events: 3000, database_limit_mib: 128, memory_limit_mib: 256 },
    }), { mode: 0o600, flag: 'wx' })
    const preview = await command(config, environment, ['--capture-control'], { action: 'preview' }, 0, true)
    if (preview.content_saved || preview.records.selected !== 0 || preview.hidden_reasoning !== 'unavailable') {
      throw new Error('The isolated native preview saved content or claimed hidden data access.')
    }
    return { phase: 'capture-preview', nativeEmptyCapturePreview: true }
  } finally {
    await rm(config, { force: true })
    await rm(folder, { recursive: true, force: true })
    await rm(join(base, 'preview-state-' + id), { recursive: true, force: true })
  }
}

export async function verifyNativeHeadlessCapture(window: BrowserWindow, probePath: string): Promise<Record<string, unknown>> {
  await until(async () => (await window.webContents.executeJavaScript('window.mnemion.localStatus()')).operator?.state === 'ready', 'The headless fixture operator did not start.')
  await until(async () => (await call('status')).state === 'running', 'The headless fixture host did not finish normal startup.', 180000)
  await inRenderer(window, `await until(async()=>!!document.querySelector('.ws-workspace-name')&&window.mnemion.updateSafety()&&!!(await window.mnemion.workspaceStatus()).active?.me.administrator,'The headless fixture owner did not reopen',180000);`)
  const desktopIds = (await call('source.status')).sources.map((item: any) => item.id).sort()
  // The outer installer gate creates this parent with actual current-user
  // ownership on Windows. Let the engine create its private state itself;
  // elevated Node-created directories can otherwise have Administrators owner.
  const base = dirname(probePath), id = randomUUID(), grantId = randomUUID()
  const folderName = 'Independent conversations Équipe ' + id, stateName = 'independent-state-' + id
  const folder = join(base, folderName), configFile = join(base, 'independent-source-' + id + '.json'), keyFile = join(base, stateName, 'inbox.key')
  const recoveryFile = join(base, stateName, 'recovery.key'), archiveFile = join(base, 'independent-' + id + '.mnemion-capture')
  await mkdir(folder, { mode: 0o700 })
  const policy = { format: 'mnemion-capture-policy-v1', preset: 'conversation', capture_mode: 'messages',
    include: ['*.jsonl'], exclude: [], retention: 'until_deleted', max_file_bytes: 1000000000, max_record_bytes: 2000000 }
  const fixture = await inRenderer(window, `
    const session=(await window.mnemion.workspaceStatus()).active;
    const application=await request('POST','/v1/principals',{name:'Native independent capture',kind:'application',administrator:false},201);
    const key=await request('POST','/v1/principals/'+application.id+'/keys',{name:'Disposable independent device'},201);
    const ownerKey=await request('POST','/v1/principals/'+session.me.principal_id+'/keys',{name:'Disposable headless recovery owner'},201);
    const connector=await request('POST','/v1/connectors',{name:'Native headless conversations',provider:'conversations',principal_id:application.id,access_mode:'published'},201);
    await request('PUT','/v1/connectors/'+connector.id+'/bindings',{external_id:'headless-owner',principal_id:session.me.principal_id,role:'reviewer'});
    await request('PUT','/v1/connectors/'+connector.id+'/capture-sources/'+${JSON.stringify(id)},
      {namespace:'native-headless',name:'Independent capture',members:['headless-owner'],capture_mode:'messages',keep_accepted:true,capture_policy:${JSON.stringify(policy)}});
    await request('PUT','/v1/capture-sources/'+${JSON.stringify(id)}+'/grants/'+${JSON.stringify(grantId)},{device_key_id:key.id});
    return {endpoint:session.endpoint,tenantId:session.me.tenant_id,principalId:application.id,connectorId:connector.id,keyId:key.id,credential:key.api_key,ownerKeyId:ownerKey.id,ownerCredential:ownerKey.api_key};
  `)
  const relay = new NativeCaptureRelay(fixture.endpoint)
  const endpoint = await relay.start()
  relay.capture(grantId, 'pass')
  const environment = { ...Object.fromEntries(Object.entries(process.env).filter(([name]) => !name.startsWith('MNEMION_'))),
    MNEMION_CAPTURE_GATE_DEVICE: fixture.credential, MNEMION_CAPTURE_GATE_ADMIN: fixture.ownerCredential }
  let watcher: ReturnType<typeof launch> | undefined
  const control = (input: Record<string, unknown>, expected = 0, file = configFile, env = environment) => command(file, env, ['--capture-control'], input, expected)
  const status = (file = configFile, env = environment) => control({ action: 'status' }, 0, file, env)
  const configuration = { version: 1, service_url: endpoint, service_token: { env: 'MNEMION_CAPTURE_GATE_DEVICE' }, connector_id: fixture.connectorId,
    provider: { type: 'conversations', path: folderName, state_directory: stateName + '/provider-state', scope_id: 'native-headless', name: 'Independent capture',
      members: ['headless-owner'], publish_to_mapped_members: true, capture_mode: 'messages', capture_policy: policy },
    capture: { id, tenant_id: fixture.tenantId, principal_id: fixture.principalId, source_id: id, grant_id: grantId, keep_accepted: true,
      state_directory: stateName, inbox_key: { file: stateName + '/inbox.key' }, pending_limit_mib: 32, history_limit_events: 3000, database_limit_mib: 128, memory_limit_mib: 256 },
    poll_seconds: 30, trigger_poll_seconds: 1 }
  try {
    await writeFile(configFile, JSON.stringify(configuration), { mode: 0o600, flag: 'wx' })
    const preview = await control({ action: 'preview' })
    if (preview.content_saved || preview.records.selected !== 0 || preview.hidden_reasoning !== 'unavailable') throw new Error('The standalone preview saved content or claimed hidden data access.')
    const generated = await control({ action: 'key', confirm: true })
    if (!generated.created || generated.key_printed) throw new Error('The native headless key generator did not keep its output private.')
    const enrolled = await control({ action: 'enroll', expected_revision: 'not-enrolled', preview_hash: preview.configuration_hash, confirm: true })
    if (enrolled.enabled || enrolled.state !== 'ready' || !enrolled.inbox_present) throw new Error('The independent runner did not enroll a paused inbox.')
    await control({ action: 'resume', expected_revision: enrolled.revision, confirm: true })
    const originalKey = await readFile(keyFile), selectedText = 'Independent offline selected memory ' + randomUUID()
    await writeFile(join(folder, 'session.jsonl'), row(selectedText), { mode: 0o600, flag: 'wx' })
    relay.capture(grantId, 'offline')
    for (let launchNumber = 0; launchNumber < 2; launchNumber++) {
      watcher = launch(configFile, environment, ['--watch'])
      await until(async () => {
        watcher!.check(); relay.check()
        if (watcher!.child.exitCode !== null || watcher!.child.signalCode !== null) throw new Error('The independent watcher exited before retaining its offline queue.')
        return watcher!.reports.some(value => value.capture?.pending_events === 1 && value.capture.reason_code === 'capture_delivery_unavailable')
      }, 'The installed independent watcher did not capture offline or reopen its durable queue.', 120000)
      await watcher.stop(); watcher = undefined
      const observed = await status()
      if (observed.activity?.report?.capture?.pending_events !== 1 || !observed.inbox_present || !observed.enabled) throw new Error('Stopping the independent process lost its accepted queue or run setting.')
      if (launchNumber === 0) await rm(join(folder, 'session.jsonl'))
    }
    const paused = await control({ action: 'pause', expected_revision: (await status()).revision })
    if (paused.enabled) throw new Error('The independent source did not pause while delivery was unavailable.')
    await control({ action: 'key', key_purpose: 'recovery', recovery_key: { file: recoveryFile }, confirm: true })
    const archive = await control({ action: 'backup', expected_revision: paused.revision, archive: archiveFile, recovery_key: { file: recoveryFile }, confirm: true })
    const inspected = await control({ action: 'inspect', archive: archiveFile, recovery_key: { file: recoveryFile } })
    if (!inspected.authenticated || inspected.archive_sha256 !== archive.archive_sha256 || inspected.status.pending_events !== 1 ||
        inspected.workspace_credentials_included || inspected.source_enrolled) throw new Error('Independent backup inspection lost pending evidence or included a credential.')
    const inbox = join(base, stateName, 'inbox-' + id, 'inbox.sqlite3')
    const originalDatabase = await readFile(inbox)
    if (originalDatabase.includes(Buffer.from(selectedText)) || (await readFile(archiveFile)).includes(Buffer.from(selectedText))) throw new Error('Independent selected content was not encrypted on disk.')
    await writeFile(keyFile, randomBytes(32).toString('base64') + '\n')
    try {
      const rejected = await control({ action: 'resume', expected_revision: paused.revision, confirm: true }, 2)
      if (rejected.error !== 'capture_key_unavailable' || !(await readFile(inbox)).equals(originalDatabase)) throw new Error('A changed independent key recreated or changed its accepted inbox.')
    } finally { await writeFile(keyFile, originalKey) }
    relay.capture(grantId, 'pass')
    await control({ action: 'resume', expected_revision: paused.revision, confirm: true })
    const delivered = await command(configFile, environment, [])
    if (delivered.capture?.pending_events !== 0 || delivered.capture.stored_events !== 1 || relay.pages.length !== 1) throw new Error('The restarted independent source did not deliver its retained memory exactly once.')
    const memory = relay.pages[0].receipt.items[0].memory_id
    await inRenderer(window, `const value=await request('GET','/v1/memories/'+${JSON.stringify(memory)});if(value.version!==1||!value.content.includes(${JSON.stringify(selectedText)}))throw new Error('Independent delivery changed its original selected memory');`)
    const afterDelivery = await control({ action: 'pause', expected_revision: (await status()).revision })
    const heldPath = inbox + '.held', heldDigest = digest(await readFile(inbox))
    await rename(inbox, heldPath)
    try {
      const rejected = await control({ action: 'resume', expected_revision: afterDelivery.revision, confirm: true }, 2)
      if (rejected.error !== 'capture_inbox_missing' || digest(await readFile(heldPath)) !== heldDigest || await stat(inbox).then(() => true, () => false)) throw new Error('A missing initialized inbox was silently recreated or replaced.')
    } finally { await rename(heldPath, inbox) }
    await inRenderer(window, `await request('DELETE','/v1/memories/'+${JSON.stringify(memory)}+'?expected_version=1',null,202);`)
    const freshGrant = randomUUID(), freshId = randomUUID(), freshFile = join(base, 'recovered-source-' + id + '.json')
    const fresh = await inRenderer(window, `
      const key=await request('POST','/v1/principals/'+${JSON.stringify(fixture.principalId)}+'/keys',{name:'Disposable recovered headless device'},201);
      await request('PUT','/v1/capture-sources/'+${JSON.stringify(id)}+'/grants/'+${JSON.stringify(freshGrant)},
        {device_key_id:key.id,previous_grant_id:${JSON.stringify(grantId)},confirm_previous_policy:true});return key;
    `)
    const freshEnvironment = { ...environment, MNEMION_CAPTURE_GATE_DEVICE: fresh.api_key }
    await writeFile(freshFile, JSON.stringify({ ...configuration, capture: { ...configuration.capture, id: freshId, grant_id: freshGrant, inbox_key: { file: stateName + '/recovered-inbox.key' } } }), { mode: 0o600, flag: 'wx' })
    await control({ action: 'key', confirm: true }, 0, freshFile, freshEnvironment)
    const freshPreview = await control({ action: 'preview' }, 0, freshFile, freshEnvironment)
    const recovered = await control({ action: 'restore', expected_revision: 'not-enrolled', preview_hash: freshPreview.configuration_hash, confirm: true,
      archive: archiveFile, archive_sha256: inspected.archive_sha256, recovery_key: { file: recoveryFile }, retirement_token: { env: 'MNEMION_CAPTURE_GATE_ADMIN' } }, 0, freshFile, freshEnvironment)
    if (recovered.enabled || recovered.state !== 'ready' || !recovered.inbox_present || (await readFile(join(base, stateName, 'recovered-inbox.key'))).equals(originalKey)) throw new Error('Independent recovery lost its pause or reused the retired inbox key.')
    relay.capture(freshGrant, 'pass')
    await control({ action: 'resume', expected_revision: recovered.revision, confirm: true }, 0, freshFile, freshEnvironment)
    const writesBefore = relay.pages.length
    const reconciled = await command(freshFile, freshEnvironment, [])
    if (reconciled.capture?.pending_events !== 0 || reconciled.capture.forgotten_events !== 1 || reconciled.capture.stored_events !== 0 || relay.pages.length !== writesBefore) throw new Error('Independent archive recovery resurrected a later-forgotten memory.')
    const futureText = 'New independently recovered memory ' + randomUUID()
    await writeFile(join(folder, 'recovered-session.jsonl'), row(futureText), { mode: 0o600, flag: 'wx' })
    const future = await command(freshFile, freshEnvironment, [])
    if (future.capture?.pending_events !== 0 || future.capture.stored_events !== 1 || future.capture.forgotten_events !== 1) throw new Error('The recovered independent runner did not capture a new memory.')
    await inRenderer(window, `
      await request('GET','/v1/memories/'+${JSON.stringify(memory)},null,404);
      const results=await request('POST','/v1/recall',{query:${JSON.stringify(futureText)},all_accessible:true,mode:'lexical'});
      if(results.hits.length!==1)throw new Error('Independent recovery duplicated or omitted its new memory');
    `)
    const retired = await control({ action: 'retire', expected_revision: (await status(freshFile, freshEnvironment)).revision, retirement_token: { env: 'MNEMION_CAPTURE_GATE_ADMIN' }, confirm: true }, 0, freshFile, freshEnvironment)
    if (retired.state !== 'retired' || retired.enabled) throw new Error('The native independent device did not confirm retirement.')
    await inRenderer(window, `
      for(const id of ${JSON.stringify([grantId, freshGrant])}){const grant=await request('GET','/v1/capture-grants/'+id);if(grant.active||!grant.revoked_at)throw new Error('Headless recovery left a retired grant active');}
      await request('DELETE','/v1/keys/'+${JSON.stringify(fixture.keyId)});await request('DELETE','/v1/keys/'+${JSON.stringify(fresh.id)});
      await request('DELETE','/v1/connectors/'+${JSON.stringify(fixture.connectorId)});
      await request('POST','/v1/principals/'+${JSON.stringify(fixture.principalId)}+'/disable');
    `)
    if (JSON.stringify((await call('source.status')).sources.map((item: any) => item.id).sort()) !== JSON.stringify(desktopIds)) throw new Error('The headless runner enrolled itself as a desktop-managed source.')
    relay.check()
    await rm(folder, { recursive: true }); await rm(join(base, stateName), { recursive: true })
    await rm(configFile); await rm(freshFile); await rm(archiveFile)
    return { phase: 'capture-headless', nativeHeadlessEngineEntry: true, nativeHeadlessConsentAndKeyGeneration: true,
      nativeHeadlessOfflineWatchRestart: true, nativeHeadlessPauseWithoutConnection: true,
      nativeHeadlessEncryptedBackupAndInspection: true, nativeHeadlessChangedKeyPreservesInbox: true,
      nativeHeadlessMissingInboxRefusesReset: true, nativeHeadlessDeliveryAfterProducerRemoval: true,
      nativeHeadlessNewDeviceRecovery: true, nativeHeadlessRecoveryHonorsLaterForgetting: true,
      nativeHeadlessFutureCaptureAndRetirement: true, nativeHeadlessIndependentOfDesktopSources: true,
      nativeHeadlessFixtureCleanup: true }
  } finally {
    try { if (watcher) await watcher.stop() } finally {
      try { await inRenderer(window, `await request('DELETE','/v1/keys/'+${JSON.stringify(fixture.ownerKeyId)});`) } finally { await relay.close() }
    }
  }
}
