/** Selected capture through real app controls, a stopped host and an app restart.
 * Only the outer installed-hosting gate's disposable profile invokes this.
 */
import { dialog, type BrowserWindow } from 'electron'
import { createHash, randomUUID } from 'node:crypto'
import { mkdir, readFile, rm, rmdir, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import type { DesktopSourceView } from '../shared/desktop-sources.js'
import { callNativeOperator as call } from './native-operator-probe.js'

const pause = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))
export async function until<T>(check: () => Promise<T | false>, message: string, timeout = 90000): Promise<T> {
  const end = Date.now() + timeout
  do { const value = await check(); if (value !== false) return value; await pause(200) } while (Date.now() < end)
  throw new Error(message)
}

const rendererHelpers = `
  const pause=ms=>new Promise(r=>setTimeout(r,ms));
  async function until(check,message,timeout=30000){const end=Date.now()+timeout;do{const value=await check();if(value)return value;await pause(100);}while(Date.now()<end);throw new Error(message);}
  const card=()=>[...document.querySelectorAll('section.ws-card')].find(e=>e.querySelector('h2')?.textContent==='Run on this computer');
  async function click(text){const node=await until(()=>[...card().querySelectorAll('button')].find(e=>e.textContent.trim()===text&&!e.disabled&&e.getClientRects().length),'Missing capture control: '+text);await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));if(!node.isConnected||node.disabled)throw new Error('Capture control changed before selection');node.click();await pause(100);}
  async function selectConnection(id){location.hash='/workspace/connections';await until(()=>{const field=[...document.querySelectorAll('select')].find(s=>[...s.options].some(o=>o.value===id));if(!field)return false;if(field.value!==id){Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(field,id);field.dispatchEvent(new Event('change',{bubbles:true}));return false;}return !!card();},'The capture connection did not appear');}
  async function request(method,path,body,expected=200){const session=(await window.mnemion.workspaceStatus()).active;if(!session?.me.administrator)throw new Error('Capture fixture requires its disposable workspace owner');const response=await window.mnemion.serviceRequest({url:session.endpoint+path,method,headers:{Authorization:'Bearer '+session.sessionToken,'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},...(body?{body:JSON.stringify(body)}:{})});if(response.status!==expected)throw new Error('Capture fixture request failed: '+path+' / '+response.status);return JSON.parse(new TextDecoder().decode(response.body));}
`

export async function inRenderer(window: BrowserWindow, source: string): Promise<any> {
  return window.webContents.executeJavaScript(`(async()=>{${rendererHelpers}\n${source}\n})()`)
}

export async function sourceStatus(id: string) {
  const view = await call('source.status') as DesktopSourceView
  const source = view.sources.find(item => item.id === id)
  if (!source) throw new Error('The installed capture source disappeared.')
  return { view, source }
}

export async function pauseSource(id: string) {
  const { view } = await sourceStatus(id)
  return call('source.pause', { id, expected_revision: view.revision, enabled: false })
}

export async function verifyNativeCapture(window: BrowserWindow, config: Record<string, unknown>, probePath: string): Promise<Record<string, unknown>> {
  const base = dirname(probePath), profile = process.env.MNEMION_STUDIO_USER_DATA!
  const fixturePath = join(base, 'native-capture-fixture.json')
  const sourcesPath = join(profile, 'mnemion-desktop-sources', 'sources.json')
  const selectWorkspace = async (action: string, input: Record<string, unknown>, workspace: string) => {
    const end = Date.now() + 30000
    for (;;) {
      await inRenderer(window, `await until(()=>window.mnemion.updateSafety(),'Finish app work before the capture host transition');`)
      try { return await call(action, input, workspace) } catch (error) {
        // A background read can start between the two guards. Only this
        // pre-mutation refusal may be retried; uncertain effects never are.
        if (!(error instanceof Error) || !error.message.endsWith('Save or discard edits and finish pending requests in the app before changing its workspace.') || Date.now() >= end) throw error
        await pause(100)
      }
    }
  }
  await until(async () => (await window.webContents.executeJavaScript('window.mnemion.localStatus()')).operator?.state === 'ready', 'The native capture operator did not start.')
  if (config.phase === 'capture-enroll') {
    await inRenderer(window, `await until(async()=>!!document.querySelector('.ws-workspace-name')&&window.mnemion.updateSafety()&&!!(await window.mnemion.workspaceStatus()).active?.me.administrator,'The disposable owner interface did not reopen',180000);`)
    const folder = join(base, 'Selected conversations Équipe ' + randomUUID())
    await mkdir(folder, { mode: 0o700 })
    const fixture = await inRenderer(window, `
      const session=(await window.mnemion.workspaceStatus()).active;
      const person=await request('POST','/v1/principals',{name:'Native retained capture',kind:'application',administrator:false},201);
      const connection=await request('POST','/v1/connectors',{name:'Native retained conversations',provider:'conversations',principal_id:person.id,access_mode:'published'},201);
      await request('PUT','/v1/connectors/'+connection.id+'/bindings',{external_id:'native-capture-owner',principal_id:session.me.principal_id,role:'reviewer'});
      return {endpoint:session.endpoint,tenantId:session.me.tenant_id,principalId:person.id,connectorId:connection.id};
    `)
    const originalDialog = dialog.showOpenDialog
    let selected = false
    dialog.showOpenDialog = (async () => {
      if (selected) throw new Error('Unexpected second capture folder selection.')
      selected = true
      return { canceled: false, filePaths: [folder] }
    }) as typeof dialog.showOpenDialog
    let configured
    try {
      configured = await inRenderer(window, `
        await selectConnection(${JSON.stringify(fixture.connectorId)});
        await click('Choose folder');
        const mode=card().querySelector('select');Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(mode,'messages');mode.dispatchEvent(new Event('change',{bubbles:true}));await pause(100);
        const fields=[...card().querySelectorAll('label')].find(e=>e.textContent.startsWith('Exclude JSON fields'))?.querySelector('textarea');
        if(!fields||fields.disabled)throw new Error('The app did not offer JSON field exclusions');
        fields.closest('details').open=true;Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(fields,'text');fields.dispatchEvent(new Event('input',{bubbles:true}));await pause(100);
        const keep=[...card().querySelectorAll('label')].find(e=>e.textContent.includes('Keep captured memories when original chat logs rotate or are removed'))?.querySelector('input');
        if(!keep||keep.disabled)throw new Error('The app did not offer explicit retained capture consent');keep.click();await pause(100);
        await click('Preview capture');
        await until(()=>!!card().querySelector('[data-capture-preview="ready"]'),'Capture choices were not previewed',30000);
        card().querySelector('input[type="checkbox"][required]').click();await pause(100);
        await click('Save and start scanning');
        return await until(async()=>{const view=await window.mnemion.sourceStatus();const item=view.sources.find(s=>s.connector_id===${JSON.stringify(fixture.connectorId)});const error=card()?.querySelector('[role="alert"]');if(error)throw new Error('Capture enrollment UI: '+error.textContent.slice(0,500));return item?.custody?item:false;},'The real app did not enroll its retained source',90000);
      `)
    } finally { dialog.showOpenDialog = originalDialog }
    if (!selected || configured.capture_mode !== 'messages' || configured.capture_policy?.preset !== 'conversation' || configured.capture_policy?.retention !== 'until_deleted' || configured.custody.keep_accepted !== true || !configured.members.includes('native-capture-owner')) throw new Error('The actual capture form lost its reviewed choices or mapped audience.')
    if (configured.capture_policy.format !== 'mnemion-capture-policy-v2' || JSON.stringify(configured.capture_policy.exclude_fields) !== '["text"]') throw new Error('Native field exclusions were not retained under the reviewed v2 policy.')
    await pauseSource(configured.id)
    const saved = JSON.parse(await readFile(sourcesPath, 'utf8')).sources.find((s: any) => s.id === configured.id)
    if (!saved?.sealed_inbox_key || saved.sealed_inbox_key === saved.sealed_key) throw new Error('The installed app did not seal a separate inbox key.')
    const state = await call('status')
    const workspace = state.info.settings.workspace_id
    await inRenderer(window, `location.hash='/workspace/memories';await until(()=>window.mnemion.updateSafety(),'Capture enrollment left unsaved work');`)
    await selectWorkspace('local.stop', {}, workspace)
    await until(async () => (await call('status')).state === 'stopped', 'The disposable host did not stop for offline capture.')
    const selectedText = 'Native offline capture ' + randomUUID()
    const excludedText = 'Excluded structured tool trace ' + randomUUID()
    const excludedFieldText = 'Excluded JSON text field ' + randomUUID()
    const selectedLog = join(folder, 'codex-session.jsonl')
    await writeFile(selectedLog, JSON.stringify({ type: 'session_meta', payload: { id: randomUUID() } }) + '\n' +
      JSON.stringify({ type: 'event_msg', payload: { type: 'user_message', message: selectedText } }) + '\n' +
      JSON.stringify({ type: 'response_item', payload: { type: 'message', role: 'assistant', content: [{ type: 'output_text', text: excludedFieldText }] } }) + '\n' +
      JSON.stringify({ type: 'response_item', payload: { type: 'function_call_output', call_id: 'synthetic', output: excludedText } }) + '\n', { mode: 0o600, flag: 'wx' })
    let current = await sourceStatus(configured.id)
    await call('source.pause', { id: configured.id, expected_revision: current.view.revision, enabled: true })
    const queued = await until(async () => {
      const { source } = await sourceStatus(configured.id)
      const capture = source.activity.report?.capture
      if (source.activity.phase === 'attention' && capture?.pending_events && capture.capture_complete && capture.reason_code === 'capture_delivery_unavailable') return source
      return false
    }, 'The stopped host did not leave accepted selected memories queued.')
    await pauseSource(configured.id)
    const inboxPath = join(profile, 'mnemion-desktop-sources', 'inbox-' + configured.id, 'inbox.sqlite3')
    const ciphertext = await readFile(inboxPath)
    if (ciphertext.includes(Buffer.from(selectedText)) || ciphertext.includes(Buffer.from(excludedText))) throw new Error('The native inbox contains unencrypted selected or excluded text.')
    current = await sourceStatus(configured.id)
    let refused = false
    try { await call('source.remove', { id: configured.id, expected_revision: current.view.revision, confirm: true, discard_local_inbox: true }) } catch { refused = true }
    if (!refused || !(await readFile(inboxPath)).equals(ciphertext)) throw new Error('Offline removal did not preserve the unconfirmed inbox.')
    const archivePath = join(base, 'Capture Équipe ' + randomUUID() + '.mnemion-capture')
    const originalSave = dialog.showSaveDialog
    let archiveSelected = false
    dialog.showSaveDialog = (async () => {
      if (archiveSelected) throw new Error('Unexpected second capture archive destination.')
      archiveSelected = true
      return { canceled: false, filePath: archivePath }
    }) as typeof dialog.showSaveDialog
    let recoveryKey: string
    try {
      recoveryKey = await inRenderer(window, `
        const overview=await until(()=>document.querySelector('.ws-local-sources'),'Offline source controls were not available');overview.open=true;
        const backup=await until(()=>[...overview.querySelectorAll('details')].find(e=>e.querySelector('summary')?.textContent==='Back up this capture inbox'),'The app did not offer inbox backup');backup.open=true;
        const press=async text=>{const button=await until(()=>[...backup.querySelectorAll('button')].find(e=>e.textContent.trim()===text&&!e.disabled),'Missing backup control: '+text);button.click();await pause(100);};
        await press('Choose where to save');
        await press('Generate recovery key');
        const key=await until(()=>{const v=backup.querySelector('input[type="text"]')?.value;return v?.length===50?v:false;},'A separate backup recovery key was not generated');
        backup.querySelector('input[type="checkbox"]').click();await pause(100);
        await press('Create encrypted backup');
        await until(()=>{const error=backup.querySelector('[role="alert"]');if(error)throw new Error('Capture backup UI: '+error.textContent.slice(0,500));return backup.querySelector('[data-capture-backup="verified"]');},'The real app did not verify its capture backup',90000);
        if(backup.querySelector('input[type="password"]')?.value||backup.hasAttribute('data-update-pending'))throw new Error('Capture backup retained its recovery key or unfinished form');
        return key;
      `)
    } finally { dialog.showSaveDialog = originalSave }
    const archive = await call('source.backup.inspect', { file: archivePath, recovery_key: recoveryKey })
    if (!archiveSelected || !archive.authenticated || archive.workspace_credentials_included || archive.source_enrolled ||
        archive.binding.source_id !== configured.custody.source_id || archive.binding.grant_id !== configured.custody.grant_id ||
        archive.status.pending_events !== queued.activity.report!.capture!.pending_events) throw new Error('The native capture archive lost its original identity or pending evidence.')
    if (archive.binding.capture_policy?.format !== 'mnemion-capture-policy-v2' || JSON.stringify(archive.binding.capture_policy.exclude_fields) !== '["text"]') throw new Error('The native archive lost its approved field exclusions.')
    const archiveBytes = await readFile(archivePath)
    if (archiveBytes.includes(Buffer.from(selectedText)) || archiveBytes.includes(Buffer.from(excludedText))) throw new Error('The portable capture archive contains plaintext conversation content.')
    const [width, height] = window.getContentSize()
    try {
      window.setContentSize(720, 1000)
      await inRenderer(window, `await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));const receipt=document.querySelector('[data-capture-backup="verified"]');receipt.scrollIntoView({block:'center'});if(document.documentElement.scrollWidth>innerWidth+1)throw new Error('Capture backup controls overflow the narrow app window');`)
      await writeFile(join(base, 'native-capture-backup.png'), (await window.webContents.capturePage()).toPNG(), { mode: 0o600, flag: 'wx' })
    } finally { window.setContentSize(width, height) }
    // Provider files are no longer available on the next app launch. Only the
    // OS-protected key and the accepted encrypted inbox can complete delivery.
    await rm(selectedLog)
    await rmdir(folder)
    const captured = { ...fixture, id: configured.id, grantId: configured.custody.grant_id,
      workspace, folder, selectedText, excludedText, excludedFieldText, pending: queued.activity.report!.capture!.pending_events,
      archivePath, recoveryKey, archiveSha256: archive.archive_sha256,
      sealedInboxSha256: createHash('sha256').update(saved.sealed_inbox_key).digest('hex') }
    await writeFile(fixturePath, JSON.stringify(captured), { mode: 0o600, flag: 'wx' })
    return { phase: config.phase, nativeCaptureConsentControls: true, nativeCaptureIndependentOsKey: true,
      nativeCaptureBeforeDelivery: true, nativeCaptureOfflineRemovalPreservesInbox: true,
      nativeCaptureSelectedPayloadEncrypted: true, nativeCapturePausedBeforeRestart: true,
      nativeCaptureFieldExclusionsReviewed: true, nativeCaptureFieldPolicyArchived: true,
      nativeCaptureBackupThroughApp: true, nativeCaptureBackupEncrypted: true,
      nativeCaptureBackupAppAndAgentAgree: true, nativeCaptureBackupNarrowLayout: true }
  }

  const fixture = JSON.parse(await readFile(fixturePath, 'utf8'))
  const recoveredPhase = config.phase === 'capture-restored-resume'
  const sourceId = recoveredPhase ? fixture.restoredId : fixture.id
  const saved = JSON.parse(await readFile(sourcesPath, 'utf8')).sources.find((s: any) => s.id === sourceId)
  if (saved?.capture_policy?.format !== 'mnemion-capture-policy-v2' || JSON.stringify(saved.capture_policy.exclude_fields) !== '["text"]') throw new Error('Capture restart or recovery changed its approved field exclusions.')
  const keySha = recoveredPhase ? fixture.restoredSealedInboxSha256 : fixture.sealedInboxSha256
  if (!saved || saved.enabled || createHash('sha256').update(saved.sealed_inbox_key).digest('hex') !== keySha) throw new Error('App restart changed the capture key or lost its paused configuration.')
  let current = await sourceStatus(sourceId)
  if (!recoveredPhase && (current.source.activity.durability !== 'saved' || current.source.activity.report?.capture?.pending_events !== fixture.pending)) throw new Error('The app did not restore its last saved offline queue observation.')
  if (recoveredPhase && (current.source.custody?.grant_id !== fixture.restoredGrantId || current.source.activity.phase !== 'paused')) throw new Error('The recovered device changed its grant or started without consent.')
  const checkArchive = async () => {
    const archive = await call('source.backup.inspect', { file: fixture.archivePath, recovery_key: fixture.recoveryKey })
    if (!archive.authenticated || archive.archive_sha256 !== fixture.archiveSha256 ||
        archive.binding.grant_id !== fixture.grantId || archive.status.pending_events !== fixture.pending ||
        archive.workspace_credentials_included || archive.source_enrolled) throw new Error('Portable capture backup inspection changed its identity or contents.')
  }
  await checkArchive()
  // local.stop intentionally disables host auto-start. Resume it explicitly,
  // retaining the same workspace and endpoint, before requesting delivery.
  if ((await call('status')).state !== 'running') await call('local.start', {}, fixture.workspace)
  await until(async () => (await call('status')).state === 'running', 'The original disposable host did not resume.', 180000)
  await inRenderer(window, `await until(()=>window.mnemion.updateSafety(),'The stopped workspace page retained unfinished work');`)
  await selectWorkspace('local.open', { expected_revision: (await call('workspace.status')).revision }, fixture.workspace)
  await inRenderer(window, `await until(async()=>{const s=(await window.mnemion.workspaceStatus()).active;return s?.endpoint===${JSON.stringify(fixture.endpoint)}&&s.me.tenant_id===${JSON.stringify(fixture.tenantId)};},'Host resume changed capture identity');`)
  await inRenderer(window, `await until(()=>!!document.querySelector('.ws-workspace-name')&&window.mnemion.updateSafety(),'The resumed workspace interface did not settle');`)
  if (recoveredPhase) {
    await writeFile(join(fixture.restoredFolder, 'recovered-session.jsonl'),
      JSON.stringify({ type: 'session_meta', payload: { id: randomUUID() } }) + '\n' +
      JSON.stringify({ type: 'event_msg', payload: { type: 'user_message', message: fixture.newText } }) + '\n' +
      JSON.stringify({ type: 'response_item', payload: { type: 'message', role: 'assistant', content: [{ type: 'output_text', text: fixture.excludedFieldText }] } }) + '\n', { mode: 0o600, flag: 'wx' })
  }
  current = await sourceStatus(sourceId)
  await call('source.pause', { id: sourceId, expected_revision: current.view.revision, enabled: true })
  const delivered = await until(async () => {
    const { source } = await sourceStatus(sourceId), report = source.activity.report?.capture
    return report?.delivery_complete && report.pending_events === 0 && report.stored_events === fixture.pending + (recoveredPhase ? 1 : 0) &&
      (recoveredPhase || report.reason_code === 'capture_source_unavailable') ? report : false
  }, 'The installed app did not deliver its encrypted queue after restart and producer removal.')
  const memory = await inRenderer(window, `
    const results=await request('POST','/v1/recall',{query:${JSON.stringify(fixture.selectedText)},all_accessible:true,mode:'lexical'});
    const matching=[];for(const hit of results.hits){const m=await request('GET','/v1/memories/'+hit.memory_id);if(m.content.includes(${JSON.stringify(fixture.selectedText)})){if(JSON.stringify(m).includes(${JSON.stringify(fixture.excludedText)}))throw new Error('Messages-only custody included the excluded tool trace');if(JSON.stringify(m).includes(${JSON.stringify(fixture.excludedFieldText)})||m.metadata.field_redaction!=='json_field_names')throw new Error('The shared workspace did not preserve approved field exclusions');matching.push(m.memory_id);}}
    if(matching.length!==1)throw new Error('Offline delivery did not produce exactly one selected memory');
    await selectConnection(${JSON.stringify(fixture.connectorId)});
    await until(()=>{const counts=card()?.querySelector('[aria-label="Retained capture status"]');return counts?.textContent.includes('acknowledged by the workspace')&&counts.textContent.includes('0 queued');},'The installed app did not display its retained queue counts');
    return matching[0];
  `)
  if (recoveredPhase) {
    if (memory !== fixture.memory) throw new Error('Recovery duplicated an already accepted source memory.')
    await inRenderer(window, `
      const result=await request('POST','/v1/recall',{query:${JSON.stringify(fixture.newText)},all_accessible:true,mode:'lexical'});
      let count=0;for(const hit of result.hits){const m=await request('GET','/v1/memories/'+hit.memory_id);if(m.content.includes(${JSON.stringify(fixture.newText)})){if(JSON.stringify(m).includes(${JSON.stringify(fixture.excludedFieldText)})||m.metadata.field_redaction!=='json_field_names')throw new Error('Recovered capture did not retain its field exclusions');count++;}}
      if(count!==1)throw new Error('The recovered source did not capture exactly one new memory');
    `)
  }
  await pauseSource(sourceId)
  await inRenderer(window, `
    const grant=await request('GET','/v1/capture-grants/'+${JSON.stringify(recoveredPhase ? fixture.restoredGrantId : fixture.grantId)});
    await request('DELETE','/v1/keys/'+grant.device_key_id);
    await click('Remove from this computer');
    await click('Revoke device grant and discard local inbox');
    await until(async()=>!(await window.mnemion.sourceStatus()).sources.some(s=>s.id===${JSON.stringify(sourceId)}),'The administrator could not remove capture after its device key was revoked',60000);
    const retired=await request('GET','/v1/capture-grants/'+${JSON.stringify(recoveredPhase ? fixture.restoredGrantId : fixture.grantId)});
    if(!retired.revoked_at||retired.active)throw new Error('The native removal did not revoke its exact device grant');
    if((await request('GET','/v1/memories/'+${JSON.stringify(memory)})).memory_id!==${JSON.stringify(memory)})throw new Error('Device removal deleted an already accepted server memory');
  `)
  if (JSON.parse(await readFile(sourcesPath, 'utf8')).sources.some((s: any) => s.id === sourceId)) throw new Error('Removed capture credentials remain in source settings.')
  await checkArchive()
  if (!recoveredPhase) {
    const restoredFolder = join(base, 'Recovered conversations Équipe ' + randomUUID())
    await mkdir(restoredFolder, { mode: 0o700 })
    const originalDialog = dialog.showOpenDialog
    let selections = 0
    dialog.showOpenDialog = (async () => {
      if (++selections > 2) throw new Error('Unexpected capture recovery file selection.')
      return { canceled: false, filePaths: [selections === 1 ? fixture.archivePath : restoredFolder] }
    }) as typeof dialog.showOpenDialog
    let restored
    try {
      restored = await inRenderer(window, `
        await selectConnection(${JSON.stringify(fixture.connectorId)});
        const form=await until(()=>card()?.querySelector('[data-capture-restore="form"]'),'The app did not offer archived capture recovery');form.open=true;
        const press=async text=>{const node=await until(()=>[...form.querySelectorAll('button')].find(e=>e.textContent.trim()===text&&!e.disabled),'Missing recovery control: '+text);node.click();await pause(100);};
        await press('Choose capture backup');
        const key=form.querySelector('input[type="password"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(key,${JSON.stringify(fixture.recoveryKey)});key.dispatchEvent(new Event('input',{bubbles:true}));await pause(100);
        await press('Verify recovery archive');
        await press('Choose this computer’s conversation folder');
        await press('Preview recovered source');
        await until(()=>form.querySelector('[data-capture-preview="ready"]'),'Recovered source choices were not previewed');
        form.querySelector('input[type="checkbox"]').click();await pause(100);
        await press('Recover as a paused source');
        const receipt=await until(()=>{const error=form.querySelector('[role="alert"]');if(error)throw new Error('Capture recovery UI: '+error.textContent.slice(0,500));return form.querySelector('[data-capture-restored="ready"]');},'The actual app did not recover its capture archive',90000);
        if(form.querySelector('input[type="password"]')?.value||form.hasAttribute('data-update-pending'))throw new Error('Completed recovery retained its key or unfinished form');
        const view=await window.mnemion.sourceStatus();return view.sources.find(s=>s.id===receipt.dataset.sourceId);
      `)
    } finally { dialog.showOpenDialog = originalDialog }
    if (selections !== 2 || !restored || restored.enabled || restored.id === fixture.id || restored.custody.source_id !== current.source.custody!.source_id ||
        restored.custody.grant_id === fixture.grantId || JSON.stringify(restored.capture_policy) !== JSON.stringify(current.source.capture_policy)) throw new Error('App recovery changed source policy or failed to install a separately authorized paused device.')
    const fresh = JSON.parse(await readFile(sourcesPath, 'utf8')).sources.find((s: any) => s.id === restored.id)
    if (!fresh?.sealed_inbox_key || fresh.sealed_inbox_key === fresh.sealed_key || fresh.sealed_inbox_key === saved.sealed_inbox_key || fresh.sealed_key === saved.sealed_key) throw new Error('The app reused retired device credentials or its old inbox key.')
    if ((await call('source.restore.list')).items.length) throw new Error('Completed app recovery left an unfinished recovery intent.')
    const [width, height] = window.getContentSize()
    try {
      window.setContentSize(720, 1000)
      await inRenderer(window, `await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));document.querySelector('[data-capture-restored="ready"]').scrollIntoView({block:'center'});if(document.documentElement.scrollWidth>innerWidth+1)throw new Error('Capture recovery overflows the narrow app window');`)
      await writeFile(join(base, 'native-capture-recovery.png'), (await window.webContents.capturePage()).toPNG(), { mode: 0o600, flag: 'wx' })
    } finally { window.setContentSize(width, height) }
    Object.assign(fixture, { memory, restoredFolder, restoredId: restored.id, restoredGrantId: restored.custody.grant_id,
      restoredSealedInboxSha256: createHash('sha256').update(fresh.sealed_inbox_key).digest('hex'), newText: 'Native recovered future memory ' + randomUUID() })
    await writeFile(fixturePath, JSON.stringify(fixture), { mode: 0o600 })
    return { phase: config.phase, nativeCaptureQueueSurvivesAppRestart: true, nativeCaptureKeyReopenedByOs: true,
      nativeCaptureFieldExclusionsDelivered: true,
      nativeCaptureDeliversAfterProducerRemoval: true, nativeCaptureVisibleAppCounts: true,
      nativeCaptureAdministratorRemovalAfterKeyRevocation: true, nativeCaptureRemovalRetainsServerMemory: true,
      nativeCaptureBackupSurvivesAppRestart: true, nativeCaptureBackupInspectAfterSourceRemoval: true,
      nativeCaptureRestoreThroughApp: true, nativeCaptureRestoreAppAndAgentAgree: true,
      nativeCaptureRestorePausedWithNewKeys: true, nativeCaptureRestoreNarrowLayout: true, acceptedEvents: delivered.stored_events }
  }
  await inRenderer(window, `
    await request('DELETE','/v1/connectors/'+${JSON.stringify(fixture.connectorId)});
    await request('POST','/v1/principals/'+${JSON.stringify(fixture.principalId)}+'/disable');
    location.hash='/workspace/memories';
  `)
  await rm(join(fixture.restoredFolder, 'recovered-session.jsonl'))
  await rmdir(fixture.restoredFolder)
  await rm(fixture.archivePath)
  await rm(fixturePath)
  return { phase: config.phase, nativeCaptureRestoredKeyReopenedByOs: true, nativeCaptureRestoredPausedAfterRestart: true,
    nativeCaptureFieldExclusionsSurviveRecovery: true,
    nativeCaptureRestoredQueueReconcilesWithoutDuplicates: true, nativeCaptureRestoredNewMemoriesCaptured: true,
    nativeCaptureFixtureCleanup: true, acceptedEvents: delivered.stored_events }
}
