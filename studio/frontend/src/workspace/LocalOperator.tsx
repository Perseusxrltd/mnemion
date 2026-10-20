import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Bot, Copy } from 'lucide-react';
import type { LocalStatus } from '../../../shared/local-workspace';
import DesktopSourcesOverview from './DesktopSourcesOverview';
import { DesktopAgentInstallations } from './DesktopAgentSetup';

export default function LocalOperator({ status }: { status: LocalStatus }) {
  const [notice, setNotice] = useState('');
  const operator = status.operator;
  if (!operator) return <><DesktopSourcesOverview /><DesktopAgentInstallations /></>;
  const setup = {
    protocol: 'mnemion-desktop-operator-v1', scope: 'owning_os_account',
    command: operator.command,
    stdin_examples: { discover: { action: 'catalog' }, status: { action: 'status' }, connection: { action: 'workspace.status' } },
    observed_workspace_id: status.info?.settings?.workspace_id ?? null,
    instructions: 'Run the command on this computer under the app owner’s OS account. Send one JSON request on stdin. Read fresh status and the operation catalog before changes. Supply secrets on private stdin and save newly generated keys with --result-file.',
  };
  return <><DesktopSourcesOverview /><DesktopAgentInstallations /><section className="ws-device-settings ws-local-operator" aria-labelledby="local-operator-title">
    <div className="ws-memory-heading"><h2 id="local-operator-title"><Bot size={19} />Agents on this computer</h2><span className="ws-badge">{operator.state === 'ready' ? 'Ready' : operator.state === 'starting' ? 'Starting' : 'Needs attention'}</span></div>
    <p>{operator.message}</p>
    <p className="ws-helper">Let a trusted local agent connect this app to your team’s workspace, manage setup and updates, adjust RAM, and handle backups and recovery. It can work while the app is in the background. These controls use your OS account’s authority; agents using the memory API keep their workspace permissions.</p>
    <div className="ws-setup-actions"><button type="button" className="ws-button" disabled={operator.state !== 'ready'} onClick={async () => {
      try { await navigator.clipboard.writeText(JSON.stringify(setup, null, 2)); setNotice('Local agent setup copied. It contains instructions and local paths, with no credentials.'); }
      catch { setNotice('The clipboard is unavailable. Use the local operator guide below.'); }
    }}><Copy size={16} />Copy local agent setup</button></div>
    {notice && <p className="ws-notice" role="status">{notice}</p>}
    <Link className="ws-link" to="/workspace/help?doc=docs%2Fservice%2Fdesktop-operator.md">Local agent and recovery guide<ArrowRight size={13} /></Link>
  </section></>;
}
