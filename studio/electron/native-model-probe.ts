/** Installed-host model enrollment: private state, restart, public choices and no inference. */
import type { BrowserWindow } from 'electron'
import { createServer } from 'node:http'
import { readFile, stat } from 'node:fs/promises'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'
import type { LocalStatus } from '../shared/local-workspace.js'
import type { ModelDefinition } from '../shared/local-models.js'
import { ModelSetupFailure, type ModelSetupPhase, type ModelSetupReason } from './native-model-diagnostics.js'

type Call = (action: string, input?: Record<string, unknown>, workspace?: string) => Promise<any>

export async function verifyNativeModels(window: BrowserWindow, call: Call): Promise<Record<string, boolean>> {
  let requests = 0
  const server = createServer((_request, response) => { requests++; response.writeHead(503); response.end() })
  try {
    await new Promise<void>((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
    const address = server.address()
    if (!address || typeof address === 'string') throw new ModelSetupFailure('initial', 'action_failed')
    return await verifyProfiles(window, call, 'http://127.0.0.1:' + address.port, () => requests)
  } catch (error) {
    throw error instanceof ModelSetupFailure ? error : new ModelSetupFailure('initial', 'action_failed')
  } finally {
    server.closeAllConnections()
    await new Promise<void>(resolve => server.close(() => resolve()))
  }
}

async function verifyProfiles(window: BrowserWindow, call: Call, origin: string, requests: () => number): Promise<Record<string, boolean>> {
  let phase: ModelSetupPhase = 'initial'
  let observed: LocalStatus | undefined
  const status = async () => { observed = await call('status') as LocalStatus; return observed }
  const fail = (reason: ModelSetupReason): never => { throw new ModelSetupFailure(phase, reason, observed) }
  const failure = (error: unknown) => error instanceof ModelSetupFailure ? error : new ModelSetupFailure(phase, 'action_failed', observed)
  const before = await status()
  const workspace = before.info?.settings?.workspace_id
  if (!workspace || !before.info?.model_access) fail('missing_status')
  const suffix = randomUUID().slice(0, 8)
  const key = 'disposable-native-model-key-' + suffix
  const providers: ModelDefinition[] = [
    { kind: 'embedding', profile: { id: 'native-embedding-' + suffix, label: 'Native embedding setup proof',
      protocol: 'openai', endpoint: origin + '/v1/embeddings', model: 'fixture-only', revision: 'native-v1', dimensions: 2 } },
    { kind: 'librarian', profile: { id: 'native-librarian-' + suffix, label: 'Native librarian setup proof',
      protocol: 'ollama', endpoint: origin + '/api/chat', model: 'fixture-only', revision: 'native-v1' } },
  ]
  const steady = async () => {
    const ready = await window.webContents.executeJavaScript(`(async()=>{const end=Date.now()+30000;while(Date.now()<end){if(window.mnemion.updateSafety())return true;await new Promise(r=>setTimeout(r,100));}return false;})()`)
    if (!ready) fail('pending_app_work')
  }
  const change = async (input: Record<string, unknown>) => {
    const end = Date.now() + 30000
    for (;;) {
      const current = await status()
      await steady()
      try {
        return await call('local.models', { workspace_id: workspace,
          expected_revision: current.info!.model_access!.revision, ...input }, workspace) as LocalStatus
      } catch (error) {
        // Background UI reads can start between the two safety checks. This
        // specific refusal happens before any mutation; other failures propagate.
        if (!(error instanceof Error) || !error.message.endsWith('Save or discard edits and finish pending requests in the app before restarting its workspace.') || Date.now() >= end) throw error
        await new Promise(resolve => setTimeout(resolve, 100))
      }
    }
  }
  const wait = async () => {
    const end = Date.now() + 120000
    while (Date.now() < end) {
      const current = await status()
      // A structured error may arrive before the process closes. Preserve it
      // immediately; waiting for close used to replace it with a timeout.
      if (current.errorCode || current.state === 'error') fail('restart_error')
      if (current.state === 'running') return current
      await new Promise(resolve => setTimeout(resolve, 300))
    }
    fail('restart_timeout')
  }
  const oldLocation = await window.webContents.executeJavaScript('window.location.hash')
  let failed = false
  try {
    for (const provider of providers) {
      phase = provider.kind === 'embedding' ? 'save_embedding' : 'save_librarian'
      const saved = await change({ action: 'save', provider, api_key: key })
      if (JSON.stringify(saved).includes(key)) fail('private_key_exposed')
      await wait()
    }
    phase = 'inspect'
    const current = await status()
    if (!providers.every(provider => current.info!.model_access!.providers.some(p => p.kind === provider.kind && p.profile.id === provider.profile.id && p.has_api_key))) fail('profiles_missing')
    const path = join(before.info!.data_directory, 'model-providers.json')
    const privateRecord = JSON.parse(await readFile(path, 'utf8'))
    if (privateRecord.providers.filter((p: any) => p.api_key === key).length !== 2) fail('private_credentials_missing')
    if (process.platform !== 'win32' && ((await stat(path)).mode & 0o077)) fail('permissions')
    const choices = await window.webContents.executeJavaScript(`(async()=>{
      const s=(await window.mnemion.workspaceStatus()).active;
      async function get(path){const r=await window.mnemion.serviceRequest({url:s.endpoint+path,method:'GET',headers:{Authorization:'Bearer '+s.sessionToken}});if(r.status!==200)throw new Error('Native model choices unavailable');return JSON.parse(new TextDecoder().decode(r.body));}
      const space=(await get('/v1/spaces')).items[0].id;
      return {embedding:await get('/v1/spaces/'+space+'/embedding'),librarian:await get('/v1/spaces/'+space+'/librarian/models'),settings:await get('/v1/spaces/'+space+'/librarian')};
    })()`)
    if (!choices.embedding.profiles.some((p: any) => p.id === providers[0].profile.id && p.registered) ||
        !choices.librarian.items.some((p: any) => p.id === providers[1].profile.id) ||
        choices.settings.enabled || JSON.stringify(choices).includes(key)) fail('public_choices_invalid')
    phase = 'app'
    await window.webContents.executeJavaScript("window.location.hash='/workspace/setup'")
    const visible = await window.webContents.executeJavaScript(`(async()=>{const end=Date.now()+30000;while(Date.now()<end){const card=document.getElementById('model-providers');if(card?.textContent.includes('Native embedding setup proof')&&card.textContent.includes('Native librarian setup proof'))return true;await new Promise(r=>setTimeout(r,100));}return false;})()`)
    if (!visible) fail('app_choices_missing')
    if (requests()) fail('unselected_network')
    return { nativeModelPrivateSetup: true, nativeModelRestartAndChoices: true,
      nativeModelAppAndAgentControls: true, nativeModelEnrollmentWithoutInference: true }
  } catch (error) {
    failed = true
    throw failure(error)
  } finally {
    // On failure, the enclosing installed-host probe shuts down the actual app
    // and retains its disposable state. Do not mutate a failing host again or
    // let fixture cleanup replace the first error with a later timeout.
    if (!failed) try {
      phase = 'restore_view'
      await window.webContents.executeJavaScript(`window.location.hash=${JSON.stringify(oldLocation)}`)
      for (const provider of providers) {
        phase = provider.kind === 'embedding' ? 'remove_embedding' : 'remove_librarian'
        const current = await status()
        if (current.info?.model_access?.providers.some(p => p.kind === provider.kind && p.profile.id === provider.profile.id)) {
          await change({ action: 'remove', kind: provider.kind, profile_id: provider.profile.id })
          await wait()
        }
      }
      const cleared = await status()
      if (!cleared.info?.model_access) fail('missing_status')
      if (providers.some(provider => cleared.info!.model_access!.providers.some(
        saved => saved.kind === provider.kind && saved.profile.id === provider.profile.id))) fail('cleanup_profiles_remain')
    } catch (error) { throw failure(error) }
  }
}
