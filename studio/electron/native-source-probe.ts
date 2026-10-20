/** Disposable installed-app acceptance for folder onboarding and private controls. */
import type { BrowserWindow } from 'electron'
import { randomUUID } from 'node:crypto'
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import type { DesktopSourceView } from '../shared/desktop-sources.js'

type Call = (action: string, input?: Record<string, unknown>) => Promise<any>

export async function verifyNativeSources(window: BrowserWindow, call: Call): Promise<Record<string, boolean>> {
  const path = join(dirname(process.env.MNEMION_STUDIO_USER_DATA!), 'native-source-' + randomUUID())
  await mkdir(path, { mode: 0o700 })
  await writeFile(join(path, 'decision.md'), 'Native source acceptance: this device can capture shared memory.', { mode: 0o600, flag: 'wx' })
  const id = randomUUID()
  const fixture = await window.webContents.executeJavaScript(`(async()=>{
    const session=(await window.mnemion.workspaceStatus()).active;
    async function request(method,path,body,expected){
      const response=await window.mnemion.serviceRequest({url:session.endpoint+path,method,
        headers:{Authorization:'Bearer '+session.sessionToken,'Content-Type':'application/json'},
        ...(body?{body:JSON.stringify(body)}:{})});
      if(response.status!==expected)throw new Error('Native source fixture request failed: '+response.status);
      return JSON.parse(new TextDecoder().decode(response.body));
    }
    const person=await request('POST','/v1/principals',{name:'Native source application',kind:'application',administrator:false},201);
    const key=await request('POST','/v1/principals/'+person.id+'/keys',{name:'Disposable source key'},201);
    const source=await request('POST','/v1/connectors',{name:'Native Studio source',provider:'filesystem',principal_id:person.id,access_mode:'published'},201);
    return {endpoint:session.endpoint,tenantId:session.me.tenant_id,principalId:person.id,connectorId:source.id,keyId:key.id,credential:key.api_key};
  })()`)
  try {
    const before = await call('source.status') as DesktopSourceView
    if (!before.secure_storage) throw new Error('Native source acceptance requires protected credential storage.')
    const input = { expected_revision: before.revision, credential: fixture.credential,
      source: { id, endpoint: fixture.endpoint, tenant_id: fixture.tenantId, principal_id: fixture.principalId,
        connector_id: fixture.connectorId, name: 'Native Studio source', provider: 'filesystem', path, members: [],
        publish_to_mapped_members: true, poll_seconds: 300, memory_limit_mib: 256, max_files: 100, enabled: false } }
    // Exercise the renderer bridge for setup, then the private local agent for
    // status, resume, scan and removal against the same saved configuration.
    const saved = await window.webContents.executeJavaScript(`window.mnemion.sourceConfigure(${JSON.stringify(input)})`) as DesktopSourceView
    if (saved.sources.find(item => item.id === id)?.enabled !== false || JSON.stringify(saved).includes(fixture.credential) || JSON.stringify(saved).includes('sealed_key')) throw new Error('Native source setup exposed a key or lost its paused state.')
    const savedPath = saved.sources.find(item => item.id === id)!.path
    const settings = await readFile(join(process.env.MNEMION_STUDIO_USER_DATA!, 'mnemion-desktop-sources', 'sources.json'), 'utf8')
    if (settings.includes(fixture.credential)) throw new Error('A desktop source key was persisted without OS protection.')
    await call('source.pause', { expected_revision: saved.revision, id, enabled: true })
    let completed = false
    const until = Date.now() + 90000
    while (Date.now() < until) {
      const current = (await call('source.status') as DesktopSourceView).sources.find(item => item.id === id)
      if (current?.activity.report?.completed) {
        if (current.activity.report.changed !== 1) throw new Error('The native source did not capture exactly its selected document.')
        completed = true; break
      }
      if (current?.activity.phase === 'attention') throw new Error('Native source scan failed: ' + current.activity.message)
      await new Promise(resolve => setTimeout(resolve, 500))
    }
    if (!completed) throw new Error('The native source scan did not complete within its deadline.')
    const originalHash = await window.webContents.executeJavaScript('window.location.hash')
    try {
      await window.webContents.executeJavaScript(`window.location.hash='/workspace/connections'`)
      const visible = await window.webContents.executeJavaScript(`(async()=>{
        const until=Date.now()+30000;
        while(Date.now()<until){
          const selector=[...document.querySelectorAll('select')].find(s=>[...s.options].some(o=>o.value===${JSON.stringify(fixture.connectorId)}));
          if(selector&&selector.value!==${JSON.stringify(fixture.connectorId)}){Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(selector,${JSON.stringify(fixture.connectorId)});selector.dispatchEvent(new Event('change',{bubbles:true}));}
          if(document.body.textContent.includes('Run on this computer')&&document.body.textContent.includes(${JSON.stringify(savedPath)}))return true;
          await new Promise(r=>setTimeout(r,100));
        }
        return false;
      })()`)
      if (!visible) throw new Error('The installed Connections page did not display its configured source.')
    } finally { await window.webContents.executeJavaScript(`window.location.hash=${JSON.stringify(originalHash)}`) }
    return { nativeSourceCapture: true, nativeSourceEncryptedCredential: true, nativeSourceAppAndAgentControls: true, nativeSourceVisibleInConnections: true }
  } finally {
    const current = await call('source.status') as DesktopSourceView
    if (current.sources.some(item => item.id === id)) await call('source.remove', { expected_revision: current.revision, id, confirm: true })
    await window.webContents.executeJavaScript(`(async()=>{
      const s=(await window.mnemion.workspaceStatus()).active;
      for(const [method,path,label] of [['DELETE','/v1/connectors/'+${JSON.stringify(fixture.connectorId)},'connection'],['DELETE','/v1/keys/'+${JSON.stringify(fixture.keyId)},'key'],['POST','/v1/principals/'+${JSON.stringify(fixture.principalId)}+'/disable','application']]){
        const r=await window.mnemion.serviceRequest({url:s.endpoint+path,method,headers:{Authorization:'Bearer '+s.sessionToken}});
        if(r.status!==200)throw new Error('Native source fixture cleanup failed for '+label+' ('+r.status+').');
      }
    })()`)
    await rm(path, { recursive: true, force: true })
  }
}
