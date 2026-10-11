// Developer diagnostic only: attach to a disposable local Electron inspector,
// read restart guards, disconnect. Never use this as a public upgrade gate.
import { createRequire } from 'node:module';
import { realpathSync, readFileSync } from 'node:fs';
import { isAbsolute, relative } from 'node:path';
import { createHash } from 'node:crypto';

if (process.argv[2] === '--prepare') {
  const binary = realpathSync(process.argv[3]);
  const parent = realpathSync(process.env.RUNNER_TEMP || '.');
  const path = relative(parent, binary);
  if (process.env.GITHUB_ACTIONS !== 'true' || process.env.RUNNER_ENVIRONMENT !== 'github-hosted'
      || process.platform !== 'linux' || !path || path.startsWith('..') || isAbsolute(path)) {
    throw new Error('Only a disposable Linux runner copy may enable its inspector');
  }
  const require = createRequire(new URL('../studio/electron/package.json', import.meta.url));
  const { flipFuses, getCurrentFuseWire, FuseVersion, FuseV1Options } = require('@electron/fuses');
  const digest = () => createHash('sha256').update(readFileSync(binary)).digest('hex');
  const beforeHash = digest();
  const before = await getCurrentFuseWire(binary);
  await flipFuses(binary, { version: FuseVersion.V1, [FuseV1Options.EnableNodeCliInspectArguments]: true });
  const after = await getCurrentFuseWire(binary);
  for (const key of Object.keys(before)) {
    if (key !== String(FuseV1Options.EnableNodeCliInspectArguments) && before[key] !== after[key]) {
      throw new Error('The diagnostic changed an unrelated runtime fuse');
    }
  }
  if (after[FuseV1Options.EnableNodeCliInspectArguments] !== 49) throw new Error('Inspector fuse was not enabled');
  console.log(JSON.stringify({ developer_diagnostic_only: true, public_upgrade_gate: false,
    modified_fuse: 'EnableNodeCliInspectArguments', original_binary_sha256: beforeHash, diagnostic_binary_sha256: digest() }));
  process.exit(0);
}

const endpoint = new URL(process.argv[2]);
if (endpoint.protocol !== 'ws:' || endpoint.hostname !== '127.0.0.1' || !endpoint.port ||
    endpoint.username || endpoint.password || endpoint.search || endpoint.hash) {
  throw new Error('Expected a local disposable inspector');
}
const expression = `(async () => {
  const { app, BrowserWindow, powerMonitor } = process.getBuiltinModule('module').createRequire(process.execPath)('electron');
  const windows = BrowserWindow.getAllWindows().filter(window => !window.isDestroyed());
  return {
    version: app.getVersion(), electron: process.versions.electron,
    idleSeconds: powerMonitor.getSystemIdleTime(),
    idleState: powerMonitor.getSystemIdleState(600),
    windows: await Promise.all(windows.map(async window => ({
      focused: window.isFocused(), visible: window.isVisible(), minimized: window.isMinimized(),
      loading: window.webContents.isLoading(), crashed: window.webContents.isCrashed(),
      renderer: await Promise.race([
        window.webContents.executeJavaScript('({ bridge: !!window.mnemion, safe: window.mnemion?.updateSafety?.() === true, ready: document.readyState })')
          .catch(() => ({ error: 'renderer_check_failed' })),
        new Promise(resolve => setTimeout(() => resolve({ error: 'renderer_check_timed_out' }), 3000))
      ])
    })))
  };
})()`;

const socket = new WebSocket(endpoint);
const result = await new Promise((resolve, reject) => {
  const timer = setTimeout(() => { socket.close(); reject(new Error('Inspector check timed out')); }, 7000);
  socket.addEventListener('error', () => { clearTimeout(timer); reject(new Error('Local inspector unavailable')); });
  socket.addEventListener('open', () => socket.send(JSON.stringify({ id: 1, method: 'Runtime.evaluate',
    params: { expression, awaitPromise: true, returnByValue: true } })));
  socket.addEventListener('message', event => {
    if (typeof event.data !== 'string' || event.data.length > 65536) {
      clearTimeout(timer); socket.close(); reject(new Error('Invalid inspector response')); return;
    }
    const value = JSON.parse(event.data);
    if (value.id !== 1) return;
    clearTimeout(timer); socket.close();
    if (value.error || value.result?.exceptionDetails || !value.result?.result?.value) {
      reject(new Error('The installed runtime could not report its restart guards')); return;
    }
    resolve(value.result.result.value);
  });
});
console.log(JSON.stringify(result));
