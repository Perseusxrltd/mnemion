/** Reviewed policy migration through the installed app and its private operator.
 * Uses only the outer hosting gate's disposable workspace/profile and loopback relay.
 */
import { dialog, type BrowserWindow } from 'electron'
import { createHash, randomUUID } from 'node:crypto'
import { appendFile, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import type { CapturePolicy, DesktopSource, DesktopSourceView } from '../shared/desktop-sources.js'
import { callNativeOperator as call } from './native-operator-probe.js'
import { inRenderer, pauseSource, sourceStatus, until } from './native-capture-probe.js'
import { NativeCaptureRelay } from './native-capture-relay.js'
import { workspaceCipher } from './service-bridge.js'

const hash = (value: string | Buffer) => createHash('sha256').update(value).digest('hex')
const line = (value: unknown) => JSON.stringify(value) + '\n'
const message = (text: string) => line({ type: 'event_msg', payload: { type: 'user_message', message: text } })
const metadata = () => line({ type: 'session_meta', payload: { id: randomUUID() } })

async function transition(window: BrowserWindow, action: string, input: Record<string, unknown>, workspace?: string) {
  const deadline = Date.now() + 30000
  for (;;) {
    await inRenderer(window, `await until(()=>window.mnemion.updateSafety(),'Finish app work before selecting the policy fixture workspace');`)
    try { return await call(action, input, workspace) } catch (error) {
      // Only the existing pre-mutation refusal can be retried. Lost replies are not.
      if (!(error instanceof Error) || !error.message.endsWith('Save or discard edits and finish pending requests in the app before changing its workspace.') || Date.now() >= deadline) throw error
      await new Promise(resolve => setTimeout(resolve, 100))
    }
  }
}

export async function verifyNativeCapturePolicy(window: BrowserWindow, probePath: string): Promise<Record<string, unknown>> {
  const base = dirname(probePath), profile = process.env.MNEMION_STUDIO_USER_DATA!
  const settings = join(profile, 'mnemion-desktop-sources', 'sources.json')
  const readSaved = async (id: string) => JSON.parse(await readFile(settings, 'utf8')).sources.find((item: any) => item.id === id)
  await until(async () => (await window.webContents.executeJavaScript('window.mnemion.localStatus()')).operator?.state === 'ready', 'The capture policy operator did not start.')
  const local = await until(async () => {
    const state = await call('status')
    if (state.state === 'error') throw new Error('The disposable policy host could not start: ' + state.errorCode)
    return state.state === 'running' ? state : false
  }, 'The capture policy host did not finish startup.', 180000)
  if (!await workspaceCipher().available()) throw new Error('The policy journey requires its real OS credential store.')
  await inRenderer(window, `await until(async()=>!!document.querySelector('.ws-workspace-name')&&window.mnemion.updateSafety()&&!!(await window.mnemion.workspaceStatus()).active?.me.administrator,'The policy fixture owner did not reopen',180000);`)
  const owner = await inRenderer(window, `return (await window.mnemion.workspaceStatus()).active;`)
  const relay = new NativeCaptureRelay(owner.endpoint)
  const endpoint = await relay.start()
  let relayKey: { id: string; api_key: string } | undefined
  try {
    relayKey = await inRenderer(window, `return request('POST','/v1/principals/'+${JSON.stringify(owner.me.principal_id)}+'/keys',{name:'Disposable policy relay'},201);`)
    await transition(window, 'workspace.connect', { endpoint, credential: relayKey!.api_key, remember: false,
      expected_revision: (await call('workspace.status')).revision, expected_tenant_id: owner.me.tenant_id, expected_principal_id: owner.me.principal_id })
    await inRenderer(window, `await until(async()=>{const s=(await window.mnemion.workspaceStatus()).active;return s?.endpoint===${JSON.stringify(endpoint)}&&!!document.querySelector('.ws-workspace-name')&&window.mnemion.updateSafety();},'The policy fixture did not select its private relay');`)
    const id = randomUUID(), grantId = randomUUID()
    const folder = join(base, 'Reviewed policy Équipe ' + randomUUID())
    await mkdir(folder, { mode: 0o700 })
    const policy: CapturePolicy = { format: 'mnemion-capture-policy-v1', preset: 'conversation', capture_mode: 'messages',
      include: ['*.jsonl'], exclude: [], retention: 'until_deleted', max_file_bytes: 1000000000, max_record_bytes: 2000000 }
    const fixture = await inRenderer(window, `
      const application=await request('POST','/v1/principals',{name:'Native policy capture',kind:'application',administrator:false},201);
      const device=await request('POST','/v1/principals/'+application.id+'/keys',{name:'Disposable original policy device'},201);
      const connection=await request('POST','/v1/connectors',{name:'Native policy conversations',provider:'conversations',principal_id:application.id,access_mode:'published'},201);
      await request('PUT','/v1/connectors/'+connection.id+'/bindings',{external_id:'policy-owner',principal_id:${JSON.stringify(owner.me.principal_id)},role:'reviewer'});
      const source=await request('PUT','/v1/connectors/'+connection.id+'/capture-sources/'+${JSON.stringify(id)},
        {namespace:'native-policy',name:'Native policy conversations',members:['policy-owner'],capture_mode:'messages',keep_accepted:true,capture_policy:${JSON.stringify(policy)}});
      await request('PUT','/v1/capture-sources/'+source.source_id+'/grants/'+${JSON.stringify(grantId)},{device_key_id:device.id});
      return {principalId:application.id,connectorId:connection.id,spaceId:source.space_id,credential:device.api_key};
    `)
    const limits = { memory_limit_mib: 384, max_files: 100, pending_limit_mib: 32, history_limit_events: 3000, database_limit_mib: 192 }
    const preview = await call('source.preview', { selection: { path: folder, capture_mode: 'messages', capture_policy: policy, keep_accepted: true, ...limits } })
    const source: DesktopSource = { id, endpoint, tenant_id: owner.me.tenant_id, connector_id: fixture.connectorId,
      principal_id: fixture.principalId, name: 'Native policy conversations', provider: 'conversations', path: folder,
      scope_id: 'native-policy', members: ['policy-owner'], capture_mode: 'messages', capture_policy: policy,
      custody: { source_id: id, grant_id: grantId, keep_accepted: true, pending_limit_mib: limits.pending_limit_mib,
        history_limit_events: limits.history_limit_events, database_limit_mib: limits.database_limit_mib },
      publish_to_mapped_members: true, poll_seconds: 300, memory_limit_mib: limits.memory_limit_mib, max_files: limits.max_files, enabled: false }
    await call('source.configure', { expected_revision: (await call('source.status')).revision, source,
      credential: fixture.credential, preview_hash: preview.configuration_hash })
    const saved = await readSaved(id)
    const keptText = 'Kept native policy evidence ' + randomUUID(), forgottenText = 'Forgotten native policy evidence ' + randomUUID()
    const laterText = 'Must wait for reviewed native policy ' + randomUUID(), toolText = 'Newly selected native tool event ' + randomUUID()
    const keptFile = join(folder, 'kept.jsonl'), forgottenFile = join(folder, 'forgotten.jsonl')
    await writeFile(keptFile, metadata() + message(keptText) + line({ type: 'response_item', payload: { type: 'function_call_output', call_id: 'synthetic', output: toolText } }), { mode: 0o600, flag: 'wx' })
    await writeFile(forgottenFile, metadata() + message(forgottenText), { mode: 0o600, flag: 'wx' })
    relay.capture(grantId, 'offline')
    await call('source.pause', { id, expected_revision: (await call('source.status')).revision, enabled: true })
    await until(async () => {
      relay.check()
      const { source } = await sourceStatus(id), report = source.activity.report?.capture
      return source.activity.phase !== 'scanning' && report?.pending_events === 2 && report.reason_code === 'capture_delivery_unavailable' ? report : false
    }, 'The policy fixture did not retain its original offline queue.')
    await pauseSource(id)
    await appendFile(keptFile, message(laterText))
    relay.capture(grantId, 'pass')
    await inRenderer(window, `
      await selectConnection(${JSON.stringify(fixture.connectorId)});
      const backup=await until(()=>[...card().querySelectorAll('details')].find(e=>e.querySelector('summary')?.textContent==='Back up this capture inbox'),'The paused policy source has no inline backup controls');backup.open=true;
      const button=await until(()=>[...backup.querySelectorAll('button')].find(e=>e.textContent==='Deliver saved queue'&&!e.disabled),'The app did not offer paused queue delivery');button.click();
      await until(()=>{const error=backup.querySelector('[role="alert"]');if(error)throw new Error('Paused delivery UI: '+error.textContent.slice(0,500));return backup.querySelector('[data-capture-drained="complete"]');},'The app did not confirm its paused queue delivery',90000);
    `)
    const settled = await call('source.drain', { id, expected_revision: (await call('source.status')).revision, confirm: true })
    if (!settled.delivery_complete || settled.source_enabled || settled.remote_committed_events !== 0 || settled.status.stored_events !== 2 || settled.status.pending_events) throw new Error('Paused app delivery read new records or disagreed with the native agent.')
    await inRenderer(window, `
      const matches=async text=>{const results=await request('POST','/v1/recall',{query:text,all_accessible:true,mode:'lexical'});const found=[];for(const hit of results.hits){const m=await request('GET','/v1/memories/'+hit.memory_id);if(m.content.includes(text))found.push(m);}return found;};
      if((await matches(${JSON.stringify(laterText)})).length||(await matches(${JSON.stringify(toolText)})).length)throw new Error('Paused delivery accepted new or excluded producer content');
      const forgotten=await matches(${JSON.stringify(forgottenText)});if(forgotten.length!==1)throw new Error('The policy fixture lacks its single deletion witness');
      await request('DELETE','/v1/memories/'+forgotten[0].memory_id+'?expected_version='+forgotten[0].version,null,202);
    `)
    const forgotten = await call('source.drain', { id, expected_revision: (await call('source.status')).revision, confirm: true })
    if (!forgotten.delivery_complete || forgotten.status.forgotten_events !== 1) throw new Error('The paused inbox did not reconcile its later deletion before policy review.')
    await inRenderer(window, `
      const admin=await until(()=>document.querySelector('[data-capture-policy-source="'+${JSON.stringify(id)}+'"]'),'The app did not expose this source to its workspace administrator');
      const form=await until(()=>admin.querySelector('form'),'The source has no policy review form');form.closest('details').open=true;
      const preset=[...form.querySelectorAll('label')].find(e=>e.textContent.startsWith('Capture preset'))?.querySelector('select');
      if(!preset||preset.disabled)throw new Error('The policy preset is unavailable');Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(preset,'detailed');preset.dispatchEvent(new Event('change',{bubbles:true}));await pause(100);
      const retention=[...form.querySelectorAll('label')].find(e=>e.textContent.startsWith('Server retention'))?.querySelector('select');
      if(!retention||retention.disabled)throw new Error('Scheduled capture expiry is unavailable');Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(retention,'expire_after');retention.dispatchEvent(new Event('change',{bubbles:true}));await pause(100);
      const days=[...form.querySelectorAll('label')].find(e=>e.textContent.startsWith('Days after first server acceptance'))?.querySelector('input');
      if(!days)throw new Error('The expiry period cannot be reviewed');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(days,'7');days.dispatchEvent(new Event('input',{bubbles:true}));await pause(100);
      const fields=[...form.querySelectorAll('label')].find(e=>e.textContent.startsWith('Exclude JSON fields'))?.querySelector('textarea');
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(fields,'test_secret');fields.dispatchEvent(new Event('input',{bubbles:true}));await pause(100);
      const press=async text=>{const b=await until(()=>[...admin.querySelectorAll('button')].find(e=>e.textContent===text&&!e.disabled),'Missing policy review control: '+text);b.click();await pause(100);};
      await press('Review policy change');
      const review=await until(()=>admin.querySelector('[data-capture-policy-review="ready"]'),'The app did not show the current policy and affected grants');
      if(!review.textContent.includes('7 days')||!review.textContent.includes('earlier copies'))throw new Error('The expiry review omitted its period or earlier fragment copies');
      review.querySelector('input[type="checkbox"]').click();await pause(100);
      await press('Approve policy change');
      await until(()=>{const error=admin.querySelector('[role="alert"]');if(error)throw new Error('Policy review UI: '+error.textContent.slice(0,500));return admin.querySelector('[role="status"]')?.textContent.includes('Policy 2 approved');},'The workspace did not approve its reviewed policy');
      const old=await request('GET','/v1/capture-grants/'+${JSON.stringify(grantId)});if(!old.active||old.policy_version!==1)throw new Error('Approving a new default silently changed or retired the original device policy');
    `)
    const archivePath = join(base, 'Reviewed policy ' + randomUUID() + '.mnemion-capture')
    const originalSave = dialog.showSaveDialog
    let saves = 0
    dialog.showSaveDialog = (async () => {
      if (++saves !== 1) throw new Error('Unexpected second policy backup destination.')
      return { canceled: false, filePath: archivePath }
    }) as typeof dialog.showSaveDialog
    let recoveryKey: string
    try {
      recoveryKey = await inRenderer(window, `
        const backup=[...card().querySelectorAll('details')].find(e=>e.querySelector('summary')?.textContent==='Back up this capture inbox');backup.open=true;
        const press=async text=>{const b=await until(()=>[...backup.querySelectorAll('button')].find(e=>e.textContent===text&&!e.disabled),'Missing policy backup control: '+text);b.click();await pause(100);};
        await press('Choose where to save');await press('Generate recovery key');
        const key=await until(()=>{const value=backup.querySelector('input[type="text"]')?.value;return value?.length===50?value:false;},'The policy archive lacks a separate recovery key');
        backup.querySelector('input[type="checkbox"]').click();await pause(100);await press('Create encrypted backup');
        await until(()=>{const error=backup.querySelector('[role="alert"]');if(error)throw new Error('Policy backup UI: '+error.textContent.slice(0,500));return backup.querySelector('[data-capture-backup="verified"]');},'The policy archive was not verified',90000);
        return key;
      `)
    } finally { dialog.showSaveDialog = originalSave }
    const archive = await call('source.backup.inspect', { file: archivePath, recovery_key: recoveryKey })
    if (saves !== 1 || !archive.authenticated || archive.binding.grant_id !== grantId || archive.status.pending_events || archive.status.unknown_pages || archive.status.forgotten_events !== 1) throw new Error('The current policy backup lost its settled queue or deletion witness.')
    const originalDatabase = join(profile, 'mnemion-desktop-sources', 'inbox-' + id, 'inbox.sqlite3')
    const originalHash = hash(await readFile(originalDatabase))
    const originalOpen = dialog.showOpenDialog
    let opens = 0
    dialog.showOpenDialog = (async () => {
      if (++opens > 2) throw new Error('Policy migration must keep the original producer folder and recovery archive.')
      return { canceled: false, filePaths: [archivePath] }
    }) as typeof dialog.showOpenDialog
    let replacement: DesktopSource
    relay.interruptRetirement(grantId)
    try {
      replacement = await inRenderer(window, `
        const form=await until(()=>card().querySelector('[data-capture-restore="form"]'),'The app did not offer reviewed policy adoption');form.open=true;
        if(form.querySelector('summary').textContent!=='Apply the workspace’s current capture policy')throw new Error('The existing source has no policy migration control');
        const press=async text=>{const b=await until(()=>[...form.querySelectorAll('button')].find(e=>e.textContent===text&&!e.disabled),'Missing policy migration control: '+text);b.click();await pause(100);};
        await press('Choose capture backup');
        const key=form.querySelector('input[type="password"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(key,${JSON.stringify(recoveryKey)});key.dispatchEvent(new Event('input',{bubbles:true}));await pause(100);
        await press('Verify recovery archive');await press('Preview recovered source');
        await until(()=>{const error=form.querySelector('[role="alert"]');if(error)throw new Error('Policy preview UI: '+error.textContent.slice(0,500));return form.querySelector('[data-capture-preview="ready"]');},'The reviewed new policy was not previewed');
        form.querySelector('input[type="checkbox"]').click();await pause(100);await press('Apply policy and keep source paused');
        await until(()=>form.querySelector('[role="alert"]'),'The interrupted retirement did not show its unresolved result',90000);
        const pending=await until(()=>card().querySelector('[aria-label="Pending capture recoveries"]'),'The app did not offer recovery beside the interrupted operation');
        if(!pending.textContent.includes('retirement is not yet confirmed'))throw new Error('Pending recovery hid the uncertain previous-device retirement');
        const observed=await window.mnemion.sourceRecoveries();
        if(observed.items.length!==1||observed.items[0].previous_grant_revoked!==false||observed.items[0].copy_available)throw new Error('App and agent pending retirement states disagree');
        await press('Clear recovery choices');
        const button=async text=>{const b=await until(()=>[...pending.querySelectorAll('button')].find(e=>e.textContent===text&&!e.disabled),'Missing pending recovery control: '+text);b.click();await pause(100);};
        await button('Choose original backup');
        const recovery=pending.querySelector('input[type="password"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(recovery,${JSON.stringify(recoveryKey)});recovery.dispatchEvent(new Event('input',{bubbles:true}));await pause(100);
        await button('Finish recovery');
        const receipt=await until(()=>{const error=pending.querySelector('[role="alert"]');if(error)throw new Error('Pending retirement UI: '+error.textContent.slice(0,500));return pending.querySelector('[data-capture-restored="ready"]');},'The app did not reconcile and finish its paused policy replacement',90000);
        if(pending.querySelector('input[type="password"]')?.value||form.hasAttribute('data-update-pending'))throw new Error('Completed recovery retained a key or unfinished state');
        const view=await window.mnemion.sourceStatus();return view.sources.find(s=>s.id===receipt.dataset.sourceId);
      `)
    } finally { dialog.showOpenDialog = originalOpen }
    if (opens !== 2 || relay.retirementRequests !== 1 || relay.retirementRepliesDropped !== 1 || !replacement || replacement.id === id || replacement.enabled || replacement.capture_mode !== 'complete' ||
        replacement.capture_policy?.preset !== 'detailed' || replacement.capture_policy.format !== 'mnemion-capture-policy-v3' ||
        replacement.capture_policy.retention !== 'expire_after' || replacement.capture_policy.retention_days !== 7 ||
        replacement.capture_policy.expiry_scope !== 'captured_fragment_family' || replacement.capture_policy.exclude_fields?.join(',') !== 'test_secret' ||
        replacement.path !== folder || replacement.scope_id !== source.scope_id ||
        replacement.custody?.source_id !== id || replacement.custody.grant_id === grantId || replacement.max_files !== limits.max_files ||
        replacement.memory_limit_mib !== limits.memory_limit_mib || replacement.custody.pending_limit_mib !== limits.pending_limit_mib ||
        replacement.custody.history_limit_events !== limits.history_limit_events || replacement.custody.database_limit_mib !== limits.database_limit_mib) throw new Error('The policy form changed the reviewed source identity, resource limits or paused state.')
    const current = await call('source.status') as DesktopSourceView, fresh = await readSaved(replacement.id)
    if (current.sources.some(item => item.id === id) || !current.sources.some(item => item.id === replacement.id) ||
        !fresh?.sealed_inbox_key || fresh.sealed_inbox_key === fresh.sealed_key || fresh.sealed_inbox_key === saved.sealed_inbox_key || fresh.sealed_key === saved.sealed_key ||
        hash(await readFile(originalDatabase)) !== originalHash || (await call('source.restore.list')).items.length) throw new Error('Policy replacement reused keys, altered the original inbox or left an ambiguous source.')
    const preservedArchive = await call('source.backup.inspect', { file: archivePath, recovery_key: recoveryKey })
    if (preservedArchive.archive_sha256 !== archive.archive_sha256 || preservedArchive.binding.grant_id !== grantId ||
        preservedArchive.status.forgotten_events !== 1) throw new Error('Migration changed the original portable capture archive.')
    const newStatus = await call('source.drain', { id: replacement.id, expected_revision: current.revision, confirm: true })
    if (!newStatus.delivery_complete || newStatus.status.coverage.catalog !== 'unobserved' || newStatus.status.forgotten_events !== 1) throw new Error('The replacement claimed old coverage as new or lost its deletion history.')
    await inRenderer(window, `const grant=await request('GET','/v1/capture-grants/'+${JSON.stringify(grantId)});if(!grant.revoked_at||grant.active)throw new Error('The exact old device grant remains active after policy migration');`)
    const [width, height] = window.getContentSize()
    try {
      window.setContentSize(720, 1000)
      await inRenderer(window, `await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));document.querySelector('[data-capture-restored="ready"]').scrollIntoView({block:'center'});if(document.documentElement.scrollWidth>innerWidth+1)throw new Error('The policy migration receipt overflows a narrow app window');`)
      await writeFile(join(base, 'native-capture-policy.png'), (await window.webContents.capturePage()).toPNG(), { mode: 0o600, flag: 'wx' })
    } finally { window.setContentSize(width, height) }
    relay.capture(replacement.custody.grant_id, 'pass')
    await call('source.pause', { id: replacement.id, expected_revision: (await call('source.status')).revision, enabled: true })
    await until(async () => {
      relay.check()
      const { source } = await sourceStatus(replacement.id), report = source.activity.report?.capture
      return source.activity.phase !== 'scanning' && report?.delivery_complete && report.capture_complete && report.stored_events > 2 && report.forgotten_events >= 1 ? report : false
    }, 'The resumed policy replacement did not deliver its newly selected content.')
    await pauseSource(replacement.id)
    await inRenderer(window, `
      for(const [text,expected] of ${JSON.stringify([[laterText, true], [toolText, true], [forgottenText, false]])}){
        const result=await request('POST','/v1/recall',{query:text,all_accessible:true,mode:'lexical'});let present=false;
        for(const hit of result.hits){const m=await request('GET','/v1/memories/'+hit.memory_id);if(m.content.includes(text))present=true;}
        if(present!==expected)throw new Error('Resumed policy capture lost selected content or revived forgotten evidence');
      }
      await selectConnection(${JSON.stringify(fixture.connectorId)});
      const retention=await request('GET','/v1/connectors/'+${JSON.stringify(fixture.connectorId)}+'/capture-sources/'+${JSON.stringify(id)}+'/retention');
      if(retention.families<1||retention.pending_families<1||retention.due_families||retention.semantics!=='scheduled_cleanup'||retention.backup_erasure!=='not_included')throw new Error('The server did not schedule the reviewed expiry policy');
      const admin=await until(()=>document.querySelector('[data-capture-policy-source="'+${JSON.stringify(id)}+'"]'),'The retained source administration disappeared');
      const refresh=await until(()=>[...admin.querySelectorAll('button')].find(e=>e.textContent==='Refresh cleanup'&&!e.disabled),'Cleanup status cannot be refreshed');refresh.click();
      await until(()=>admin.querySelector('[data-capture-retention-status="ready"]')?.textContent.includes('scheduled families'),'The app did not expose retention cleanup status');
      const select=[...card().querySelectorAll('label')].find(e=>e.textContent.startsWith('Server retention'))?.querySelector('select');
      if(select?.value!=='expire_after')throw new Error('The source settings dropped the approved expiry choice');
      await click('Remove from this computer');await click('Revoke device grant and discard local inbox');
      await until(async()=>!(await window.mnemion.sourceStatus()).sources.some(s=>s.id===${JSON.stringify(replacement.id)}),'The reviewed policy fixture could not be removed',60000);
      await request('DELETE','/v1/connectors/'+${JSON.stringify(fixture.connectorId)});
      await request('POST','/v1/principals/'+${JSON.stringify(fixture.principalId)}+'/disable');
      location.hash='/workspace/memories';
    `)
    if ((await call('source.status')).sources.some((item: DesktopSource) => [id, replacement.id].includes(item.id))) throw new Error('The policy fixture left saved source credentials behind.')
    await rm(keptFile); await rm(forgottenFile); await rm(folder, { recursive: true })
    await rm(archivePath)
    relay.check()
    return { phase: 'capture-policy', nativeCapturePolicyPausedDrainThroughApp: true, nativeCapturePolicyDrainDoesNotRead: true,
      nativeCapturePolicyAdministratorReview: true, nativeCapturePolicyBackupAndMigrationThroughApp: true,
      nativeCapturePolicyRetainsResourceLimits: true, nativeCapturePolicyNewOsKeysAndOldGrantRetired: true,
      nativeCapturePolicyOldArchiveAndInboxUnmodified: true, nativeCapturePolicyNewCoverageUnobserved: true,
      nativeCapturePolicyForgetSurvivesReselection: true, nativeCapturePolicyResumedSelectionDelivered: true,
      nativeCapturePolicyAppAndAgentAgree: true, nativeCapturePolicyNarrowLayout: true, nativeCapturePolicyFixtureCleanup: true,
      nativeCapturePolicyExpiryReviewedAndPreserved: true, nativeCapturePolicyExpiryScheduledAndVisible: true,
      nativeCapturePolicyV3FieldExclusionsPreserved: true, nativeCapturePolicyLostRetirementReply: true,
      nativeCapturePolicyPendingRetirementVisible: true, nativeCapturePolicyRetirementReconciledWithoutReplay: true }
  } finally {
    // Always restore the original local workspace. Retain failed fixture files
    // for diagnosis; only a completed journey removes its own records/files.
    try {
      if (relayKey) {
        try { await inRenderer(window, `await request('DELETE','/v1/keys/'+${JSON.stringify(relayKey.id)});`) }
        finally {
          await inRenderer(window, `location.hash='/workspace/memories';`)
          await transition(window, 'local.open', { expected_revision: (await call('workspace.status')).revision }, local.info.settings.workspace_id)
        }
      }
    } finally { await relay.close() }
  }
}
