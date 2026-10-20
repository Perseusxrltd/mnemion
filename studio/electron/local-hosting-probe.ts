/** Installed-app validation, enabled only with a private disposable profile. */
import type { BrowserWindow } from 'electron'
import { readFile, stat, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { verifyPersonalAccess } from './personal-access-probe.js'
import { verifyNativeBackups } from './native-backup-probe.js'

export async function verifyLocalHostingProbe(window: BrowserWindow): Promise<Record<string, unknown> | null> {
  const path = process.env.MNEMION_STUDIO_HOSTING_PROBE
  const profile = process.env.MNEMION_STUDIO_USER_DATA
  const smoke = process.env.MNEMION_STUDIO_SMOKE_FILE
  if (!path) return null
  if (!profile || !smoke || dirname(resolve(path)) !== dirname(resolve(profile)) || dirname(resolve(smoke)) !== dirname(resolve(path)) ||
      (await stat(path)).size > 4096) throw new Error('Hosting validation requires an isolated profile and evidence directory')
  const config = JSON.parse(await readFile(path, 'utf8'))
  if (!['create', 'resume', 'recover-port', 'sign-in', 'sign-in-resume', 'backup-capture', 'backup-recover', 'backup-resume'].includes(config.phase) || !Number.isInteger(config.port) || config.port < 1024 || config.port > 65535 ||
      (config.phase !== 'create' && !['memoryId', 'spaceId'].every(key => /^[a-f0-9-]{36}$/.test(config[key])))) throw new Error('Invalid hosting validation configuration')
  if (config.phase === 'sign-in-resume' && !['tenantId', 'principalId', 'sessionId'].every(key => /^[a-f0-9-]{36}$/.test(config[key]))) throw new Error('Invalid personal-access validation identity')
  if (config.phase.startsWith('backup-')) {
    const result = await verifyNativeBackups(window, config, path)
    await writeFile(join(dirname(path), config.phase + '-workspace.png'), (await window.webContents.capturePage()).toPNG(), { mode: 0o600 })
    return result
  }
  if (config.phase.startsWith('sign-in')) {
    const result = await verifyPersonalAccess(window, config)
    await writeFile(join(dirname(path), config.phase + '-workspace.png'), (await window.webContents.capturePage()).toPNG(), { mode: 0o600 })
    return result
  }
  const result = await window.webContents.executeJavaScript(`(async () => {
    const config = ${JSON.stringify(config)};
    const bridge = window.mnemion;
    const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
    async function until(check, message, timeout = 30000) {
      const deadline = Date.now() + timeout;
      do { const value = await check(); if (value) return value; await pause(100); } while (Date.now() < deadline);
      throw new Error(typeof message === 'function' ? message() : message);
    }
    const button = text => [...document.querySelectorAll('button')].find(node => (node.querySelector('strong')?.textContent === text || node.textContent.trim() === text) && !node.matches(':disabled') && node.getClientRects().length);
    async function click(text) { (await until(() => button(text), 'Missing enabled control: ' + text)).click(); await pause(100); }
    async function input(selector, value) {
      const field = await until(() => document.querySelector(selector), () => {
        // Only fixed selectors and classifications leave the private renderer.
        // Never include input values, page text or an arbitrary route/query.
        const known = ['input[autocomplete="organization"]', 'input[autocomplete="name"]', '.ws-memory-limit input', '.ws-setup-advanced input[max="65535"]'];
        const label = document.querySelector('.ws-setup-steps')?.getAttribute('aria-label');
        const step = [1, 2, 3].find(number => label === 'Setup step ' + number + ' of 3') ?? null;
        const route = location.hash === '#/workspace' ? 'workspace' : location.hash.startsWith('#/help?') || location.hash === '#/help' ? 'help' : 'other';
        return 'Missing setup field: ' + JSON.stringify({ selector: known.includes(selector) ? selector : 'unknown', step, route });
      });
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(field, value);
      field.dispatchEvent(new Event('input', { bubbles: true })); await pause(100);
    }
    location.hash = '/workspace';
    if (config.phase === 'create') {
      const initial = await bridge.localStatus();
      if (!initial.available || initial.info?.configured) throw new Error('The installed app must offer a fresh complete local runtime');
      await click('Create on this computer');
      if (config.emulated) await until(() => document.querySelector('.ws-local-setup')?.textContent.includes('through Windows x64 compatibility'), 'The Windows ARM setup did not disclose backend emulation');
      await input('input[autocomplete="organization"]', 'Équipe installed validation');
      await input('input[autocomplete="name"]', 'Disposable owner');
      await click('Continue');
      const model = await until(() => document.querySelector('.ws-setup-fields select'), 'Missing model selection');
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(model, 'e5-small');
      model.dispatchEvent(new Event('change', { bubbles: true })); await pause(100);
      document.querySelector('input[name="memory-mode"][value="manual"]').click();
      await input('.ws-memory-limit input', '2048');
      document.querySelector('.ws-setup-advanced').open = true;
      await input('.ws-setup-advanced input[max="65535"]', String(config.port));
      await click('Continue');
      await until(() => document.querySelector('.ws-setup-review')?.textContent.includes('Équipe installed validation'), 'Setup review did not retain entered settings');
      await click('Create workspace');
      await until(async () => {
        const status = await bridge.localStatus();
        if (status.state === 'error') throw new Error('Installed local setup failed: ' + status.errorCode + ' / stage ' + status.stage + ' / ' + status.message + ' / diagnostic ' + JSON.stringify(status.diagnostic));
        return status.state === 'running';
      }, 'The installed local runtime did not finish setup', 600000);
      await click('Open workspace');
    }
    if (config.phase === 'recover-port') {
      await until(async () => {
        const status = await bridge.localStatus();
        if (status.state === 'error' && status.errorCode !== 'port_in_use') throw new Error('Unexpected port recovery failure: ' + status.errorCode);
        return status.state === 'error' && status.errorCode === 'port_in_use';
      }, 'The occupied local port did not reach its recovery screen', 180000);
      await until(() => document.querySelector('.ws-local-setup')?.textContent.includes('Another program is using this workspace'), 'The UI did not explain the local address conflict');
      await click('Save local address');
      await until(() => document.querySelector('.ws-local-setup')?.textContent.includes('Address saved. Resume the workspace when ready.'), 'The UI did not confirm the saved address');
      const changed = await bridge.localStatus();
      if (changed.state !== 'stopped' || changed.info.settings.port === config.port) throw new Error('Port repair must retain a stopped workspace at a new address');
      await click('Resume local workspace');
      await until(async () => (await bridge.localStatus()).state === 'running', 'The repaired workspace did not resume', 180000);
      // Saved local workspaces reopen automatically once an explicit Resume
      // succeeds. Do not wait for a button that disappears as the UI opens.
    }
    await until(() => document.querySelector('.ws-workspace-name')?.textContent === 'Équipe installed validation',
      'The installed UI did not open or automatically restore its local workspace', 180000);
    const session = (await bridge.workspaceStatus()).active;
    if (!session || session.me.tenant_name !== 'Équipe installed validation') throw new Error('The UI has no authenticated local session');
    if (session.me.service_version !== await bridge.version()) throw new Error('The local session did not retain the bundled server version');
    if (config.phase === 'recover-port' && new URL(session.endpoint).port === String(config.port)) throw new Error('The repaired UI reconnected to the occupied old address');
    async function request(method, path, body) {
      const response = await bridge.serviceRequest({ url: session.endpoint + path, method,
        headers: { Authorization: 'Bearer ' + session.sessionToken, 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
        ...(body ? { body: JSON.stringify(body) } : {}) });
      if (response.status < 200 || response.status >= 300) throw new Error('Installed service request failed: ' + path + ' / ' + response.status);
      return JSON.parse(new TextDecoder().decode(response.body));
    }
    const spaces = (await request('GET', '/v1/spaces')).items;
    if (['create', 'resume'].includes(config.phase) && spaces.length !== 1) throw new Error('Setup must create exactly one private space');
    const originalSpace = config.phase === 'create' ? spaces[0] : spaces.find(space => space.id === config.spaceId);
    if (!originalSpace) throw new Error('The original private space was lost after restart');
    let memoryId = config.memoryId;
    if (config.phase === 'create') {
      const saved = await request('POST', '/v1/spaces/' + originalSpace.id + '/memories',
        { content: 'Installed application validation: shared memory keeps assistants connected across applications.', kind: 'note' });
      await until(async () => {
        const operation = await request('GET', '/v1/operations/' + saved.operation_id);
        if (operation.state === 'failed') throw new Error('Installed semantic indexing failed');
        return operation.state === 'ready';
      }, 'Installed semantic indexing did not finish', 120000);
      memoryId = saved.memory_id;
    } else {
      if ((await request('GET', '/v1/memories/' + memoryId)).memory_id !== memoryId) throw new Error('A memory was lost after the installed app restarted');
    }
    const recalled = await request('POST', '/v1/recall', { query: 'assistants share memory across applications', space_ids: [originalSpace.id], mode: 'semantic' });
    if (!recalled.hits.some(hit => hit.memory_id === memoryId)) throw new Error('The installed model did not retrieve the saved memory');
    const status = await bridge.localStatus();
    if (status.info?.resources?.remote_access?.ngrok_sdk !== '1.7.0') throw new Error('The installed engine cannot load its reviewed ngrok SDK');
    if (status.info?.settings?.memory?.limit_mib !== 2048) throw new Error('The setup RAM policy was not retained');
    if (config.phase === 'create') {
      location.hash = '/workspace/journal';
      await until(() => document.querySelector('.ws-journal-host'), 'The installed app did not offer local journal registration');
      await click('Register a repository');
      await input('.ws-journal-host input[type="url"]', 'https://git.example.invalid/team/memory.git');
      document.querySelector('.ws-journal-host input[type="checkbox"][required]').click();
      await click('Save host registration');
      await until(async () => {
        const current = await bridge.localStatus();
        if (current.state === 'error') throw new Error('Journal registration restart failed: ' + current.errorCode);
        return current.state === 'running' && current.info?.journal_access?.destinations.some(item => item.space_id === originalSpace.id && item.remote === 'https://git.example.invalid/team/memory.git');
      }, 'Journal registration did not survive the controlled host restart', 180000);
      const journal = await request('GET', '/v1/spaces/' + originalSpace.id + '/writeback');
      if (journal.configured || journal.destination?.repository !== 'https://git.example.invalid/team/memory.git') throw new Error('Host registration must retain separate space approval before publication');
      if ((await request('GET', '/v1/memories/' + memoryId)).memory_id !== memoryId) throw new Error('Journal registration lost an existing memory');
      location.hash = '/workspace/memories';
      await until(() => !document.querySelector('.ws-journal-host form'), 'Journal setup did not close');
    }
    await until(() => bridge.updateSafety(), 'Settled workspace must permit a guarded update');
    const picker = await until(() => document.querySelector('select[aria-label="Memory space"]'), 'Missing memory-space navigation');
    picker.dispatchEvent(new Event('change', { bubbles: true }));
    await until(() => bridge.updateSafety(), 'Memory-space navigation incorrectly blocks updates');
    location.hash = '/workspace/new';
    // The previous journal page also has textareas; wait for the actual editor
    // instead of editing a node that React removes during this navigation.
    const draft = await until(() => document.querySelector('.ws-page textarea[placeholder="What should this workspace remember?"]'), 'Missing memory editor');
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(draft, 'Disposable unsaved update-guard check');
    draft.dispatchEvent(new Event('input', { bubbles: true })); await pause(100);
    if (bridge.updateSafety()) throw new Error('An unsaved memory permits an update restart');
    location.hash = '/workspace/memories';
    await until(() => !draft.isConnected && bridge.updateSafety(), 'Closing the disposable editor did not restore update readiness');
    if (typeof window.require !== 'undefined') throw new Error('The installed renderer is not sandboxed');
    return { phase: config.phase, memoryId, spaceId: originalSpace.id, endpoint: session.endpoint, tenantId: session.me.tenant_id,
      actualSetupControls: config.phase === 'create', uiOpenedWorkspace: true, nativeService: true,
      journalRegistrationControls: config.phase === 'create',
      authenticatedApi: true, serverVersionRetained: true, realModelInference: true, semanticSaveAndRecall: true, nativeNgrokSdkLoaded: true,
      automaticReopen: config.phase === 'resume', recoveredPortConflict: config.phase === 'recover-port', savedMemoryPresent: true, memoryPolicyRetained: true,
      navigationPreservesUpdateReadiness: true, unsavedDraftBlocksUpdate: true, closedEditorRestoresUpdateReadiness: true };
  })()`)
  await writeFile(join(dirname(path), config.phase + '-workspace.png'), (await window.webContents.capturePage()).toPNG(), { mode: 0o600 })
  return result
}

export function watchHostingProbeQuit(quit: () => void): void {
  const path = process.env.MNEMION_STUDIO_HOSTING_PROBE
  if (!path || !process.env.MNEMION_STUDIO_USER_DATA || !process.env.MNEMION_STUDIO_SMOKE_FILE) return
  const timer = setInterval(() => {
    if (existsSync(join(dirname(path), 'quit-request'))) { clearInterval(timer); quit() }
  }, 100)
  timer.unref()
}
