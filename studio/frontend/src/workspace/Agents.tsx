import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { MnemionError } from "@mnemion/client";
import { Check, Copy, RefreshCw, Terminal } from "lucide-react";
import type { Connection } from "./connection-types";

const clients = [
  ["codex", "Codex"], ["claude-code", "Claude Code"],
  ["claude-desktop", "Claude Desktop"], ["cursor", "Cursor"],
  ["gemini-cli", "Gemini CLI"], ["zed", "Zed"],
  ["devin", "Devin Desktop · Cascade"], ["windsurf", "Windsurf · legacy Cascade"],
  ["generic", "Another MCP client"],
];

export function Agents({ connection, space }: { connection: Connection; space: string }) {
  const { endpoint } = connection;
  const authentication = useQuery({
    queryKey: ["agent-oauth-configuration"],
    queryFn: () => connection.client.oauthConfiguration(),
    staleTime: 60_000,
    retry: (count, error) => !(error instanceof MnemionError && error.status === 404) && count < 1,
  });
  const unavailable = authentication.error instanceof MnemionError && authentication.error.status === 404;
  const signIn = authentication.isError ? undefined : authentication.data;
  const [client, setClient] = useState("codex");
  const [shell, setShell] = useState(navigator.platform.startsWith("Win") ? "powershell" : "posix");
  const [credentials, setCredentials] = useState("app.mnemion-credentials.json");
  const [config, setConfig] = useState("");
  const [compatibility, setCompatibility] = useState(false);
  const [copied, setCopied] = useState("");
  const [error, setError] = useState("");
  const quote = (value: string) => shell === "powershell" ? `'${value.replaceAll("'", "''")}'` : `'${value.replaceAll("'", "'\\''")}'`;
  const command = `mnemion-agent --client ${client} --credentials ${quote(credentials)}${config.trim() ? ` --config ${quote(config)}` : ""}${compatibility ? ` --legacy-space ${space}` : ""}`;
  const template = JSON.stringify({ api_url: endpoint, api_key: "REPLACE_WITH_THIS_APPLICATIONS_KEY" }, null, 2);
  async function copy(value: string, label: string) {
    try { await navigator.clipboard.writeText(value); setCopied(label); setError(""); }
    catch { setError("Clipboard access is unavailable. Select and copy the command below."); }
  }
  const copyButton = (value: string, label: string) => <button className="ws-button" onClick={() => copy(value, label)}>{copied === label ? <Check size={15} /> : <Copy size={15} />}{copied === label ? "Copied" : label}</button>;
  return <div className="ws-page">
    <header className="ws-page-heading"><div><div className="ws-eyebrow">Assistants & applications</div><h1>Give your agents shared memory</h1><p>Each agent uses its own identity to recall permitted knowledge and save new evidence.</p></div><Terminal size={26} /></header>
    {error && <div className="ws-notice ws-error" role="alert">{error}</div>}
    <section className="ws-card ws-agent-sign-in">
      <div className="ws-section-title"><h2>Connect with your account</h2><button type="button" className="ws-button ws-quiet" disabled={authentication.isFetching} onClick={() => void authentication.refetch()} aria-label="Check agent sign-in availability"><RefreshCw size={15} />Check availability</button></div>
      {authentication.isPending && <p role="status">Checking this workspace’s sign-in options…</p>}
      {authentication.isError && <p role="status">{unavailable ? "This server needs an update to show its sign-in options here. Your host operator can check whether agent sign-in is enabled." : "Sign-in options could not be checked. Check your connection and try again."}</p>}
      {signIn?.mode === "disabled" && <p>Your host operator can enable account sign-in for this workspace at its public HTTPS address. You can also connect using a dedicated application key below.</p>}
      {signIn && signIn.mode !== "disabled" && !signIn.mcp_enabled && <p>Your host operator needs to enable this workspace’s MCP gateway before agents can connect.</p>}
      {signIn?.mcp_enabled && signIn.mode !== "disabled" && signIn.resource && <>
        <p>{signIn.mode === "personal" ? "Use your personal workspace login or a company account offered on the consent page. An agent supporting MCP OAuth opens that page for you to review and approve access." : "This workspace uses your organization’s identity provider. Your administrator must link your company account to your workspace identity."}</p>
        <label className="ws-field"><span>Workspace MCP address</span><input value={signIn.resource} readOnly onFocus={event => event.target.select()} /></label>
        {copyButton(signIn.resource, "Copy MCP address")}
        <ol className="ws-agent-steps">
          <li>Add this address to the agent’s MCP or connector settings and choose OAuth.</li>
          <li>Sign in when the agent opens the authorization page.</li>
          <li>Review the app and permissions, then approve the connection.</li>
        </ol>
        {signIn.mode === "personal" && <p>The app will use your account’s permissions, including future changes. Use a separate account when an agent needs narrower access. <Link className="ws-link" to="/workspace/account">Manage your login and connected apps</Link>.</p>}
        {signIn.mode === "external" && <p className="ws-helper">Identity provider: {signIn.issuer}. Your administrator controls its authorization and revocation policy.</p>}
      </>}
      <p><Link className="ws-link" to="/workspace/help?doc=docs%2Fservice%2Fhosted-agent-sign-in.md">Agent sign-in and host setup guide</Link></p>
      <p className="ws-helper">Agent settings and OAuth support vary by provider. Connecting MCP gives the agent tools for this workspace; conversation capture is configured separately in Connections.</p>
    </section>
    <details className="ws-agent-key-setup"><summary>Connect with a dedicated application key</summary>
    <p>Create a separately managed identity for a background agent or a client using local MCP configuration.</p>
    <section className="ws-card"><h2>1. Prepare this application’s access</h2><p>Ask your workspace administrator to create an application and key in <Link className="ws-link" to="/workspace/team">People & apps</Link>, then grant access to the spaces it needs. A reader can recall; a contributor can also save. Company source access comes from the connection’s identity mappings.</p><p>On the machine running the agent, install Mnemion into a dedicated environment. Save this template as a private credentials file and replace the placeholder with that application’s key.</p>
      <pre className="ws-code">{template}</pre>{copyButton(template, "Copy credentials template")}
      <p className="ws-helper">Keep this file out of Git and shared folders. Restrict it to your operating-system account. Rotate or revoke the key in People & apps when access changes.</p>
    </section>
    <section className="ws-card"><h2>2. Connect an MCP client</h2><div className="ws-connector-form">
      <label>Client<select value={client} onChange={event => setClient(event.target.value)}>{clients.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
      <label>Terminal<select value={shell} onChange={event => setShell(event.target.value)}><option value="posix">macOS / Linux shell</option><option value="powershell">Windows PowerShell</option></select></label>
      <label>Credentials file<input value={credentials} onChange={event => setCredentials(event.target.value)} required /></label>
      <label>{client === "generic" ? "Client configuration file" : "Custom configuration file (optional)"}<input value={config} onChange={event => setConfig(event.target.value)} placeholder="Use this operating-system profile" /></label>
      <label className="ws-checkbox"><input type="checkbox" checked={compatibility} onChange={event => setCompatibility(event.target.checked)} />Include v3 / Open Brain tools in this space</label>
    </div><p>Run the preview in the environment where Mnemion is installed. It resolves the interpreter and credentials paths for that machine.</p>
      <pre className="ws-code">{command}</pre>{copyButton(command, "Copy preview command")}
      <p>Close the client, review the preview, then apply the connection and reopen the client.</p>
      <pre className="ws-code">{command} --apply</pre>{copyButton(`${command} --apply`, "Copy setup command")}
      <p className="ws-helper">Setup backs up existing settings and changes only the Mnemion server entry. JSON files with comments require a manual merge. WSL and Windows use their own profiles; run setup on the side where the agent runs. Claude Desktop’s standard profile is available on macOS and Windows.</p>
    </section>
    <section className="ws-card"><h2>3. Check the connection</h2><p>Ask the agent to list its memory spaces, then recall a known decision. Saves need a writable space; search and context can include all accessible spaces. Source citations let you inspect the evidence behind a result.</p><pre className="ws-code">List my Mnemion spaces. Search my accessible memory for a decision about our project and show the source.</pre><p className="ws-helper">Applications can also use the Python or TypeScript SDK, HTTP API, or the optional MCP HTTP gateway. Retrieved documents and messages are evidence; they cannot grant the agent new permissions.</p></section>
    </details>
  </div>;
}
