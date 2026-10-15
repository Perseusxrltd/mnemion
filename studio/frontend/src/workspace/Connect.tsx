import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, BookOpen, Database, Globe, LoaderCircle, LockKeyhole, ShieldCheck, Workflow } from "lucide-react";
import { MnemionClient } from "@mnemion/client";
import BrandMark from "../components/BrandMark";
import { version } from "../../package.json";
import { nativeFetch } from "./native";
import type { Connection, WorkspaceSession, WorkspaceStatus } from "./connection-types";
import type { LocalStatus } from '../../../shared/local-workspace';
import LocalSetup from './LocalSetup';
import RecoverWorkspace from './RecoverWorkspace';
import WorkspaceRecovery from './WorkspaceRecovery';
import SignInForm from './SignInForm';
import { browserBookmarks, initialJoinLink, type JoinLink } from './sign-in';

function errorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : "The connection could not be completed.";
  return message.replace(/^Error invoking remote method '[^']+': (?:Error: )?/, "");
}

function savedAddress(): string {
  try {
    const value = localStorage.getItem("mnemion_service_url");
    if (value) return value;
  } catch { /* Restricted browser storage does not prevent a connection. */ }
  return location.protocol === "file:" ? "http://127.0.0.1:7892" : location.origin;
}

function rememberAddress(address: string): void {
  try { localStorage.setItem("mnemion_service_url", address); } catch { /* Optional convenience only. */ }
}

function nativeConnection(session: WorkspaceSession): Connection {
  let closed = false;
  let unsubscribe: (() => void) | undefined;
  const listeners = new Set<() => void>();
  const listen = () => {
    unsubscribe ??= window.mnemion?.onWorkspaceClosed?.(token => {
      if (token !== session.sessionToken || closed) return;
      closed = true;
      for (const listener of listeners) listener();
    });
  };
  listen();
  return {
    endpoint: session.endpoint,
    me: session.me,
    authentication: session.authentication,
    ...(session.remembered && session.me.administrator && window.mnemion?.workspaceRecoveryRefresh ? {
      refreshRecovery: () => window.mnemion!.workspaceRecoveryRefresh!(session.sessionToken),
    } : {}),
    client: new MnemionClient({ baseUrl: session.endpoint, apiKey: session.sessionToken, fetch: nativeFetch }),
    subscribeClosed: listener => {
      listen(); listeners.add(listener);
      if (closed) queueMicrotask(() => { if (listeners.has(listener)) listener(); });
      return () => { listeners.delete(listener); };
    },
    close: () => { unsubscribe?.(); unsubscribe = undefined; listeners.clear(); },
  };
}

export default function Connect({ onConnect, initialError, initialJoin }: { onConnect: (connection: Connection) => void; initialError?: unknown; initialJoin?: JoinLink | null }) {
  const desktop = window.mnemion?.workspaceConnect ? window.mnemion : undefined;
  const [incoming] = useState(() => initialJoinLink() ?? initialJoin ?? null);
  const [joinMethod, setJoinMethod] = useState<'key' | 'password' | 'invitation'>(() => incoming?.invitation ? 'invitation' : incoming?.workspaceId || (!desktop && browserBookmarks().length) ? 'password' : 'key');
  const [endpoint, setEndpoint] = useState(() => incoming?.endpoint ?? savedAddress());
  const [key, setKey] = useState("");
  const [remember, setRemember] = useState(false);
  const [status, setStatus] = useState<WorkspaceStatus>();
  const [busy, setBusy] = useState(desktop ? "Checking saved workspaces…" : "");
  const [error, setError] = useState<unknown>(initialError);
  const [forgetting, setForgetting] = useState<string>();
  const [inspecting, setInspecting] = useState<string>();
  const [storageIssue, setStorageIssue] = useState(false);
  const [resetConfirm, setResetConfirm] = useState(false);
  const [selection, setSelection] = useState<'join' | 'local' | 'recover' | null>(incoming ? 'join' : desktop?.localStatus ? null : 'join');
  const [local, setLocal] = useState<LocalStatus>();
  const [continueLocal, setContinueLocal] = useState(false);
  const operation = useRef(0);
  const addressInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!desktop?.workspaceStatus || !desktop.workspaceResume) return;
    const generation = ++operation.current;
    void (async () => {
      let readingSavedData = true;
      try {
        const [savedResult, localResult] = await Promise.allSettled([
          desktop.workspaceStatus!(), desktop.localStatus?.(),
        ]);
        if (generation !== operation.current) return;
        if (localResult.status === 'fulfilled' && localResult.value) {
          setLocal(localResult.value);
          if (localResult.value.preferences?.selected && localResult.value.available && !initialError && !incoming) {
            setContinueLocal(true); setSelection('local');
            if (savedResult.status === 'fulfilled') setStatus(savedResult.value);
            return;
          }
        }
        if (savedResult.status === 'rejected') throw savedResult.reason;
        const saved = savedResult.value;
        readingSavedData = false;
        if (generation !== operation.current) return;
        setStatus(saved);
        setRemember(saved.secureStorage);
        if (saved.activeId && !initialError) setSelection('join');
        if ((saved.active || (saved.activeId && saved.secureStorage)) && !initialError && !incoming) {
          setSelection('join');
          setBusy("Reconnecting to your workspace…");
          const session = await desktop.workspaceResume!();
          if (session && generation === operation.current) onConnect(nativeConnection(session));
        }
      } catch (error) {
        if (generation === operation.current) {
          setError(error);
          if (readingSavedData) setStorageIssue(true);
        }
      } finally {
        if (generation === operation.current) setBusy("");
      }
    })();
    return () => { ++operation.current; };
  }, [desktop, onConnect]);

  async function run(label: string, action: () => Promise<void>) {
    const generation = ++operation.current;
    setBusy(label);
    setError(undefined);
    try { await action(); } catch (error) {
      if (generation === operation.current) setError(error);
    } finally {
      if (generation === operation.current) setBusy("");
    }
  }

  function complete(session: WorkspaceSession) {
    setKey("");
    rememberAddress(session.endpoint);
    onConnect(nativeConnection(session));
  }

  async function connect(event: FormEvent) {
    event.preventDefault();
    await run("Checking your workspace and access…", async () => {
      let url: URL;
      try { url = new URL(endpoint.trim()); } catch { throw new Error("Enter a valid workspace address."); }
      if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
        throw new Error("Enter the workspace address without credentials or query parameters.");
      }
      if (url.protocol !== "https:" && !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) {
        throw new Error("Use HTTPS for a remote workspace so your key is protected in transit.");
      }
      const address = url.href.replace(/\/+$/, "").replace(/\/(?:v1|mcp)$/, "");
      if (desktop?.workspaceConnect) {
        complete(await desktop.workspaceConnect({ endpoint: address, credential: key.trim(), remember: remember && !!status?.secureStorage }));
        return;
      }
      const client = new MnemionClient({ baseUrl: address, apiKey: key.trim(), fetch: nativeFetch });
      const me = await client.me();
      setKey("");
      rememberAddress(address);
      onConnect({ client, me, endpoint: address });
    });
  }

  return (
    <div className="ws-connect">
      <div className="ws-connect-story">
        <Link to="/workspace" className="ws-brand"><BrandMark />mnemion<span>studio</span></Link>
        <div className="ws-connect-intro">
          <p className="ws-eyebrow">Memory that travels with your work</p>
          <h1>One shared memory.<br /><span>Every app, on the same page.</span></h1>
          <p>Keep decisions, context, and evidence connected across your team’s assistants and systems.</p>
          <div className="ws-story-features">
            <span><ShieldCheck size={18} /> Explicit access for every space</span>
            <span><BookOpen size={18} /> Sources and revision history</span>
            <span><Workflow size={18} /> Visualize your memory in Obsidian</span>
          </div>
        </div>
        <div className="ws-connect-footer">
          <small>Free forever · Mnemion {version}</small>
          <a href="https://www.perseusxr.com/mnemion" target="_blank" rel="noreferrer">By Perseus XR ↗</a>
        </div>
      </div>
      <div className="ws-connect-panel">
        <div className="ws-connect-form">
          <p className="ws-eyebrow">Your workspace</p>
          <h2>Welcome to Mnemion</h2>
          <p>{selection === 'local' ? 'Set up once. Keep every assistant connected.' : 'Create a private workspace, or connect to your team’s shared memory.'}</p>
          {selection === null && <div className="ws-setup-choices">
            {!!error && <div className="ws-notice ws-error" role="alert">{errorMessage(error)}</div>}
            <button className="ws-setup-choice" disabled={!!busy || !local?.available} onClick={() => { setContinueLocal(false); setSelection('local'); }}><Database size={23} /><span><strong>{local?.info?.configured ? 'Open my local workspace' : 'Create on this computer'}</strong><small>Private storage, a local model, and automatic resource management.</small></span><ArrowRight size={18} /></button>
            <button className="ws-setup-choice" disabled={!!busy} onClick={() => setSelection('join')}><Globe size={23} /><span><strong>Join a workspace</strong><small>Use a workspace hosted by your team or on another computer.</small></span><ArrowRight size={18} /></button>
            {local && !local.available && <small>This installation does not include the local engine. You can join an existing workspace.</small>}
          </div>}
          {selection === 'local' && <LocalSetup initial={local} autoContinue={continueLocal} onOpen={complete} onBack={() => { setContinueLocal(false); setSelection(null); }} />}
          {selection === 'recover' && <RecoverWorkspace onBack={() => setSelection(null)} onUse={value => { setLocal(value); setContinueLocal(true); setSelection('local'); }} />}
          {selection === null && desktop?.localBackupRestore && <button className="ws-button ws-recovery-choice" type="button" disabled={!!busy} onClick={() => setSelection('recover')}>Recover a workspace from an encrypted backup</button>}
          {selection !== 'local' && selection !== 'recover' && <>
          {desktop && status && !status.secureStorage && (selection === 'join' || status.bookmarks.length > 0) && <div className="ws-notice" role="status">
            <p>Unlock your operating system’s secure store to reopen saved connections. Approve any secure-store prompt, then retry. You can also connect for this session without saving a key.</p>
            <button type="button" className="ws-button ws-quiet" disabled={!!busy} onClick={() => void run("Checking secure storage…", async () => {
              const saved = await desktop.workspaceStatus!();
              setStatus(saved); setRemember(saved.secureStorage);
            })}>Retry secure storage</button>
          </div>}
          {!!status?.bookmarks.length && (
            <section className="ws-saved-workspaces" aria-label="Saved workspaces">
              <h3>Continue in a workspace</h3>
              {[...status.bookmarks].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)).map(bookmark => (
                <div className="ws-saved-workspace" key={bookmark.id}>
                  <div><strong>{bookmark.label}</strong><span>{bookmark.principalName}</span><small>{bookmark.endpoint}</small></div>
                  <div className="ws-saved-actions">
                    <button className="ws-button ws-primary" disabled={!!busy || !status.secureStorage} onClick={() => void run("Checking your saved connection…", async () => complete(await desktop!.workspaceRestore!(bookmark.id)))} aria-label={`Open ${bookmark.label} as ${bookmark.principalName}`}><ArrowRight size={15} />Open</button>
                    <button type="button" className="ws-button ws-quiet" aria-expanded={inspecting === bookmark.id} aria-controls={`recovery-${bookmark.id}`} onClick={() => setInspecting(inspecting === bookmark.id ? undefined : bookmark.id)}>Details & recovery</button>
                    <button className="ws-button ws-quiet" disabled={!!busy} onClick={() => setForgetting(bookmark.id)} aria-label={`Forget ${bookmark.label} on this device`}>Forget</button>
                  </div>
                  {inspecting === bookmark.id && <div className="ws-recovery-container" id={`recovery-${bookmark.id}`}><WorkspaceRecovery bookmark={bookmark} busy={!!busy} onReconnect={() => void run("Checking your saved connection…", async () => complete(await desktop!.workspaceRestore!(bookmark.id)))} onNewConnection={() => {
                    setEndpoint(bookmark.endpoint); setKey(''); setSelection('join'); setError(undefined);
                    requestAnimationFrame(() => { addressInput.current?.scrollIntoView({ block: 'center' }); addressInput.current?.focus({ preventScroll: true }); });
                  }} /></div>}
                  {forgetting === bookmark.id && (
                    <div className="ws-forget-confirm" role="group" aria-label="Confirm forgetting this connection">
                      <p>Remove this saved connection from this device? You’ll need a current key to connect again. Your workspace and memories stay available.</p>
                      <button className="ws-button" disabled={!!busy} onClick={() => void run("Removing saved connection…", async () => {
                        await desktop!.workspaceForget!(bookmark.id);
                        setForgetting(undefined);
                        setStatus(await desktop!.workspaceStatus!());
                      })}>Forget connection</button>
                      <button className="ws-button ws-quiet" disabled={!!busy} onClick={() => setForgetting(undefined)}>Keep it</button>
                    </div>
                  )}
                </div>
              ))}
            </section>
          )}
          {selection === 'join' && <div className="ws-saved-actions" role="group" aria-label="Choose how to join">
            <button type="button" className={`ws-button ${joinMethod === 'password' ? 'ws-primary' : 'ws-quiet'}`} disabled={!!busy} onClick={() => setJoinMethod('password')}>Sign in</button>
            <button type="button" className={`ws-button ${joinMethod === 'invitation' ? 'ws-primary' : 'ws-quiet'}`} disabled={!!busy} onClick={() => setJoinMethod('invitation')}>Use invitation</button>
            <button type="button" className={`ws-button ${joinMethod === 'key' ? 'ws-primary' : 'ws-quiet'}`} disabled={!!busy} onClick={() => setJoinMethod('key')}>Workspace key</button>
          </div>}
          {selection === 'join' && joinMethod !== 'key' && <SignInForm key={joinMethod} method={joinMethod} incoming={incoming} initialEndpoint={endpoint} initialError={error} secureStorage={!!status?.secureStorage} busy={!!busy} onBusy={setBusy} onConnect={onConnect} onNativeConnect={complete} />}
          {selection === 'join' && joinMethod === 'key' && <form className="ws-join-form" onSubmit={connect} aria-label="Connect a workspace">
            {desktop?.localStatus && <button type="button" className="ws-button ws-quiet" disabled={!!busy} onClick={() => setSelection(null)}>Choose another setup</button>}
            {!!status?.bookmarks.length && <h3>Join another workspace</h3>}
            <p>Use the address and key supplied by your workspace administrator.</p>
            <label className="ws-field"><span>Workspace address</span><input ref={addressInput} type="url" value={endpoint} onChange={event => setEndpoint(event.target.value)} required disabled={!!busy} placeholder="https://memory.example.com" autoComplete="url" /></label>
            <small>You can also paste the API address ending in /v1 or MCP address ending in /mcp.</small>
            <label className="ws-field"><span>Workspace key</span><input type="password" value={key} onChange={event => setKey(event.target.value)} required disabled={!!busy} placeholder="mnm_…" autoComplete="off" spellCheck={false} /></label>
            {desktop && (
              <>
                <label className="ws-checkbox"><input type="checkbox" checked={remember} onChange={event => setRemember(event.target.checked)} disabled={!!busy || !status?.secureStorage} />Remember this workspace on this device</label>
                <small className="ws-secure-note"><LockKeyhole size={15} aria-hidden="true" />{status?.secureStorage ? "Saved keys are encrypted with your operating system’s secure store. Mnemion reconnects after restart; Disconnect pauses reconnection." : "Your operating system’s secure store is locked or unavailable. You can connect for this session without saving your key."}</small>
              </>
            )}
            {!!error && <div className="ws-notice ws-error" role="alert">{errorMessage(error)}</div>}
            {storageIssue && desktop?.workspaceReset && <div className="ws-notice">
              {resetConfirm ? <>
                <p>Forget all saved connections on this device and reset their settings? Your workspaces and memories remain on their servers. You’ll need current keys to reconnect.</p>
                <button type="button" className="ws-button" disabled={!!busy} onClick={() => void run("Resetting saved connections…", async () => {
                  await desktop.workspaceReset!();
                  const saved = await desktop.workspaceStatus!();
                  setStatus(saved); setRemember(saved.secureStorage);
                  setStorageIssue(false); setResetConfirm(false);
                })}>Forget all and reset</button>
                <button type="button" className="ws-button ws-quiet" disabled={!!busy} onClick={() => setResetConfirm(false)}>Cancel</button>
              </> : <button type="button" className="ws-button ws-quiet" disabled={!!busy} onClick={() => setResetConfirm(true)}>Reset saved connections</button>}
            </div>}
            <button className="ws-button ws-primary" disabled={!!busy || !key.trim()}>{busy ? <LoaderCircle size={17} className="ws-spin" /> : <ArrowRight size={17} />}{busy || "Open workspace"}</button>
            {!desktop && <small>Your key stays in this window’s memory. Disconnecting or reloading clears it.</small>}
          </form>}
          {busy && <p className="ws-connect-progress" role="status" aria-live="polite">{busy}</p>}
          {busy === "Reconnecting to your workspace…" && <button className="ws-button ws-quiet" onClick={() => void run("Pausing reconnection…", async () => { await desktop!.workspaceDisconnect!(); requestAnimationFrame(() => addressInput.current?.focus()); })}>Use another workspace</button>}
          </>}
          <Link className="ws-link" to="/help">Setup guides, documentation & roadmap</Link>
          <Link className="ws-link" to="/help?doc=docs%2Fservice%2Fconnection-diagnostics.md">Workspace offline? Connection & recovery guide</Link>
          <Link className="ws-link" to="/help?doc=docs%2Fservice%2Fprivacy.md">Privacy & data handling</Link>
          {window.mnemion?.platform && <small>Background mode, login startup and supported automatic updates are enabled by default. Change them in <strong>Background and updates</strong> in the app menu.</small>}
        </div>
        {import.meta.env.DEV && <Link className="ws-link ws-legacy-link" to="/dashboard">Open the legacy local vault</Link>}
      </div>
    </div>
  );
}
