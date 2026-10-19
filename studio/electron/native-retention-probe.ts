/** Actual forms, private agent transport and encrypted files in a disposable gate profile. */
import type { BrowserWindow } from 'electron'
import { readFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { callNativeOperator as agent } from './native-operator-probe.js'
import type { BackupInventory } from '../shared/local-workspace.js'

export async function verifyNativeRetention(window: BrowserWindow): Promise<Record<string, boolean>> {
  const workspace = (await agent('status')).info.settings.workspace_id
  const current = (await agent('backup.status')).configuration
  await agent('backup.configure', { expected_revision: current.revision, destination: current.destination,
    enabled: current.enabled, snapshot_hours: current.snapshot_hours, ledger_minutes: current.ledger_minutes,
    key_saved: true, retention: { mode: 'keep_all', snapshots: 2, ledgers: 2 } }, workspace)
  // Three new captures also exercise an upgraded profile whose older files
  // predate the private ownership catalog and must never be adopted implicitly.
  for (let index = 0; index < 3; index++) await agent('backup.run', {}, workspace)
  const all = await agent('backup.inventory', {}, workspace) as BackupInventory
  if (all.state !== 'keep_all' || all.tracked_snapshots < 3 || all.candidate_files !== 0) throw new Error('Native keep-all retention did not preserve its recorded copies.')
  await window.webContents.executeJavaScript(`(async()=>{
    const bridge=window.mnemion;
    const pause=ms=>new Promise(r=>setTimeout(r,ms));
    async function until(check,message,timeout=180000){
      const end=Date.now()+timeout;
      do{const value=await check();if(value)return value;
        const error=document.querySelector('.ws-backup-panel .ws-error[role="alert"]');
        if(error)throw new Error('Native retention UI: '+error.textContent.slice(0,1000));
        await pause(100);
      }while(Date.now()<end);throw new Error(message);
    }
    const panel=()=>document.querySelector('.ws-setup-page .ws-backup-panel');
    const button=text=>[...(panel()?.querySelectorAll('button')??[])].find(node=>node.textContent.trim()===text);
    async function click(text){(await until(()=>{const node=button(text);return node&&!node.disabled&&node;},'Missing retention button: '+text)).click();await pause(100);}
    async function field(labelText,value,kind='input'){
      const field=await until(()=>{
        const node=[...(panel()?.querySelectorAll('label')??[])].find(node=>node.querySelector('span')?.textContent===labelText)?.querySelector(kind);
        return node?.isConnected&&!node.disabled&&node;
      },'Retention field did not become editable: '+labelText);
      Object.getOwnPropertyDescriptor(kind==='select'?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(field,value);
      field.dispatchEvent(new Event(kind==='select'?'change':'input',{bubbles:true}));await pause(100);
    }
    location.hash='/workspace/setup';
    await until(()=>panel()?.querySelector('.ws-backup-inventory'),'Backup inventory did not appear');
    // Workspace selection and backup completion each notify the renderer.
    // Let the new route hydrate its saved form before sending user input, and
    // never send synthetic changes to controls disabled by a pending refresh.
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    await field('Backup retention','limited','select');
    await field('Full snapshots to keep','2');await field('Recent access ledgers to keep','2');
    if(bridge.updateSafety())throw new Error('Unsaved retention settings did not protect the form.');
    await click('Save backup settings');
    await until(async()=>{const policy=(await bridge.localBackupStatus()).configuration?.retention;return policy?.mode==='limited'&&policy.snapshots===2&&policy.ledgers===2&&bridge.updateSafety();},'The retention policy did not save');
    await click('Review stored copies');
    await until(()=>document.querySelector('.ws-backup-cleanup input'),'The inventory did not offer its older copies');
    if(!button('Clean up reviewed copies')?.disabled)throw new Error('Native cleanup did not require confirmation.');
    document.querySelector('.ws-backup-cleanup input').click();await pause(100);
    if(bridge.updateSafety())throw new Error('Pending cleanup confirmation did not protect the form.');
    await click('Clean up reviewed copies');
    await until(async()=>{const view=await bridge.localBackupStatus();return view.last_retention?.state==='complete'&&view.last_retention.deleted_files>=2&&bridge.updateSafety();},'The reviewed cleanup did not complete');
    await click('Review stored copies');
    await until(()=>document.querySelectorAll('.ws-backup-table tbody tr').length>=4,'The retained recovery points did not appear');
    document.querySelector('.ws-backup-inventory').scrollIntoView({block:'center'});
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  })()`)
  const kept = await agent('backup.inventory', {}, workspace) as BackupInventory
  if (kept.tracked_snapshots !== 2 || kept.tracked_ledgers < 2 || kept.candidate_files !== 0) throw new Error('Native cleanup did not retain its configured recovery points.')
  const fixture = JSON.parse(await readFile(join(dirname(process.env.MNEMION_STUDIO_USER_DATA!), 'native-backup-fixture.json'), 'utf8'))
  for (const file of kept.recent) {
    const verified = await agent('backup.inspect', { source: join(kept.folder, file.name), recovery_key: fixture.key }, workspace)
    if (!verified.authenticated || (file.kind === 'snapshot' && !verified.archive_verified)) throw new Error('A retained recovery file did not authenticate after cleanup.')
  }
  const configuration = (await agent('backup.status')).configuration
  const noWork = await agent('backup.prune', { expected_revision: configuration.revision, plan_token: kept.plan_token, confirm: true }, workspace)
  if (noWork.deleted_files !== 0 || noWork.state !== 'complete') throw new Error('Agent cleanup repeated completed removals.')
  return { nativeBackupRetention: true, retentionKeepsVerifiedPairs: true, retentionControlsAndAgentAgree: true }
}
