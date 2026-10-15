/** Real backup/recovery acceptance, only inside the installed gate's disposable profile. */
import { dialog, type BrowserWindow } from 'electron'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { verifyNativeOperator } from './native-operator-probe.js'

export async function verifyNativeBackups(window: BrowserWindow, config: Record<string, unknown>, probePath: string): Promise<Record<string, unknown>> {
  const base = dirname(probePath), fixturePath = join(base, 'native-backup-fixture.json')
  const folder = join(base, 'Encrypted backups Équipe')
  await mkdir(folder, { recursive: true, mode: 0o700 })
  const saved = config.phase === 'backup-capture' ? null : JSON.parse(await readFile(fixturePath, 'utf8'))
  const choices = config.phase === 'backup-capture' ? [folder] : config.phase === 'backup-recover' ? [saved.snapshot.file, saved.ledger.file] : []
  const originalDialog = dialog.showOpenDialog
  // Only the OS picker is replaced. The actual form, trusted IPC, OS cipher,
  // controller, engine, encrypted files, database and model remain real.
  dialog.showOpenDialog = (async () => {
    let selected = choices.shift()
    if (!selected) throw new Error('Unexpected native recovery file selection')
    if (config.phase === 'backup-recover' && choices.length === 0) {
      const latest = JSON.parse(await readFile(join(process.env.MNEMION_STUDIO_USER_DATA!, 'mnemion-local-workspace', 'last-ledger.json'), 'utf8'))
      selected = latest.ledger.file
    }
    return { canceled: false, filePaths: [selected] }
  }) as typeof dialog.showOpenDialog
  try {
    const result = await window.webContents.executeJavaScript(`(async () => {
      const config = ${JSON.stringify(config)}, saved = ${JSON.stringify(saved)};
      const bridge = window.mnemion;
      const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
      async function until(check, message, timeout = 30000) {
        const deadline = performance.now() + timeout;
        do {
          const value = await check(); if (value) return value;
          const failure = document.querySelector('.ws-recover-workspace .ws-error[role="alert"], .ws-backup-panel .ws-error[role="alert"]');
          if (failure) throw new Error('Native recovery UI: ' + failure.textContent.slice(0, 1000));
          await pause(100);
        } while (performance.now() < deadline);
        throw new Error(message);
      }
      const button = text => [...document.querySelectorAll('button')].find(node => (node.getAttribute('aria-label') === text || node.getAttribute('title') === text || node.textContent.trim() === text) && !node.matches(':disabled') && node.getClientRects().length);
      async function click(text) { (await until(() => button(text), 'Missing recovery control: ' + text)).click(); await pause(100); }
      async function input(selector, value) {
        const field = await until(() => document.querySelector(selector), 'Missing recovery field');
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(field, value);
        field.dispatchEvent(new Event('input', { bubbles: true })); await pause(100);
      }
      async function ready() {
        await until(async () => {
          const status = await bridge.localStatus();
          if (status.state === 'error') throw new Error('Native recovery startup failed: ' + status.errorCode);
          return status.state === 'running' && document.querySelector('.ws-workspace-name')?.textContent === 'Équipe installed validation';
        }, 'The recovery workspace did not open', 600000);
        const session = (await bridge.workspaceStatus()).active;
        if (!session?.me.administrator) throw new Error('The independent local administrator did not reconnect');
        return session;
      }
      let session;
      async function request(method, path, body, expected = 200) {
        const response = await bridge.serviceRequest({ url: session.endpoint + path, method,
          headers: { Authorization: 'Bearer ' + session.sessionToken, 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
          ...(body ? { body: JSON.stringify(body) } : {}) });
        if (response.status !== expected) throw new Error('Backup acceptance request failed: ' + path + ' / ' + response.status);
        return JSON.parse(new TextDecoder().decode(response.body));
      }
      async function recoverScreen() {
        await click('Disconnect');
        await click('Recover a workspace from an encrypted backup');
        await until(() => document.querySelector('.ws-recover-workspace'), 'Recovery entry point did not open');
      }
      location.hash = '/workspace';
      session = await ready();
      if (config.phase === 'backup-capture') {
        const spaces = (await request('GET', '/v1/spaces')).items;
        const discarded = await request('POST', '/v1/spaces/' + spaces[0].id + '/memories',
          { content: 'Disposable native recovery record: this must remain deleted after restoration.', kind: 'note' }, 202);
        location.hash = '/workspace/setup';
        await until(() => document.querySelector('.ws-backup-panel'), 'Backup settings did not appear');
        await click('Choose folder');
        await click('Generate key');
        const key = document.querySelector('.ws-backup-key input[type="password"]').value;
        if (!key.startsWith('mnm_bk_') || key.length !== 50) throw new Error('A complete recovery key was not generated');
        document.querySelector('.ws-backup-key input[type="checkbox"]').click(); await pause(100);
        await click('Save backup settings');
        await until(async () => (await bridge.localBackupStatus()).configuration?.protected_key, 'The native OS store did not protect the backup key');
        await until(() => bridge.updateSafety(), 'Saving the backup form did not clear its update guard');
        await click('Back up now');
        const backed = await until(async () => {
          const view = await bridge.localBackupStatus();
          if (view.last_error) throw new Error('Native encrypted backup: ' + view.last_error.slice(0, 1000));
          return view.last_snapshot?.snapshot && view;
        }, 'The native encrypted snapshot did not finish', 180000);
        const deletion = await request('DELETE', '/v1/memories/' + discarded.memory_id + '?expected_version=1', undefined, 202);
        if (deletion.operation_id) await until(async () => {
          const operation = await request('GET', '/v1/operations/' + deletion.operation_id);
          if (operation.state === 'failed') throw new Error('The native deletion did not finish');
          return operation.state === 'ready';
        }, 'The native deletion did not finish', 120000);
        await click('Refresh ledger');
        await until(async () => (await bridge.localBackupStatus()).last_ledger?.operation_id !== backed.last_snapshot.operation_id &&
          (await bridge.localStatus()).backup?.state === 'complete', 'The current access ledger did not finish', 120000);
        const latest = await bridge.localBackupStatus();
        if (latest.snapshot_availability !== 'present' || latest.ledger_availability !== 'present') throw new Error('A verified native backup file is unavailable');
        document.querySelector('.ws-backup-panel').scrollIntoView({ block: 'start' }); await pause(100);
        return { phase: config.phase, nativeEncryptedSnapshot: true, laterDeletionLedger: true, protectedKeySaved: true,
          backupFormRestoresUpdateReadiness: true, fixture: { key, snapshot: backed.last_snapshot.snapshot, ledger: latest.last_ledger.ledger,
            discardedId: discarded.memory_id, tenantId: session.me.tenant_id, workspaceId: (await bridge.localStatus()).info.settings.workspace_id } };
      }
      if (config.phase === 'backup-recover') {
        // No supplied key: this must reopen the key stored by the previous OS process.
        await bridge.localBackupRun({ ledger_only: true });
        const policy = await bridge.localBackupStatus();
        if (!policy.configuration?.protected_key) throw new Error('The backup key was not retained across native restart');
        await recoverScreen();
        await click('Choose snapshot');
        await input('.ws-recover-workspace input[type="password"]', saved.key);
        await click('Inspect snapshot');
        await until(() => button('Choose ledger'), 'The authenticated snapshot did not advance to its ledger');
        await click('Choose ledger');
        await click('Inspect ledger');
        await until(() => document.querySelector('.ws-setup-review'), 'The ledger did not produce a recovery review');
        document.querySelector('.ws-setup-review input[type="checkbox"]').click(); await pause(100);
        await click('Create verified recovery copy');
        await until(() => button('Use this recovery copy'), 'The separate native recovery copy did not verify', 300000);
        await click('Use this recovery copy');
        session = await ready();
        const status = await bridge.localStatus();
        if (!status.preferences.recoveryRoot || status.info.settings.workspace_id === saved.workspaceId) throw new Error('Recovery reused the original host identity or location');
        if (session.me.tenant_id !== saved.tenantId) throw new Error('Recovery lost the original organization');
        await request('GET', '/v1/memories/' + config.memoryId);
        await request('GET', '/v1/memories/' + saved.discardedId, undefined, 404);
        await until(() => bridge.updateSafety(), 'Finished recovery leaves a stale update blocker');
        return { phase: config.phase, protectedKeyReopened: true, realRecoveryControls: true, separateRecoveryCopy: true,
          originalOrganizationRetained: true, retainedMemoryReadable: true, postSnapshotDeletionPreserved: true,
          freshAdministratorConnected: true, recoveryRoot: status.preferences.recoveryRoot };
      }
      const restored = await bridge.localStatus();
      if (!restored.preferences.recoveryRoot || restored.info.settings.workspace_id === saved.workspaceId) throw new Error('Restart did not reopen the selected recovery copy');
      await request('GET', '/v1/memories/' + config.memoryId);
      await request('GET', '/v1/memories/' + saved.discardedId, undefined, 404);
      await recoverScreen();
      await click('Return to the original local workspace');
      session = await ready();
      const original = await bridge.localStatus();
      if (original.preferences.recoveryRoot || original.info.settings.workspace_id !== saved.workspaceId) throw new Error('The original workspace did not remain independently accessible');
      await request('GET', '/v1/memories/' + config.memoryId);
      await request('GET', '/v1/memories/' + saved.discardedId, undefined, 404);
      return { phase: config.phase, recoveredCopyReopened: true, deletionPreservedAfterReopen: true, originalWorkspaceReopened: true };
    })()`)
    if (result.fixture) {
      await writeFile(fixturePath, JSON.stringify(result.fixture), { mode: 0o600, flag: 'wx' })
      delete result.fixture
      const policy = await readFile(join(process.env.MNEMION_STUDIO_USER_DATA!, 'mnemion-local-workspace', 'backup-policy.json'), 'utf8')
      const fixture = JSON.parse(await readFile(fixturePath, 'utf8'))
      if (policy.includes(fixture.key)) throw new Error('A native backup recovery key was saved in plaintext')
    }
    if (choices.length) throw new Error('The recovery workflow did not use its expected native file selections')
    return { ...result, ...await verifyNativeOperator(window, String(config.phase)) }
  } finally { dialog.showOpenDialog = originalDialog }
}
