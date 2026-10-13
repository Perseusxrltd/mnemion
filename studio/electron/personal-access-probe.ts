/** Invoked only by the installed-workspace gate in its disposable profile. */
import type { BrowserWindow } from 'electron'

export async function verifyPersonalAccess(window: BrowserWindow, config: Record<string, unknown>): Promise<Record<string, unknown>> {
  return window.webContents.executeJavaScript(`(async () => {
    const config = ${JSON.stringify(config)};
    const bridge = window.mnemion;
    const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
    async function until(check, message, timeout = 30000) {
      const deadline = performance.now() + timeout;
      do { const value = await check(); if (value) return value; await pause(100); } while (performance.now() < deadline);
      throw new Error(message);
    }
    const button = text => [...document.querySelectorAll('button')].find(node =>
      (node.querySelector('strong')?.textContent === text || node.textContent.trim() === text) && !node.matches(':disabled') && node.getClientRects().length);
    async function click(text) { (await until(() => button(text), 'Missing personal-access control: ' + text)).click(); await pause(100); }
    async function input(label, value) {
      const field = await until(() => [...document.querySelectorAll('label.ws-field')].find(node => node.querySelector('span')?.textContent === label)?.querySelector('input'), 'Missing personal-access field: ' + label);
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(field, value);
      field.dispatchEvent(new Event('input', { bubbles: true })); await pause(100);
    }
    async function request(session, method, path, body, expected = 200) {
      const response = await bridge.serviceRequest({ url: session.endpoint + path, method,
        headers: { Authorization: 'Bearer ' + session.sessionToken, 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
        ...(body ? { body: JSON.stringify(body) } : {}) });
      if (response.status !== expected) throw new Error('Personal-access service request failed: ' + path + ' / ' + response.status);
      return JSON.parse(new TextDecoder().decode(response.body));
    }
    location.hash = '/workspace';
    await until(() => document.querySelector('.ws-workspace-name')?.textContent === 'Équipe installed validation',
      'The saved workspace did not reopen through the installed UI', 180000);
    let session = (await bridge.workspaceStatus()).active;
    if (!session) throw new Error('The installed UI has no active workspace');
    let principalId = config.principalId;
    if (config.phase === 'sign-in') {
      if (!session.me.administrator) throw new Error('The independent local owner must provision the fixture member');
      const spaces = (await request(session, 'GET', '/v1/spaces')).items;
      const person = await request(session, 'POST', '/v1/principals', { name: 'Native invited member', kind: 'human', administrator: false }, 201);
      principalId = person.id;
      await request(session, 'PUT', '/v1/spaces/' + spaces[0].id + '/grants/' + person.id, { role: 'contributor' });
      const invitation = await request(session, 'POST', '/v1/sign-in/invitations', { principal_id: person.id, purpose: 'enroll', expires_in_seconds: 3600 }, 201);
      const endpoint = session.endpoint;
      await click('Disconnect');
      await click('Join a workspace');
      await click('Use invitation');
      await input('Workspace address', endpoint);
      await input('Private invitation link or code', invitation.invitation_token);
      await click('Review invitation');
      await until(() => document.querySelector('.ws-sign-in')?.textContent.includes('Native invited member') && document.querySelector('.ws-sign-in')?.textContent.includes('contributor'), 'The invitation did not show the scoped member and role');
      await input('Login name', 'native-member');
      await input('Choose your password', 'harbour comet mitten glacier tapestry');
      await input('Confirm password', 'harbour comet mitten glacier tapestry');
      await input('Device name', 'Native personal login');
      const remember = document.querySelector('form[aria-label="Accept a workspace invitation"] input[type="checkbox"]');
      if (!remember || remember.disabled) throw new Error('The real OS credential store must support remembering this login');
      if (!remember.checked) remember.click();
      await click('Create my login and open workspace');
      await until(() => document.querySelector('.ws-workspace-name')?.textContent === 'Équipe installed validation', 'The invitation did not open the workspace');
      session = (await bridge.workspaceStatus()).active;
    }
    if (!session || session.authentication !== 'password' || !session.remembered || session.me.principal_id !== principalId || session.me.administrator || session.me.tenant_name !== 'Équipe installed validation') {
      throw new Error('The native app must retain the remembered member identity without administrator privileges');
    }
    if (config.phase === 'sign-in-resume' && session.me.tenant_id !== config.tenantId) throw new Error('The reopened login belongs to another workspace');
    const preferences = (await bridge.localStatus()).preferences;
    if (preferences.selected || !preferences.startWithApp) throw new Error('Remembering a person must start the host without selecting its owner account');
    await request(session, 'GET', '/v1/principals', undefined, 403);
    const memory = await request(session, 'GET', '/v1/memories/' + config.memoryId);
    if (memory.memory_id !== config.memoryId) throw new Error('The member lost access to the granted memory');
    const current = (await request(session, 'GET', '/v1/sign-in/sessions')).items.filter(item => item.current);
    if (current.length !== 1 || (config.phase === 'sign-in-resume' && current[0].id !== config.sessionId)) throw new Error('Restart must refresh the same device session');
    const result = { phase: config.phase, memoryId: config.memoryId, endpoint: session.endpoint,
      tenantId: session.me.tenant_id, principalId, sessionId: current[0].id,
      uiInvitationAccepted: config.phase === 'sign-in', passwordSession: true, remembered: true,
      memberMemoryAccess: true, administratorAccessDenied: true,
      sameDeviceSessionRestored: config.phase === 'sign-in-resume', ownHostReadyBeforeRefresh: config.phase === 'sign-in-resume' };
    if (config.phase === 'sign-in-resume') {
      location.hash = '/workspace/account';
      await until(() => document.querySelector('h1')?.textContent === 'Account & sessions', 'The member account page did not open');
      await click('Revoke session');
      await click('Revoke access');
      await until(() => document.querySelector('form[aria-label="Sign in to a workspace"]'), 'Revoking the current native session did not return to sign-in');
      const after = await bridge.workspaceStatus();
      if (after.active || after.bookmarks.some(item => item.principalId === principalId)) throw new Error('Revoked native access remained selected or saved');
      let staleRejected = false;
      try { await request(session, 'GET', '/v1/me'); } catch { staleRejected = true; }
      if (!staleRejected) throw new Error('A signed-out native handle remained usable');
      // The OS operator's independent key verifies server-side revocation; it
      // is never returned by the renderer bridge or written to the receipt.
      const owner = await bridge.localOpen();
      const recorded = (await request(owner, 'GET', '/v1/sign-in/sessions')).items.find(item => item.id === current[0].id);
      if (!owner.me.administrator || !recorded?.revoked_at) throw new Error('The independent owner could not confirm session revocation');
      await bridge.workspaceDisconnect();
      Object.assign(result, { uiSessionRevoked: true, staleNativeHandleRejected: true, independentOwnerKeyPreserved: true });
    }
    if (typeof window.require !== 'undefined') throw new Error('The personal-login renderer is not sandboxed');
    return result;
  })()`)
}
