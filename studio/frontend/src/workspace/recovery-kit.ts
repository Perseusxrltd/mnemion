import type { RecoveryDirectoryRecord } from '@mnemion/client';
import { recoveryRecord } from '../../../electron/workspace-recovery';
import template from '../../../../mnemion/service/recovery_kit.html?raw';

const base64 = (bytes: Uint8Array) => btoa(String.fromCharCode(...bytes));

/** Never send this passphrase or a workspace credential to a server. */
export async function exportRecoveryKit(record: RecoveryDirectoryRecord, passphrase: string, endpoint: string, name: string): Promise<void> {
  const directory = recoveryRecord(record);
  if ([...passphrase].length < 15 || new TextEncoder().encode(passphrase).length > 4096 || passphrase.includes('\0')) throw new Error('Use a separate kit passphrase of at least 15 characters.');
  if (!globalThis.crypto?.subtle) throw new Error('Use the desktop app or the workspace’s HTTPS address to encrypt a recovery kit.');
  const address = new URL(endpoint);
  if ((address.protocol !== 'https:' && !(address.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(address.hostname))) || address.username || address.password || address.search || address.hash || /[\s\\]/.test(endpoint) || endpoint.length > 4096) throw new Error('Use the verified workspace address.');
  if (!name.trim() || [...name].length > 256 || /[\u0000-\u001f\u007f]/.test(name)) throw new Error('Use the verified workspace name.');
  const clear = new TextEncoder().encode(JSON.stringify({format:'mnemion-recovery-kit-v1',workspace_name:name,endpoint,captured_at:new Date().toISOString(),record:directory}));
  if (clear.length > 16384) throw new Error('The recovery kit exceeds its metadata limit.');
  const password = new TextEncoder().encode(passphrase), salt = crypto.getRandomValues(new Uint8Array(32)), iv = crypto.getRandomValues(new Uint8Array(12));
  const material = await crypto.subtle.importKey('raw', password, 'PBKDF2', false, ['deriveKey']); password.fill(0);
  const key = await crypto.subtle.deriveKey({name:'PBKDF2',hash:'SHA-256',salt,iterations:600000}, material, {name:'AES-GCM',length:256}, false, ['encrypt']);
  let encrypted: ArrayBuffer;
  try { encrypted = await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:new TextEncoder().encode('mnemion-recovery-kit-v1')},key,clear); }
  finally { clear.fill(0); }
  const envelope = {format:1,algorithm:'AES-256-GCM',kdf:'PBKDF2-SHA256',iterations:600000,salt:base64(salt),iv:base64(iv),ciphertext:base64(new Uint8Array(encrypted))};
  let html = template.replace(/\r\n?/g, '\n');
  if (html.split('__MNEMION_RECOVERY_DATA__').length !== 2 || html.split('__MNEMION_SCRIPT_HASH__').length !== 2) throw new Error('The installed recovery viewer is incomplete.');
  html = html.replace('__MNEMION_RECOVERY_DATA__', JSON.stringify(envelope));
  const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  if (!script) throw new Error('The installed recovery viewer is incomplete.');
  html = html.replace('__MNEMION_SCRIPT_HASH__', base64(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(script)))));
  const url = URL.createObjectURL(new Blob([html], {type:'text/html;charset=utf-8'}));
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'mnemion-recovery-kit.html'; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
