import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, BookOpen, LoaderCircle, LockKeyhole, ShieldCheck, Workflow } from "lucide-react";
import { MnemionClient } from "@mnemion/client";
import BrandMark from "../components/BrandMark";
import { version } from "../../package.json";
import { nativeFetch } from "./native";
import type { Connection, WorkspaceSession, WorkspaceStatus } from "./connection-types";

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
  return {
    endpoint: session.endpoint,
    me: session.me,
    client: new MnemionClient({ baseUrl: session.endpoint, apiKey: session.sessionToken, fetch: nativeFetch }),
  };
}

export default function Connect({ onConnect, initialError }: { onConnect: (connection: Connection) => void; initialError?: unknown }) {
  const desktop = window.mnemion?.workspaceConnect ? window.mnemion : undefined;
  const [endpoint, setEndpoint] = useState(savedAddress);
  const [key, setKey] = useState("");
  const [remember, setRemember] = useState(false);
  const [status, setStatus] = useState<WorkspaceStatus>();
  const [busy, setBusy] = useState(desktop ? "Checking saved workspaces…" : "");
  const [error, setError] = useState<unknown>(initialError);
  const [forgetting, setForgetting] = useState<string>();
  const [storageIssue, setStorageIssue] = useState(false);
  const [resetConfirm, setResetConfirm] = useState(false);
  const operation = useRef(0);
  const addressInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!desktop?.workspaceStatus || !desktop.workspaceResume) return;
    const generation = ++operation.current;
    void (async () => {
      let readingSavedData = true;
      try {
        const saved = await desktop.workspaceStatus!();
        readingSavedData = false;
        if (generation !== operation.current) return;
        setStatus(saved);
        setRemember(saved.secureStorage);
        if (saved.active || saved.activeId) {
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
          <p>Connect to the workspace where your team’s memory lives.</p>
          {!!status?.bookmarks.length && (
            <section className="ws-saved-workspaces" aria-label="Saved workspaces">
              <h3>Continue in a workspace</h3>
              {[...status.bookmarks].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)).map(bookmark => (
                <div className="ws-saved-workspace" key={bookmark.id}>
                  <div><strong>{bookmark.label}</strong><span>{bookmark.principalName}</span><small>{bookmark.endpoint}</small></div>
                  <div className="ws-saved-actions">
                    <button className="ws-button ws-primary" disabled={!!busy || !status.secureStorage} onClick={() => void run("Checking your saved connection…", async () => complete(await desktop!.workspaceRestore!(bookmark.id)))} aria-label={`Open ${bookmark.label} as ${bookmark.principalName}`}><ArrowRight size={15} />Open</button>
                    <button className="ws-button ws-quiet" disabled={!!busy} onClick={() => setForgetting(bookmark.id)} aria-label={`Forget ${bookmark.label} on this device`}>Forget</button>
                  </div>
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
          <form className="ws-join-form" onSubmit={connect} aria-label="Connect a workspace">
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
          </form>
          {busy && <p className="ws-connect-progress" role="status" aria-live="polite">{busy}</p>}
          {busy === "Reconnecting to your workspace…" && <button className="ws-button ws-quiet" onClick={() => void run("Pausing reconnection…", async () => { await desktop!.workspaceDisconnect!(); requestAnimationFrame(() => addressInput.current?.focus()); })}>Use another workspace</button>}
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
