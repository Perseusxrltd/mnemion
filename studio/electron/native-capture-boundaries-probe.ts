/** Real installed capture boundaries, across two launches of one private profile. */
import { safeStorage, type BrowserWindow } from 'electron'
import { createHash, randomUUID } from 'node:crypto'
import { appendFile, mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import type { CapturePolicy, CaptureReport, DesktopSource, DesktopSourceView } from '../shared/desktop-sources.js'
import { callNativeOperator as call } from './native-operator-probe.js'
import { inRenderer, pauseSource, sourceStatus, until } from './native-capture-probe.js'
import { NativeCaptureRelay } from './native-capture-relay.js'

const hash = (value: string | Buffer) => createHash('sha256').update(value).digest('hex')
const line = (value: unknown) => Buffer.from(JSON.stringify(value) + '\n')
const message = (text: string) => line({ type: 'event_msg', payload: { type: 'user_message', message: text } })
const metadata = () => line({ type: 'session_meta', payload: { id: randomUUID() } })
function canonical(value: any): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']'
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}'
  return JSON.stringify(value)
}

async function transition(window: BrowserWindow, action: string, input: Record<string, unknown>, workspace?: string) {
  const deadline = Date.now() + 30000
  for (;;) {
    await inRenderer(window, `await until(()=>window.mnemion.updateSafety(),'Finish app work before changing the capture connection');`)
    try { return await call(action, input, workspace) } catch (error) {
      if (!(error instanceof Error) || !error.message.endsWith('Save or discard edits and finish pending requests in the app before changing its workspace.') || Date.now() >= deadline) throw error
      await new Promise(resolve => setTimeout(resolve, 100))
    }
  }
}

async function cycle(id: string, relay: NativeCaptureRelay, expected: (report: CaptureReport) => boolean, label: string) {
  const before = await sourceStatus(id)
  if (before.source.enabled) throw new Error('The boundary fixture must explicitly resume a paused source.')
  const previous = before.source.activity.finished_at
  await call('source.pause', { id, expected_revision: before.view.revision, enabled: true })
  const report = await until(async () => {
    relay.check()
    const { source } = await sourceStatus(id)
    const report = source.activity.report?.capture
    return source.activity.phase !== 'scanning' && source.activity.finished_at !== previous && report && expected(report) ? report : false
  }, label)
  await pauseSource(id)
  return report
}

async function assertReader(window: BrowserWindow, credential: string, sourceSpace: string, memory?: string) {
  await inRenderer(window, `
    const session=(await window.mnemion.workspaceStatus()).active;
    const headers={Authorization:'Bearer '+${JSON.stringify(credential)}};
    const me=await window.mnemion.serviceRequest({url:session.endpoint+'/v1/me',method:'GET',headers});
    if(me.status!==200)throw new Error('The revoked reader must remain an authenticated account');
    const response=await window.mnemion.serviceRequest({url:session.endpoint+'/v1/spaces',method:'GET',headers});
    if(response.status!==200||JSON.parse(new TextDecoder().decode(response.body)).items.some(s=>s.id===${JSON.stringify(sourceSpace)}))throw new Error('Capture replay restored a removed reader grant');
    ${memory ? `const value=await window.mnemion.serviceRequest({url:session.endpoint+'/v1/memories/'+${JSON.stringify(memory)},method:'GET',headers});if(![403,404].includes(value.status))throw new Error('A revoked reader can read a captured memory');` : ''}
  `)
}

function verifyPages(relay: NativeCaptureRelay, fixture: any, expected: Array<{ text: string; raw: Buffer; start: number; generation: number }>) {
  if (relay.dropped !== 1 || relay.pages.length !== 1 || relay.reconciled.length) throw new Error('The boundary fixture did not lose exactly one real commit reply.')
  const { page, receipt } = relay.pages[0]
  if (page.events.length !== expected.length || receipt.items.length !== expected.length || receipt.source_id !== fixture.id) throw new Error('The delivery page lost accepted source fragments.')
  const generations = new Map<number, string>(), scope = page.events[0].producer_scope
  for (const item of expected) {
    const matching = page.events.filter(event => event.item.memory.content.includes(item.text) && event.item.memory.metadata.source_segment_sha256 === hash(item.raw))
    if (matching.length !== 1) throw new Error('The accepted page duplicated or omitted a selected message.')
    const event = matching[0], attributes = event.item.memory.metadata
    if (event.producer_scope !== scope || event.event_id !== hash(canonical(['mnemion-capture-event-v1', fixture.id, scope, event.item])) ||
        attributes.source_byte_start !== item.start || attributes.source_byte_end !== item.start + item.raw.length ||
        attributes.source_segment_sha256 !== hash(item.raw) || attributes.raw_evidence_stored !== false ||
        attributes.capture_mode !== 'messages' || attributes.capture_policy_revision !== fixture.policyRevision ||
        JSON.stringify(event).includes(fixture.excludedText)) throw new Error('Captured event identity, byte range, digest or selection provenance changed.')
    const previous = generations.get(item.generation)
    if (previous && previous !== attributes.source_generation) throw new Error('Appending an incomplete message changed its original producer generation.')
    generations.set(item.generation, attributes.source_generation)
    const accepted = receipt.items.filter(item => item.event_id === event.event_id)
    if (accepted.length !== 1 || accepted[0].outcome !== 'stored' || !accepted[0].memory_id || !accepted[0].operation_id) throw new Error('The committed receipt omitted a durable memory or operation identity.')
  }
  if (new Set(generations.values()).size !== generations.size) throw new Error('Log rotation reused the old producer generation.')
  return { page, receipt }
}

export async function verifyNativeCaptureBoundaries(window: BrowserWindow, config: Record<string, unknown>, probePath: string): Promise<Record<string, unknown>> {
  const base = dirname(probePath), profile = process.env.MNEMION_STUDIO_USER_DATA!
  const fixturePath = join(base, 'native-capture-boundary-fixture.json')
  const settingsPath = join(profile, 'mnemion-desktop-sources', 'sources.json')
  const readSaved = async (id: string) => JSON.parse(await readFile(settingsPath, 'utf8')).sources.find((source: any) => source.id === id)
  await until(async () => (await window.webContents.executeJavaScript('window.mnemion.localStatus()')).operator?.state === 'ready', 'The capture boundary operator did not start.')
  const local = await until(async () => {
    const state = await call('status')
    if (state.state === 'error') throw new Error('The disposable boundary host could not start: ' + state.errorCode)
    return state.state === 'running' ? state : false
  }, 'The capture boundary host did not finish its normal startup.', 180000)
  const workspace = local.info.settings.workspace_id
  if (!safeStorage.isEncryptionAvailable()) throw new Error('The installed boundary gate needs its real OS key store.')
  await inRenderer(window, `await until(async()=>!!document.querySelector('.ws-workspace-name')&&window.mnemion.updateSafety()&&!!(await window.mnemion.workspaceStatus()).active?.me.administrator,'The boundary fixture owner did not reopen',180000);`)
  const owner = await inRenderer(window, `return (await window.mnemion.workspaceStatus()).active;`)
  const resume = config.phase === 'capture-boundaries-resume'
  const fixture: any = resume ? JSON.parse(await readFile(fixturePath, 'utf8')) : { id: randomUUID(), grantId: randomUUID(), workspace,
    endpoint: owner.endpoint, tenantId: owner.me.tenant_id, ownerId: owner.me.principal_id }
  if (fixture.workspace !== workspace || fixture.endpoint !== owner.endpoint || fixture.tenantId !== owner.me.tenant_id || fixture.ownerId !== owner.me.principal_id) throw new Error('The capture boundary fixture reopened a different workspace or owner.')
  const relay = new NativeCaptureRelay(fixture.endpoint)
  const endpoint = await relay.start(resume ? Number(new URL(fixture.captureEndpoint).port) : 0)
  // Renderer session handles are intentionally bound to one endpoint. Issue a
  // disposable owner key through the authenticated bridge instead of treating
  // that private handle as a transferable service credential.
  let relayKey: { id: string; api_key: string } | undefined
  try {
    const issued = await inRenderer(window, `return request('POST','/v1/principals/'+${JSON.stringify(fixture.ownerId)}+'/keys',{name:'Disposable native capture relay'},201);`) as { id: string; api_key: string }
    relayKey = issued
    const connected = await transition(window, 'workspace.connect', { endpoint, credential: issued.api_key, remember: false,
      expected_revision: (await call('workspace.status')).revision, expected_tenant_id: fixture.tenantId, expected_principal_id: fixture.ownerId })
    if (connected.active?.endpoint !== endpoint || connected.active?.me.principal_id !== fixture.ownerId) throw new Error('The native operator selected a different capture relay identity.')
    await inRenderer(window, `await until(async()=>{const s=(await window.mnemion.workspaceStatus()).active;return s?.endpoint===${JSON.stringify(endpoint)}&&!!document.querySelector('.ws-workspace-name')&&window.mnemion.updateSafety();},'The app did not display the operator-selected capture connection');`)
    if (!resume) {
      const folder = join(base, 'Capture boundaries Équipe ' + randomUUID())
      await mkdir(folder, { mode: 0o700 })
      const selectedLog = join(folder, 'session.jsonl'), rolledLog = join(folder, 'session.rolled')
      const policy: CapturePolicy = { format: 'mnemion-capture-policy-v1', preset: 'conversation', capture_mode: 'messages',
        include: ['*.jsonl'], exclude: [], retention: 'until_deleted', max_file_bytes: 1000000000, max_record_bytes: 2000000 }
      const created = await inRenderer(window, `
        const application=await request('POST','/v1/principals',{name:'Native boundary capture',kind:'application',administrator:false},201);
        const device=await request('POST','/v1/principals/'+application.id+'/keys',{name:'Disposable boundary device'},201);
        const reader=await request('POST','/v1/principals',{name:'Native boundary reader',kind:'application',administrator:false},201);
        const readerKey=await request('POST','/v1/principals/'+reader.id+'/keys',{name:'Disposable scoped reader'},201);
        const connector=await request('POST','/v1/connectors',{name:'Native boundary conversations',provider:'conversations',principal_id:application.id,access_mode:'published'},201);
        await request('PUT','/v1/connectors/'+connector.id+'/bindings',{external_id:'boundary-owner',principal_id:${JSON.stringify(fixture.ownerId)},role:'reviewer'});
        await request('PUT','/v1/connectors/'+connector.id+'/bindings',{external_id:'boundary-reader',principal_id:reader.id,role:'reader'});
        const source=await request('PUT','/v1/connectors/'+connector.id+'/capture-sources/'+${JSON.stringify(fixture.id)},
          {namespace:'native-boundaries',name:'Native boundary conversations',members:['boundary-owner','boundary-reader'],capture_mode:'messages',keep_accepted:true,capture_policy:${JSON.stringify(policy)}});
        await request('PUT','/v1/capture-sources/'+source.source_id+'/grants/'+${JSON.stringify(fixture.grantId)},{device_key_id:device.id});
        return {principalId:application.id,connectorId:connector.id,spaceId:source.space_id,readerId:reader.id,readerKey:readerKey.api_key,credential:device.api_key};
      `)
      const { credential, readerKey, ...identities } = created
      Object.assign(fixture, identities, { captureEndpoint: endpoint, folder, selectedLog, rolledLog,
        policyRevision: hash(canonical(policy)), sealedReaderKey: safeStorage.encryptString(readerKey).toString('base64'),
        selectedText: 'First complete boundary message ' + randomUUID(),
        completedText: 'Completed Unicode boundary é 🧠 ' + randomUUID(),
        rotatedText: 'Accepted after actual log rotation ' + randomUUID(),
        excludedText: 'Excluded private tool frame ' + randomUUID() })
      const selection = { path: folder, capture_mode: 'messages', capture_policy: policy, keep_accepted: true,
        memory_limit_mib: 256, max_files: 100, pending_limit_mib: 32, history_limit_events: 2000, database_limit_mib: 128 }
      const preview = await call('source.preview', { selection })
      if (preview.policy_revision !== fixture.policyRevision || preview.content_saved || preview.hidden_reasoning !== 'unavailable') throw new Error('The agent preview changed the reviewed capture policy or claimed hidden data access.')
      const source: DesktopSource = { id: fixture.id, endpoint, tenant_id: fixture.tenantId, connector_id: fixture.connectorId,
        principal_id: fixture.principalId, name: 'Native boundary conversations', provider: 'conversations', path: folder,
        scope_id: 'native-boundaries', members: ['boundary-owner', 'boundary-reader'], capture_mode: 'messages', capture_policy: policy,
        custody: { source_id: fixture.id, grant_id: fixture.grantId, keep_accepted: true, pending_limit_mib: 32, history_limit_events: 2000, database_limit_mib: 128 },
        publish_to_mapped_members: true, poll_seconds: 300, memory_limit_mib: 256, max_files: 100, enabled: false }
      const saved = await call('source.configure', { expected_revision: (await call('source.status')).revision,
        source, credential, preview_hash: preview.configuration_hash }) as DesktopSourceView
      if (saved.sources.find(item => item.id === fixture.id)?.enabled !== false || JSON.stringify(saved).includes(credential)) throw new Error('Native agent enrollment failed to retain a private paused source.')
      const sealedInbox = (await readSaved(fixture.id)).sealed_inbox_key
      fixture.sealedInboxSha256 = hash(sealedInbox)
      const first = Buffer.concat([metadata(), message(fixture.selectedText),
        line({ type: 'response_item', payload: { type: 'function_call_output', call_id: 'synthetic', output: fixture.excludedText } })])
      const second = message(fixture.completedText)
      const split = second.indexOf(Buffer.from('é')) + 1
      if (split < 2 || second[split] !== 0xa9) throw new Error('The fixture must split a real multibyte UTF-8 character.')
      await writeFile(selectedLog, Buffer.concat([first, second.subarray(0, split)]), { mode: 0o600, flag: 'wx' })
      relay.capture(fixture.grantId, 'offline')
      const partial = await cycle(fixture.id, relay, report => report.pending_events === 1 && report.reason_code === 'capture_delivery_unavailable', 'Incomplete native capture was not saved before delivery.')
      if (partial.coverage?.examined_prefix_bytes !== first.length || partial.coverage.observed_bytes !== first.length + split ||
          partial.coverage.unaccepted_observed_bytes !== split || partial.coverage.records.selected !== 1 || partial.coverage.records.omitted !== 2 ||
          partial.coverage.history_before_tracking !== 'unknown' || !partial.coverage.queue_nonempty_since || partial.stored_events !== 0) throw new Error('The installed capture advanced past an incomplete UTF-8 record or lost its real byte coverage.')
      fixture.queueSince = partial.coverage.queue_nonempty_since
      // Adjust capacity through the real form while paused. The device key,
      // source identity and already accepted queue must remain the same.
      relay.capture(fixture.grantId, 'pass')
      await inRenderer(window, `
        await selectConnection(${JSON.stringify(fixture.connectorId)});
        const settings=[...card().querySelectorAll('details')].find(e=>e.querySelector('form'));if(!settings)throw new Error('Missing source settings form');settings.open=true;
        const set=async(label,value)=>{const input=[...settings.querySelectorAll('label')].find(e=>e.textContent.startsWith(label))?.querySelector('input');if(!input||input.disabled)throw new Error('Missing native quota control: '+label);Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,String(value));input.dispatchEvent(new Event('input',{bubbles:true}));await pause(100);};
        await set('Maximum entries per history counter',3000);await set('Maximum encrypted storage for this source (MiB)',192);
        await click('Preview capture');await until(()=>card().querySelector('[data-capture-preview="ready"]'),'Capacity changes were not previewed');
        card().querySelector('input[type="checkbox"][required]').click();await pause(100);await click('Save source settings');
        await until(async()=>{const view=await window.mnemion.sourceStatus();const item=view.sources.find(s=>s.id===${JSON.stringify(fixture.id)});const error=card()?.querySelector('[role="alert"]');if(error)throw new Error('Capacity form failed: '+error.textContent.slice(0,500));return item?.custody?.history_limit_events===3000&&item.custody.database_limit_mib===192&&!card().hasAttribute('data-update-pending');},'The app did not save the reviewed history capacity');
      `)
      if (hash((await readSaved(fixture.id)).sealed_inbox_key) !== fixture.sealedInboxSha256) throw new Error('Changing native capacity replaced the inbox key.')
      relay.capture(fixture.grantId, 'offline')
      await appendFile(selectedLog, second.subarray(split))
      const completed = await cycle(fixture.id, relay, report => report.pending_events === 2 && report.coverage?.unaccepted_observed_bytes === 0, 'Completing the UTF-8 record did not capture exactly its new fragment.')
      if (completed.coverage?.examined_prefix_bytes !== first.length + second.length || completed.coverage.records.selected !== 2 ||
          completed.coverage.queue_nonempty_since !== fixture.queueSince || completed.history?.events !== 2 ||
          completed.history.event_limit !== 3000 || completed.history.database_limit_bytes !== 192 * 1024 * 1024) throw new Error('Capture app/agent quotas, byte progress or queue age disagree.')
      const abandoned = Buffer.from('{"type":"event_msg","payload":{"type":"user_message","message":"Unfinished before rotation')
      await appendFile(selectedLog, abandoned)
      await cycle(fixture.id, relay, report => report.pending_events === 2 && report.coverage?.unaccepted_observed_bytes === abandoned.length, 'The native capture did not retain its unresolved producer tail.')
      const rotated = Buffer.concat([metadata(), message(fixture.rotatedText)])
      await rename(selectedLog, rolledLog)
      await writeFile(selectedLog, rotated, { mode: 0o600, flag: 'wx' })
      const afterRotation = await cycle(fixture.id, relay, report => report.pending_events === 3 && report.coverage?.uncertain_scopes === 1, 'Native log rotation lost accepted fragments or its unresolved gap.')
      if (afterRotation.coverage?.unresolved_previous_bytes !== abandoned.length || afterRotation.coverage.records.selected !== 1 ||
          afterRotation.coverage.examined_prefix_bytes !== rotated.length || afterRotation.coverage.queue_nonempty_since !== fixture.queueSince) throw new Error('The native rotation status overstated complete history.')
      fixture.unresolvedBytes = abandoned.length
      await inRenderer(window, `
        await request('DELETE','/v1/connectors/'+${JSON.stringify(fixture.connectorId)}+'/bindings',
          {external_id:'boundary-reader',principal_id:${JSON.stringify(fixture.readerId)},role:'reader'});
      `)
      await assertReader(window, readerKey, fixture.spaceId)
      relay.capture(fixture.grantId, 'drop')
      const lost = await cycle(fixture.id, relay, report => report.unknown_pages === 1 && report.pending_events === 3 && report.stored_events === 0 && report.reason_code === 'capture_delivery_unavailable', 'A lost native commit reply did not retain an honest uncertain queue.')
      const evidence = verifyPages(relay, fixture, [
        { text: fixture.selectedText, raw: first, start: 0, generation: 0 },
        // The open final fragment has a new immutable revision when its tail
        // completes. Both approved revisions are retained as separate events.
        { text: fixture.completedText, raw: Buffer.concat([first, second]), start: 0, generation: 0 },
        { text: fixture.rotatedText, raw: rotated, start: 0, generation: 1 },
      ])
      await assertReader(window, readerKey, fixture.spaceId, evidence.receipt.items[0].memory_id!)
      const ciphertext = await readFile(join(profile, 'mnemion-desktop-sources', 'inbox-' + fixture.id, 'inbox.sqlite3'))
      if ([fixture.selectedText, fixture.completedText, fixture.rotatedText, fixture.excludedText].some(text => ciphertext.includes(Buffer.from(text)))) throw new Error('The native boundary inbox stored plaintext conversation content.')
      Object.assign(fixture, evidence, { unknownPages: lost.unknown_pages })
      await writeFile(fixturePath, JSON.stringify(fixture), { mode: 0o600, flag: 'wx' })
      return { phase: config.phase, nativeCaptureAgentEnrollment: true, nativeCaptureIncompleteUnicode: true,
        nativeCaptureQuotaAppAndAgentAgree: true, nativeCaptureCompletedUnicode: true,
        nativeCaptureRotationKeepsAcceptedAndGap: true, nativeCaptureExactEventProvenance: true,
        nativeCaptureLostRealCommitReply: true, nativeCaptureReaderRevokedWhileQueued: true,
        nativeCaptureBoundaryPrivateState: true, acceptedEvents: 3 }
    }

    const saved = await readSaved(fixture.id), current = await sourceStatus(fixture.id)
    const previous = current.source.activity.report?.capture
    if (!saved || saved.enabled || hash(saved.sealed_inbox_key) !== fixture.sealedInboxSha256 ||
        current.source.activity.durability !== 'saved' || !previous || previous.unknown_pages !== fixture.unknownPages ||
        previous.pending_events !== 3 || previous.stored_events !== 0) throw new Error('Restart lost the uncertain capture queue, pause or protected key.')
    const readerKey = safeStorage.decryptString(Buffer.from(fixture.sealedReaderKey, 'base64'))
    relay.capture(fixture.grantId, 'pass')
    const delivered = await cycle(fixture.id, relay, report => report.pending_events === 0 && report.stored_events === 3 && report.unknown_pages === 0 && report.delivery_complete, 'The installed app did not reconcile its lost commit after restart.')
    const coverage = delivered.coverage
    if (relay.pages.length || relay.reconciled.length !== 1 || relay.reconciled[0] !== fixture.page.page_id || !coverage ||
        coverage.unresolved_previous_bytes !== fixture.unresolvedBytes || coverage.queue_nonempty_since !== null ||
        !coverage.last_acknowledged_at || delivered.history?.event_limit !== 3000 ||
        delivered.history.database_limit_bytes !== 192 * 1024 * 1024) throw new Error('Reconciliation repeated a write, concealed a producer gap or lost the configured history limits.')
    const index = coverage.index
    if (index?.status !== 'available' || index.completed?.counts.events !== 3 || index.completed.counts.lexical_indexed !== 3 ||
        index.completed.counts.forgotten !== 0) throw new Error('The real workspace indexing observation did not match the three committed capture events.')
    await inRenderer(window, `
      for(const receipt of ${JSON.stringify(fixture.receipt.items)}){
        const memory=await request('GET','/v1/memories/'+receipt.memory_id);
        if(memory.memory_id!==receipt.memory_id||memory.version!==1)throw new Error('Capture reconciliation created an extra memory or revision');
      }
      for(const text of ${JSON.stringify([fixture.selectedText, fixture.completedText, fixture.rotatedText])}){
        const expected=${JSON.stringify(fixture.page.events)}.filter(event=>event.item.memory.content.includes(text)).map(event=>event.event_id);
        const result=await request('POST','/v1/recall',{query:text,all_accessible:true,mode:'lexical',max_per_source:0});
        const actual=[];for(const hit of result.hits){const memory=await request('GET','/v1/memories/'+hit.memory_id);if(memory.content.includes(text))actual.push(memory.memory_id);}
        const expectedMemories=${JSON.stringify(fixture.receipt.items)}.filter(item=>expected.includes(item.event_id)).map(item=>item.memory_id).sort();
        if(JSON.stringify(actual.sort())!==JSON.stringify(expectedMemories))throw new Error('Reconciled native capture has a missing or extra fragment revision');
      }
      const grouped=await request('POST','/v1/recall',{query:${JSON.stringify(fixture.selectedText)},all_accessible:true,mode:'lexical'});
      if(grouped.source_grouping.max_per_source!==1||grouped.hits.length!==1)throw new Error('Normal recall stopped grouping retained revisions from one original source');
      await selectConnection(${JSON.stringify(fixture.connectorId)});
      await until(()=>{const status=card()?.querySelector('[aria-label="Retained capture status"]');return status?.textContent.includes('0 queued')&&status.textContent.includes('acknowledged by the workspace');},'The installed app did not show its reconciled queue');
    `)
    await assertReader(window, readerKey, fixture.spaceId, fixture.receipt.items[0].memory_id)
    const forgotten = fixture.receipt.items.find((item: any) => fixture.page.events.find((event: any) => event.event_id === item.event_id)?.item.memory.content.includes(fixture.selectedText))
    if (!forgotten?.memory_id) throw new Error('The fixture lost its explicit deletion target.')
    const forgottenIds = fixture.receipt.items.filter((item: any) => item.lineage_id === forgotten.lineage_id).map((item: any) => item.memory_id)
    if (forgottenIds.length !== 2) throw new Error('The completed fragment must retain its two original revisions before forgetting.')
    await inRenderer(window, `
      const preview=await request('GET','/v1/memories/'+${JSON.stringify(forgotten.memory_id)});
      if(!preview.capture_forget)throw new Error('A captured fragment did not expose its deletion scope');
      await request('DELETE','/v1/memories/'+${JSON.stringify(forgotten.memory_id)}+'?expected_version='+preview.version,null,202);
    `)
    const deviceKey = safeStorage.decryptString(Buffer.from(saved.sealed_key, 'base64'))
    const replay = await inRenderer(window, `
      const response=await window.mnemion.serviceRequest({url:${JSON.stringify(endpoint + '/v1/capture-grants/' + fixture.grantId + '/pages')},method:'POST',
        headers:{Authorization:'Bearer '+${JSON.stringify(deviceKey)},'Content-Type':'application/json','Idempotency-Key':'capture:'+${JSON.stringify(fixture.page.page_id)}},body:JSON.stringify(${JSON.stringify(fixture.page)})});
      if(response.status!==200)throw new Error('The native device could not reconcile its original retained page after deletion');
      return JSON.parse(new TextDecoder().decode(response.body));
    `)
    if (replay.items.filter((item: any) => item.outcome === 'forgotten').length !== 2 ||
        replay.items.find((item: any) => item.event_id === forgotten.event_id)?.memory_id !== null) throw new Error('Replaying a retained page resurrected an explicitly forgotten fragment.')
    const fenced = await cycle(fixture.id, relay, report => report.pending_events === 0 && report.forgotten_events === 2 && report.stored_events === 1, 'Native capture did not apply the current deletion fence.')
    if (fenced.history?.denials !== 1 || fenced.coverage?.index?.completed?.counts.forgotten !== 2) throw new Error('Native history and workspace indexing lost the deletion decision.')
    relay.capture(fixture.grantId, 'offline')
    await appendFile(fixture.selectedLog, message('Queued before reviewed policy revocation ' + randomUUID()))
    await cycle(fixture.id, relay, report => report.pending_events === 1 && report.reason_code === 'capture_delivery_unavailable', 'The fixture did not accept its later message before policy review.')
    relay.capture(fixture.grantId, 'pass')
    await inRenderer(window, `
      const route='/v1/connectors/'+${JSON.stringify(fixture.connectorId)}+'/capture-sources/'+${JSON.stringify(fixture.id)};
      const review=await request('GET',route+'/policy-review');
      const changed=await request('PUT',route+'/policy-transitions/'+crypto.randomUUID(),{expected_version:review.source.version,review_token:review.review_token,
        capture_policy:{...review.source.capture_policy,preset:'detailed',capture_mode:'complete'},previous_grants:'revoke',confirm:true});
      if(changed.source.capture_mode!=='complete')throw new Error('The native policy review did not change the future source selection');
    `)
    const postsBefore = relay.pages.length
    const revoked = await cycle(fixture.id, relay, report => report.pending_events === 1 && report.reason_code === 'capture_authorization_revoked', 'An old native capture grant continued delivery after reviewed revocation.')
    if (relay.pages.length !== postsBefore || revoked.stored_events !== 1 || (await sourceStatus(fixture.id)).source.capture_mode !== 'messages') throw new Error('Policy revocation rewrote old selection, delivered without authority or lost accepted evidence.')
    await inRenderer(window, `
      await selectConnection(${JSON.stringify(fixture.connectorId)});
      await click('Remove from this computer');await click('Revoke device grant and discard local inbox');
      await until(async()=>!(await window.mnemion.sourceStatus()).sources.some(s=>s.id===${JSON.stringify(fixture.id)}),'The administrator could not retire the paused revoked capture device',60000);
      const grant=await request('GET','/v1/capture-grants/'+${JSON.stringify(fixture.grantId)});if(grant.active||!grant.revoked_at)throw new Error('Retirement left the capture grant active');
      for(const item of ${JSON.stringify(fixture.receipt.items.filter((item: any) => !forgottenIds.includes(item.memory_id)))}){
        const memory=await request('GET','/v1/memories/'+item.memory_id);if(memory.version!==1)throw new Error('Capture cleanup modified an accepted memory');
      }
      for(const id of ${JSON.stringify(forgottenIds)})await request('GET','/v1/memories/'+id,null,404);
      await request('DELETE','/v1/connectors/'+${JSON.stringify(fixture.connectorId)});
      await request('POST','/v1/principals/'+${JSON.stringify(fixture.readerId)}+'/disable');
      await request('POST','/v1/principals/'+${JSON.stringify(fixture.principalId)}+'/disable');
      location.hash='/workspace/memories';
    `)
    if (await readSaved(fixture.id)) throw new Error('Native boundary removal left its source credentials.')
    await rm(fixture.selectedLog); await rm(fixture.rolledLog); await rm(fixture.folder, { recursive: true }); await rm(fixturePath)
    relay.check()
    return { phase: config.phase, nativeCaptureUnknownReceiptSurvivesRestart: true,
      nativeCaptureReceiptReconciledWithoutWrite: true, nativeCaptureMemoryIdsAndVersionsRetained: true,
      nativeCaptureIndexObservedSeparately: true, nativeCaptureRevokedReaderStaysRevoked: true,
      nativeCaptureReplayRespectsForget: true, nativeCaptureLocalDeletionHistory: true,
      nativeCaptureReviewedPolicyStopsOldGrant: true, nativeCapturePendingRetiredThroughApp: true,
      nativeCaptureBoundaryCleanup: true, acceptedEvents: 3 }
  } finally {
    // Restore the real host before closing its temporary transport. No saved
    // workspace credential or permanent listener is created by the fixture.
    await inRenderer(window, `location.hash='/workspace/memories';`)
    try {
      await transition(window, 'local.open', { expected_revision: (await call('workspace.status')).revision }, workspace)
      if (relayKey) await inRenderer(window, `await request('DELETE','/v1/keys/'+${JSON.stringify(relayKey.id)});`)
    } finally { await relay.close() }
  }
}
