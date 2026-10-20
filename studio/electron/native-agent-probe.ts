/** Real bundled MCP startup from a disposable reviewed agent installation. */
import { app, type BrowserWindow } from 'electron'
import { spawn } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { mkdir, readFile, rm, stat, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { localEnvironment } from './local-workspace.js'
import type { AgentPreview, AgentSetupResult, AgentSetupStatus } from '../shared/desktop-agents.js'

type Call = (action: string, input?: Record<string, unknown>) => Promise<any>

export async function verifyStandaloneAgent(command: string, credentialFile: string, space: string, args?: string[]): Promise<void> {
  const child = spawn(command, args ?? ['--credentials', credentialFile, 'mcp'], {
    stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true, env: localEnvironment(process.env, dirname(credentialFile)),
  })
  let text = '', sequence = 0, failed = false
  const pending = new Map<number, { resolve: (value: any) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> }>()
  const fail = () => {
    failed = true
    for (const item of pending.values()) { clearTimeout(item.timer); item.reject(new Error('The installed agent command did not complete its MCP exchange.')) }
    pending.clear()
  }
  child.on('error', fail)
  const closed = new Promise<void>(resolve => child.once('close', () => { fail(); resolve() }))
  child.stdin.on('error', fail); child.stderr.resume(); child.stdout.setEncoding('utf8')
  child.stdout.on('data', (chunk: string) => {
    text += chunk
    if (Buffer.byteLength(text) > 1024 * 1024) { fail(); child.kill(); return }
    let end: number
    while ((end = text.indexOf('\n')) >= 0) {
      const line = text.slice(0, end); text = text.slice(end + 1)
      if (!line.trim()) continue
      try {
        const reply = JSON.parse(line), waiting = pending.get(reply.id)
        if (waiting) {
          pending.delete(reply.id); clearTimeout(waiting.timer)
          if (reply.error || !reply.result) waiting.reject(new Error('The installed MCP command rejected its probe.'))
          else waiting.resolve(reply.result)
        }
      } catch { fail(); child.kill() }
    }
  })
  const request = (method: string, params: Record<string, unknown>) => new Promise<any>((resolve, reject) => {
    if (failed) { reject(new Error('The installed MCP command has stopped.')); return }
    const id = ++sequence
    const timer = setTimeout(() => { pending.delete(id); reject(new Error('The installed MCP command exceeded its deadline.')); child.kill() }, 45000)
    pending.set(id, { resolve, reject, timer })
    child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n')
  })
  try {
    const initialized = await request('initialize', { protocolVersion: '2025-03-26', capabilities: {}, clientInfo: { name: 'native-agent-acceptance', version: '1' } })
    if (!initialized.serverInfo?.name) throw new Error('The installed MCP command did not identify its service.')
    child.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
    const tools = await request('tools/list', {})
    if (!tools.tools?.some((tool: any) => tool.name === 'memory_spaces')) throw new Error('The installed MCP command did not discover memory tools.')
    const spaces = await request('tools/call', { name: 'memory_spaces', arguments: {} })
    const items = spaces.structuredContent?.items
    if (spaces.isError || !Array.isArray(items) || items.length !== 1 || items[0].id !== space || items[0].role !== 'reader') throw new Error('The installed MCP command did not enforce the dedicated reader grant.')
  } finally {
    child.stdin.end()
    const timer = setTimeout(() => child.kill(), 5000)
    await closed; clearTimeout(timer)
  }
}

export async function verifyNativeAgents(window: BrowserWindow, call: Call): Promise<Record<string, boolean>> {
  const profile = process.env.MNEMION_STUDIO_USER_DATA!
  const folder = join(dirname(profile), 'native-agent-' + randomUUID().slice(0, 8))
  await mkdir(folder, { mode: 0o700 })
  const target = join(folder, 'agent.toml')
  const original = '# Preserve unrelated agent settings.\napproval_policy = "never"\n[mcp_servers.existing]\ncommand = "fixture-only-not-started"\n'
  await writeFile(target, original, { mode: 0o600, flag: 'wx' })
  const fixture = await window.webContents.executeJavaScript(`(async()=>{
    const s=(await window.mnemion.workspaceStatus()).active;
    async function request(method,path,body,expected=200){
      const r=await window.mnemion.serviceRequest({url:s.endpoint+path,method,headers:{Authorization:'Bearer '+s.sessionToken,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
      if(r.status!==expected)throw new Error('Native agent fixture request failed: '+r.status);
      return JSON.parse(new TextDecoder().decode(r.body));
    }
    const person=await request('POST','/v1/principals',{name:'Native scoped agent',kind:'application',administrator:false},201);
    const key=await request('POST','/v1/principals/'+person.id+'/keys',{name:'Disposable native agent'},201);
    const space=(await request('GET','/v1/spaces')).items[0].id;
    await request('PUT','/v1/spaces/'+space+'/grants/'+person.id,{role:'reader'});
    return {endpoint:s.endpoint,tenant:s.me.tenant_id,principal:person.id,key:key.api_key,keyId:key.id,space};
  })()`)
  let id: string | undefined
  try {
    for (const [client, filename, content] of [
      ['hermes', 'hermes.yaml', '# Keep Hermes policy\nmodel: {default: fixture-only}\nmcp_servers: {}\n'],
      ['openclaw', 'openclaw.json5', '{// Keep OpenClaw policy\n gateway:{bind:"loopback"},mcp:{servers:{}}}\n'],
    ]) {
      const path = join(folder, filename)
      await writeFile(path, content, { mode: 0o600, flag: 'wx' })
      const reviewed = await call('agent.preview', { setup: { client, server_name: 'mnemion-native', config_path: path,
        endpoint: fixture.endpoint, tenant_id: fixture.tenant, principal_id: fixture.principal } }) as AgentPreview
      if (reviewed.replacing || !reviewed.snippet.includes('mnemion-native') || JSON.stringify(reviewed).includes(fixture.key) || (await readFile(path, 'utf8')) !== content) throw new Error('The installed engine could not safely preview the native agent format.')
    }
    const preview = await call('agent.preview', { setup: { client: 'grok-build', server_name: 'mnemion-native', config_path: target,
      endpoint: fixture.endpoint, tenant_id: fixture.tenant, principal_id: fixture.principal } }) as AgentPreview
    id = preview.setup.id
    if (preview.replacing || (await readFile(target, 'utf8')) !== original || JSON.stringify(preview).includes(fixture.key)) throw new Error('Agent preview changed settings or exposed a key.')
    const installed = await window.webContents.executeJavaScript(`window.mnemion.agentSetupInstall(${JSON.stringify({ setup: preview.setup, configuration_hash: preview.configuration_hash, credential: fixture.key, confirm: true, replace_existing: false })})`) as AgentSetupResult
    if (installed.installation.state !== 'installed' || !installed.backup || (await readFile(installed.backup, 'utf8')) !== original) throw new Error('The native agent installer did not preserve its original settings.')
    const saved = await call('agent.status') as AgentSetupStatus
    if (!saved.installations.some(item => item.id === id && item.state === 'installed') || JSON.stringify(saved).includes(fixture.key)) throw new Error('Native agent status lost the installation or exposed its key.')
    if (app.isPackaged && (saved.runtime_version !== app.getVersion() || saved.runtime_attention || [preview.command.command, ...preview.command.args].some(value => value.includes(process.resourcesPath)))) throw new Error('Agent setup still depends on the application bundle instead of its maintained private runtime.')
    const credentialFile = join(profile, 'mnemion-desktop-agents', id, 'credentials.json')
    if (process.platform !== 'win32' && ((await stat(credentialFile)).mode & 0o077)) throw new Error('The native agent credentials are not private.')
    await verifyStandaloneAgent(preview.command.command, credentialFile, fixture.space, preview.command.args)
    const old = await window.webContents.executeJavaScript('window.location.hash')
    try {
      await window.webContents.executeJavaScript("window.location.hash='/workspace/agents'")
      const visible = await window.webContents.executeJavaScript(`(async()=>{const until=Date.now()+30000;while(Date.now()<until){if(document.body.textContent.includes('Connect an agent on this computer')&&document.body.textContent.includes('mnemion-native'))return true;await new Promise(r=>setTimeout(r,100));}return false;})()`)
      if (!visible) throw new Error('The installed agent page did not show native setup and its saved connection.')
    } finally { await window.webContents.executeJavaScript(`window.location.hash=${JSON.stringify(old)}`) }
    await call('agent.remove', { id, configuration_hash: saved.installations.find(item => item.id === id)!.configuration_hash, confirm: true })
    const remaining = await readFile(target, 'utf8')
    if (!remaining.includes('approval_policy = "never"') || !remaining.includes('[mcp_servers.existing]') || remaining.includes('mnemion-native')) throw new Error('Removing native agent setup changed unrelated settings.')
    return { nativeAgentPreviewAndInstall: true, nativeAgentPrivateCredentials: true, nativeAgentStandaloneMcp: true, nativeAgentAdditionalFormats: true,
      nativeAgentReaderPermissions: true, nativeAgentAppAndPrivateControls: true, nativeAgentRemovalPreservedSettings: true,
      nativeAgentIndependentRuntime: !!saved.runtime_version && !saved.runtime_attention }
  } finally {
    const status = await call('agent.status') as AgentSetupStatus
    const item = status.installations.find(item => item.id === id)
    if (item) await call('agent.remove', { id: item.id, configuration_hash: item.configuration_hash, confirm: true })
    await window.webContents.executeJavaScript(`(async()=>{const s=(await window.mnemion.workspaceStatus()).active;for(const [method,path] of [['DELETE','/v1/keys/'+${JSON.stringify(fixture.keyId)}],['POST','/v1/principals/'+${JSON.stringify(fixture.principal)}+'/disable']]){const r=await window.mnemion.serviceRequest({url:s.endpoint+path,method,headers:{Authorization:'Bearer '+s.sessionToken}});if(r.status!==200)throw new Error('Native agent fixture cleanup failed.');}})()`)
    await rm(folder, { recursive: true, force: true })
  }
}
