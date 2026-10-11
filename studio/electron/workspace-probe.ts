/** Native release gate. Only invoked with an explicit disposable smoke profile. */
import type { BrowserWindow } from 'electron'
import { readFile, stat } from 'node:fs/promises'

export async function verifyNativeWorkspaceProbe(window: BrowserWindow): Promise<Record<string, unknown> | null> {
  const path = process.env.MNEMION_STUDIO_WORKSPACE_PROBE
  if (!path || !process.env.MNEMION_STUDIO_SMOKE_FILE) return null
  if ((await stat(path)).size > 16384) throw new Error('Invalid workspace probe configuration')
  const config = JSON.parse(await readFile(path, 'utf8'))
  if (!config || !['save', 'resume'].includes(config.phase) || typeof config.credential !== 'string' ||
      !/^[A-Za-z0-9_-]{32,128}$/.test(config.credential) || typeof config.endpoint !== 'string' ||
      !/^http:\/\/127\.0\.0\.1:\d{1,5}\/organization$/.test(config.endpoint)) throw new Error('Invalid workspace probe configuration')
  return window.webContents.executeJavaScript(`(async () => {
    const { endpoint, credential, phase } = ${JSON.stringify(config)};
    const bridge = window.mnemion;
    const initial = await bridge.workspaceStatus();
    const secure = initial.secureStorage;
    let session;
    if (phase === 'resume' && secure) {
      session = await bridge.workspaceResume();
      if (!session?.remembered) throw new Error('The saved native connection did not resume');
    } else {
      if (phase === 'resume' && await bridge.workspaceResume() !== null) throw new Error('A session-only key persisted after exit');
      session = await bridge.workspaceConnect({ endpoint, credential, remember: secure });
    }
    if (session.endpoint !== endpoint || session.me.tenant_name !== 'Native validation' || JSON.stringify(session).includes(credential)) throw new Error('The native session exposed a credential or returned another workspace');
    const request = url => bridge.serviceRequest({url, method: 'GET', headers: { Authorization: 'Bearer ' + session.sessionToken }});
    const result = await request(endpoint + '/v1/me');
    if (result.status !== 200) throw new Error('The native broker did not authenticate its API request');
    let outsideRejected = false;
    try { await request(endpoint.replace('/organization', '') + '/v1/me'); } catch { outsideRejected = true; }
    if (!outsideRejected) throw new Error('A native workspace handle escaped its API prefix');
    let uiRestored = false;
    if (phase === 'resume' && secure) {
      const deadline = Date.now() + 10000;
      do {
        uiRestored = document.querySelector('.ws-workspace-name')?.textContent === 'Native validation';
        if (uiRestored) break;
        await new Promise(resolve => setTimeout(resolve, 100));
      } while (Date.now() < deadline);
      if (!uiRestored) throw new Error('Studio did not reopen the saved workspace after process restart');
    }
    await bridge.workspaceDisconnect();
    let staleRejected = false;
    try { await request(endpoint + '/v1/me'); } catch { staleRejected = true; }
    if (!staleRejected || await bridge.workspaceResume() !== null) throw new Error('Disconnect did not invalidate the native connection');
    if (secure && phase === 'save') {
      await bridge.workspaceRestore(session.bookmarkId);
    } else if (secure) {
      await bridge.workspaceForget(session.bookmarkId);
      if ((await bridge.workspaceStatus()).bookmarks.length) throw new Error('The native connection was not forgotten');
    }
    return { phase, secureStorage: secure, authenticated: true, outsideRejected, staleRejected,
      reconnectPaused: true, savedForRestart: secure && phase === 'save',
      processRestartRestored: secure && phase === 'resume', uiRestored,
      sessionOnlyDidNotPersist: !secure && phase === 'resume', forgotten: secure && phase === 'resume' };
  })()`)
}
