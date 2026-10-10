import { useState } from "react";
import { Link } from "react-router-dom";
import { Check, Copy, Terminal } from "lucide-react";

const clients = [
  ["codex", "Codex"], ["claude-code", "Claude Code"],
  ["claude-desktop", "Claude Desktop"], ["cursor", "Cursor"],
  ["gemini-cli", "Gemini CLI"], ["zed", "Zed"],
  ["devin", "Devin Desktop · Cascade"], ["windsurf", "Windsurf · legacy Cascade"],
  ["generic", "Another MCP client"],
];

export function Agents({ endpoint, space }: { endpoint: string; space: string }) {
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
  </div>;
}
