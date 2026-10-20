import { createElement, isValidElement, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowLeft, ExternalLink, Search } from "lucide-react";
import BrandMark from "../components/BrandMark";
import { version } from "../../package.json";
import "./documentation.css";

// Repository Markdown is the single source. Vite ships each document as a lazy,
// local asset, including in Electron; reading help never needs a server or key.
const sources = import.meta.glob<string>([
  "../../../../docs/**/*.md", "../../../../README.md",
  "../../../../SECURITY.md", "../../../../CONTRIBUTING.md", "../../../README.md",
], { query: "?raw", import: "default" });
const titles: Record<string, string> = {
  "README.md": "Mnemion overview", "SECURITY.md": "Security policy",
  "CONTRIBUTING.md": "Contributing", "studio/README.md": "Desktop setup & builds",
  "docs/ROADMAP.md": "Product roadmap", "docs/service/README.md": "Quick start & API",
  "docs/RELEASE_STATUS.md": "Published release & validation status",
  "docs/PRODUCT_REQUIREMENTS.md": "Complete requirements & implementation checklist",
  "docs/research/2026-10-11-agent-platforms.md": "Dot, Grokbot, Claude, Hermes & OpenClaw",
  "docs/service/deployment.md": "Self-hosted deployment", "docs/service/organizations.md": "Organizations, spaces & security",
  "docs/service/supervision.md": "Background service without systemd",
  "docs/service/host-recovery.md": "Rebuild a host and keep workspace identities",
  "docs/service/git-journal.md": "Git journals, publication & memory replay",
  "docs/service/legacy-buffer.md": "Recover records from an older agent buffer",
  "docs/service/journal-recovery.md": "Restore editable memories from a native journal",
  "docs/implementation/github-issues.md": "GitHub fixes & remaining issue work",
  "docs/service/managed-updates.md": "Managed server updates",
  "docs/service/workspaces.md": "Connect & remember workspaces",
  "docs/service/sign-in.md": "Individual sign-in, invitations & sessions",
  "docs/service/company-sign-in.md": "Company accounts & identity-provider setup",
  "docs/service/secrets-vault.md": "Encrypted credentials, grants & key recovery",
  "docs/service/keepass.md": "KeePass import, export & private field mapping",
  "docs/service/oauth.md": "Organization OAuth & agent access",
  "docs/service/hosted-agent-sign-in.md": "Connect agents with personal or company accounts",
  "docs/service/remote-access.md": "Share a workspace with people & agents",
  "docs/service/connection-diagnostics.md": "Connection diagnosis & host recovery",
  "docs/service/memory-map.md": "Live 3D memory map",
  "docs/service/retrieval.md": "Search ranking, passages & source evidence",
  "docs/service/memory-resources.md": "RAM budgets & local agent controls",
  "docs/implementation/app-onboarding.md": "Complete app setup requirements",
  "docs/service/desktop-sources.md": "Folder and conversation setup on this computer",
  "docs/STUDIO_DESIGN.md": "Studio design system",
  "docs/BRANDING.md": "Logo & brand assets",
  "docs/service/connectors.md": "Cloud, Git & messaging sources", "docs/service/agents.md": "Agents, apps & MCP",
  "docs/service/agent-control.md": "Agent administration & CLI",
  "docs/service/capture.md": "Conversation capture", "docs/service/insights.md": "Insights & evaluations",
  "docs/service/knowledge.md": "Wiki, graph & curation", "docs/service/migration.md": "Migration from v3",
  "docs/service/recovery.md": "Backup & recovery", "docs/service/updates.md": "Background operation & updates",
  "docs/MAINTENANCE.md": "Release & documentation maintenance",
  "docs/SUPPORT.md": "Free forever & optional support",
  "docs/CODE_SIGNING.md": "Code signing policy", "docs/service/privacy.md": "Privacy & data handling",
  "docs/service/embeddings.md": "Embedding models, reindexing & resources",
  "docs/service/librarian.md": "Librarian models, schedules & review",
};
const documents = Object.entries(sources).map(([key, load]) => {
  const path = key.startsWith("../../../../") ? key.slice(12) : `studio/${key.slice(9)}`;
  const category = path.includes("/legacy/") ? "Archive" : path.includes("/research/") ? "Research"
    : path.includes("/implementation/") ? "Engineering" : path.includes("/validation/") ? "Validation"
    : path.includes("/releases/") ? "Release notes" : path.includes("/service/") ? "Guides" : "Product";
  return { path, load, category, title: titles[path] ?? path.split("/").at(-1)!.replace(/\.md$/, "").replaceAll(/[_-]/g, " ") };
}).sort((a, b) => {
  const order = ["Guides", "Product", "Release notes", "Validation", "Engineering", "Research", "Archive"];
  return order.indexOf(a.category) - order.indexOf(b.category) || a.title.localeCompare(b.title);
});
const lookup = new Map(documents.map(doc => [doc.path, doc]));
const repository = "https://github.com/Perseusxrltd/mnemion/blob/main/";
function headingText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(headingText).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return headingText(node.props.children);
  return "";
}

export default function Documentation() {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const selected = lookup.get(params.get("doc") ?? "docs/service/README.md");
  const [query, setQuery] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const article = useRef<HTMLElement>(null);
  const section = params.get("section");
  const headingIds = new Map<string, number>();
  function heading(level: number, children: ReactNode) {
    const slug = headingText(children).toLowerCase().replace(/[^\p{L}\p{N}_ -]/gu, "").replaceAll(" ", "-");
    const count = headingIds.get(slug) ?? 0;
    headingIds.set(slug, count + 1);
    return createElement(`h${level}`, { id: `doc-${slug}${count ? `-${count}` : ""}` }, children);
  }
  const filtered = useMemo(() => documents.filter(doc => `${doc.title} ${doc.path} ${doc.category}`.toLowerCase().includes(query.toLowerCase())), [query]);
  useEffect(() => {
    let active = true;
    setBody(""); setError(""); setLoading(!!selected);
    if (selected) selected.load().then(value => { if (active) { setBody(value); setLoading(false); } })
      .catch(() => { if (active) { setError("This guide could not be loaded. Reopen the documentation to retry."); setLoading(false); } });
    else setError("This document is not included in this version. Choose a guide from the library.");
    return () => { active = false; };
  }, [selected]);
  useEffect(() => {
    article.current?.scrollTo(0, 0);
    if (section && body) article.current?.querySelector(`#${CSS.escape(`doc-${section}`)}`)?.scrollIntoView({ block: "start" });
  }, [body, section]);
  function documentLink(href: string) {
    const base = new URL(selected?.path ?? "README.md", "https://docs.mnemion.invalid/");
    const url = new URL(href, base);
    if (url.origin !== base.origin) return null;
    const path = decodeURIComponent(url.pathname.slice(1));
    return lookup.has(path) ? `${location.pathname}?doc=${encodeURIComponent(path)}${url.hash ? `&section=${encodeURIComponent(decodeURIComponent(url.hash.slice(1)))}` : ""}` : repository + path + url.hash;
  }
  return <div className="mn-docs">
    <header className="mn-docs-header">
      <Link to="/workspace"><ArrowLeft size={16} /> Workspace</Link>
      <div><BrandMark /><strong>Documentation & roadmap</strong><span>Version {version}</span></div>
      <a href="https://github.com/Perseusxrltd/mnemion" target="_blank" rel="noreferrer noopener">GitHub <ExternalLink size={14} /></a>
    </header>
    <div className="mn-docs-layout">
      <aside className="mn-docs-library">
        <label><Search size={16} /><input type="search" aria-label="Find a guide" placeholder="Find a guide…" value={query} onChange={event => setQuery(event.target.value)} /></label>
        <nav aria-label="Documentation library">
          {filtered.map((doc, index) => <div key={doc.path}>
            {(!index || filtered[index - 1].category !== doc.category) && <h2>{doc.category}</h2>}
            <button aria-current={selected?.path === doc.path ? "page" : undefined} onClick={() => setParams({ doc: doc.path })}>{doc.title}</button>
          </div>)}
          {!filtered.length && <p>No matching guides.</p>}
        </nav>
        <small>Bundled with this version. Updated guides and release notes arrive with each app update.</small>
      </aside>
      <article className="mn-docs-article" ref={article} aria-label={selected?.title ?? "Documentation"}>
        {selected?.path === "docs/RELEASE_STATUS.md" && <p>
          This is the status snapshot bundled with Mnemion {version}. <a href={repository + "docs/RELEASE_STATUS.md"} target="_blank" rel="noreferrer noopener">View live release status</a> for later updates.
        </p>}
        {loading && <p role="status">Loading guide…</p>}
        {error && <p role="alert">{error}</p>}
        <Markdown remarkPlugins={[remarkGfm]} skipHtml components={{
          h1: ({ children }) => heading(1, children), h2: ({ children }) => heading(2, children),
          h3: ({ children }) => heading(3, children), h4: ({ children }) => heading(4, children),
          h5: ({ children }) => heading(5, children), h6: ({ children }) => heading(6, children),
          a: ({ href, children }) => {
            if (!href) return <span>{children}</span>;
            const resolved = documentLink(href);
            return resolved?.startsWith(location.pathname + "?")
              ? <Link to={resolved}>{children}</Link>
              : <a href={resolved ?? href} target={href.startsWith("#") ? undefined : "_blank"} rel="noreferrer noopener">{children}</a>;
          },
          img: ({ src, alt }) => <a href={src ? documentLink(src) ?? src : undefined} target="_blank" rel="noreferrer noopener">{alt || "View linked illustration"}</a>,
          table: ({ children }) => <div className="mn-docs-table"><table>{children}</table></div>,
        }}>{body}</Markdown>
      </article>
    </div>
  </div>;
}
