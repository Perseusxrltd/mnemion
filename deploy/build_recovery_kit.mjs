/** One independent viewer for browser downloads and the installed Python CLI. */
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const { recoveryRecord } = await import(pathToFileURL(resolve(root, 'studio/electron/dist/workspace-recovery.js')).href);
const template = readFileSync(resolve(root, 'studio/shared/recovery-kit.html'), 'utf8').replace(/\r\n?/g, '\n');
const mark = readFileSync(resolve(root, 'studio/branding/mnemion.svg'), 'utf8').trim();
const result = template.replace('__MNEMION_RECOVERY_MARK__', mark).replace('__MNEMION_RECOVERY_VALIDATOR__', recoveryRecord.toString()).replace(/\r\n?/g, '\n');
const output = resolve(root, 'mnemion/service/recovery_kit.html');
if (process.argv.includes('--check')) {
  if (readFileSync(output, 'utf8').replace(/\r\n?/g, '\n') !== result) throw new Error('Rebuild the recovery viewer with node deploy/build_recovery_kit.mjs after the desktop build.');
} else writeFileSync(output, result);
