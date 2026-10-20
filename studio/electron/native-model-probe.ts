/** Installed-host model enrollment: private state, restart, public choices and no inference. */
import type { BrowserWindow } from 'electron'
import { createServer } from 'node:http'
import { readFile, stat } from 'node:fs/promises'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'
import type { LocalStatus } from '../shared/local-workspace.js'
import type { ModelDefinition } from '../shared/local-models.js'

type Call = (action: string, input?: Record<string, unknown>, workspace?: string) => Promise<any>

export async function verifyNativeModels(window: BrowserWindow, call: Call): Promise<Record<string, boolean>> {
  let requests = 0
  const server = createServer((_request, response) => { requests++; response.writeHead(503); response.end() })
  await new Promise<void>((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
  const address = server.address()
  if (!address || typeof address === 'string') throw new Error('The disposable model endpoint did not start.')
  const origin = 'http://127.0.0.1:' + address.port
  const before = await call('status') as LocalStatus
  const workspace = before.info?.settings?.workspace_id
  if (!workspace || !before.info?.model_access) { server.close(); throw new Error('Native model setup status is missing.') }
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
    if (!ready) throw new Error('Native model setup found pending app work before a host restart.')
  }
  const change = async (input: Record<string, unknown>) => {
    const end = Date.now() + 30000
    for (;;) {
      const current = await call('status') as LocalStatus
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
      const status = await call('status') as LocalStatus
      if (status.state === 'running') return status
      if (status.state === 'error') throw new Error('Native host could not resume its saved model configuration.')
      await new Promise(resolve => setTimeout(resolve, 300))
    }
    throw new Error('Native host did not resume before the model-setup deadline.')
  }
  const oldLocation = await window.webContents.executeJavaScript('window.location.hash')
  try {
    for (const provider of providers) {
      const saved = await change({ action: 'save', provider, api_key: key })
      if (JSON.stringify(saved).includes(key)) throw new Error('Model setup exposed its private key.')
      await wait()
    }
    const current = await call('status') as LocalStatus
    if (!providers.every(provider => current.info!.model_access!.providers.some(p => p.kind === provider.kind && p.profile.id === provider.profile.id && p.has_api_key))) throw new Error('Native model profiles were not retained after restart.')
    const path = join(before.info!.data_directory, 'model-providers.json')
    const privateRecord = JSON.parse(await readFile(path, 'utf8'))
    if (privateRecord.providers.filter((p: any) => p.api_key === key).length !== 2) throw new Error('Private model credentials were not retained.')
    if (process.platform !== 'win32' && ((await stat(path)).mode & 0o077)) throw new Error('Native model credentials are not private.')
    const choices = await window.webContents.executeJavaScript(`(async()=>{
      const s=(await window.mnemion.workspaceStatus()).active;
      async function get(path){const r=await window.mnemion.serviceRequest({url:s.endpoint+path,method:'GET',headers:{Authorization:'Bearer '+s.sessionToken}});if(r.status!==200)throw new Error('Native model choices unavailable');return JSON.parse(new TextDecoder().decode(r.body));}
      const space=(await get('/v1/spaces')).items[0].id;
      return {embedding:await get('/v1/spaces/'+space+'/embedding'),librarian:await get('/v1/spaces/'+space+'/librarian/models'),settings:await get('/v1/spaces/'+space+'/librarian')};
    })()`)
    if (!choices.embedding.profiles.some((p: any) => p.id === providers[0].profile.id && p.registered) ||
        !choices.librarian.items.some((p: any) => p.id === providers[1].profile.id) ||
        choices.settings.enabled || JSON.stringify(choices).includes(key)) throw new Error('Native public model choices did not preserve registration, privacy and disabled processing.')
    await window.webContents.executeJavaScript("window.location.hash='/workspace/setup'")
    const visible = await window.webContents.executeJavaScript(`(async()=>{const end=Date.now()+30000;while(Date.now()<end){const card=document.getElementById('model-providers');if(card?.textContent.includes('Native embedding setup proof')&&card.textContent.includes('Native librarian setup proof'))return true;await new Promise(r=>setTimeout(r,100));}return false;})()`)
    if (!visible) throw new Error('The installed model setup screen did not show its saved profiles.')
    if (requests) throw new Error('Saving an unselected model unexpectedly contacted its provider.')
    return { nativeModelPrivateSetup: true, nativeModelRestartAndChoices: true,
      nativeModelAppAndAgentControls: true, nativeModelEnrollmentWithoutInference: true }
  } finally {
    await window.webContents.executeJavaScript(`window.location.hash=${JSON.stringify(oldLocation)}`)
    try {
      for (const provider of providers) {
        const current = await call('status') as LocalStatus
        if (current.info?.model_access?.providers.some(p => p.kind === provider.kind && p.profile.id === provider.profile.id)) {
          await change({ action: 'remove', kind: provider.kind, profile_id: provider.profile.id })
          await wait()
        }
      }
    } finally {
      await new Promise<void>(resolve => server.close(() => resolve()))
    }
  }
}
