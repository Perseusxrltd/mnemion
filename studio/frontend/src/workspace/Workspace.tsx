import {
  createContext,
  Fragment,
  useContext,
  useMemo,
  useRef,
  useState,
  lazy,
  Suspense,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useNavigate,
  useLocation,
  useParams,
} from "react-router-dom";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Archive,
  ChartNoAxesCombined,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  BookOpenCheck,
  Check,
  Copy,
  Database,
  Download,
  FileText,
  Layers,
  LoaderCircle,
  LogOut,
  Plus,
  Plug,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Users,
  Workflow,
} from "lucide-react";
import {
  MnemionClient,
  MnemionError,
  type ApiKey,
  type ContextPack,
  type CoreBlock,
  type Kind,
  type Memory,
  type MemoryInput,
  type Page,
  type Receipt,
  type Recall,
  type Role,
  type Space,
} from "@mnemion/client";
import "./workspace.css";
import Connect from "./Connect";
import type { Connection } from "./connection-types";
import { version } from "../../package.json";
import BrandMark from "../components/BrandMark";
import ErrorBoundary from "../components/ErrorBoundary";
import { Connections, SourceProposals } from "./Connections";
import { Agents } from "./Agents";
import { KnowledgeView } from "./Knowledge";

const InsightsView = lazy(() => import("./Insights"));
const Documentation = lazy(() => import("./Documentation"));
const EmbeddingModels = lazy(() => import("./EmbeddingModels"));
const Librarian = lazy(() => import("./Librarian"));
const Setup = lazy(() => import("./Setup"));

type Me = Awaited<ReturnType<MnemionClient["me"]>>;
type Session = Connection & {
  space: Space;
  reviewer: boolean;
  writer: boolean;
  disconnect: () => void;
  selectSpace: (id: string) => void;
};
const SessionContext = createContext<Session | null>(null);
const useSession = () => {
  const session = useContext(SessionContext);
  if (!session) throw new Error("Connect to a workspace first");
  return session;
};
const date = (value: string) =>
  new Date(value).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
const message = (error: unknown) =>
  error instanceof MnemionError
    ? `${error.message}${error.requestId ? ` · Request ${error.requestId}` : ""}`
    : error instanceof Error
      ? error.message
      : "The request could not be completed.";

function ErrorNotice({ error }: { error: unknown }) {
  return error ? (
    <div className="ws-notice ws-error" role="alert">
      {message(error)}
    </div>
  ) : null;
}
function Busy() {
  return (
    <div className="ws-loading" role="status">
      <LoaderCircle className="ws-spin" size={18} /> Loading workspace…
    </div>
  );
}
function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="ws-empty">
      <Layers size={30} />
      <h3>{title}</h3>
      <div>{children}</div>
    </div>
  );
}
function Title({
  eyebrow,
  title,
  children,
  action,
}: {
  eyebrow?: string;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <header className="ws-page-heading">
      <div>
        {eyebrow && <p className="ws-eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {children && <p>{children}</p>}
      </div>
      {action}
    </header>
  );
}
function Badge({
  children,
  tone = "",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`ws-badge ${tone}`}>{children}</span>;
}
function CopyButton({
  text,
  label = "Copy",
}: {
  text: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<unknown>();
  return (
    <>
      <button
        className="ws-button ws-quiet"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(text);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
          } catch (error) {
            setError(error);
          }
        }}
      >
        {copied ? <Check size={15} /> : <Copy size={15} />}
        {copied ? "Copied" : label}
      </button>
      <ErrorNotice error={error} />
    </>
  );
}
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="ws-field">
      <span>{label}</span>
      {children}
    </label>
  );
}
function WarningList({ warnings }: { warnings: string[] }) {
  const descriptions: Record<string, string> = {
    semantic_index_incomplete:
      "Some memories are waiting for semantic indexing. Search results may be incomplete.",
    semantic_unavailable_lexical_only:
      "Semantic search is unavailable. These results use exact text search.",
    inference_busy_lexical_only:
      "The model was busy. These results use exact text only; matches based on meaning may be missing.",
    contested_evidence:
      "Some evidence is contested. Check its source before relying on it.",
    semantic_matches_require_evidence_review:
      "These matches are based on meaning. Check the evidence for your question.",
    context_budget_or_freshness_limited:
      "Some items were omitted to fit the context budget or because their source changed.",
  };
  return warnings.length ? (
    <div className="ws-notice">
      {warnings.map((warning) => (
        <p key={warning}>
          {descriptions[warning] ?? warning.replaceAll("_", " ")}
        </p>
      ))}
    </div>
  ) : null;
}


function Shell({
  connection,
  disconnect,
}: {
  connection: Connection;
  disconnect: () => void;
}) {
  const { client, me } = connection;
  const location = useLocation();
  const spaces = useQuery({
    queryKey: ["spaces"],
    queryFn: () => client.spaces(),
  });
  const [selected, setSelected] = useState("");
  const selectedSpace = useQuery({
    queryKey: ["space", selected], queryFn: () => client.space(selected),
    enabled: !!selected && !!spaces.data && !spaces.data.items.some(item => item.id === selected),
  });
  const space =
    spaces.data?.items.find((item) => item.id === selected) ??
    selectedSpace.data ??
    spaces.data?.items.find((item) => item.role);
  const [createName, setCreateName] = useState("");
  const [error, setError] = useState<unknown>();
  const [creating, setCreating] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const organizationPage = ['/workspace/team', '/workspace/connections', '/workspace/setup', '/workspace/help']
    .includes(location.pathname.replace(/\/+$/, ''));
  const role = space?.role ?? "reader";
  const reviewer = ["reviewer", "administrator"].includes(role);
  const links = [
    { to: "memories", label: "Memories", icon: Layers },
    { to: "search", label: "Search & context", icon: Search },
    { to: "knowledge", label: "Memory map & wiki", icon: BookOpen },
    { to: "blocks", label: "Core context", icon: BookOpen },
    ...(reviewer ? [{ to: "review", label: "Review", icon: ShieldCheck }] : []),
    { to: "operations", label: "Activity", icon: Workflow },
    ...(reviewer ? [{ to: "insights", label: "Insights & evaluations", icon: ChartNoAxesCombined }] : []),
    ...(reviewer ? [{ to: "librarian", label: "Librarian", icon: BookOpenCheck }] : []),
    ...(role === "administrator" ? [{ to: "models", label: "Embedding models", icon: Database }] : []),
    { to: "obsidian", label: "Obsidian", icon: Archive },
    { to: "agents", label: "Agents & apps", icon: Plug },
    { to: "help", label: "Documentation & roadmap", icon: FileText },
    { to: "setup", label: "Setup & this device", icon: Settings },
    ...(me.administrator
      ? [{ to: "connections", label: "Connections", icon: Plug }, { to: "team", label: "People & apps", icon: Users }]
      : []),
  ];
  const navigationGroups = [
    { label: "01 / Memory", pages: ["memories", "search", "knowledge", "blocks", "review"] },
    { label: "02 / Intelligence", pages: ["operations", "insights", "librarian", "models"] },
    { label: "03 / Workspace", pages: ["setup", "obsidian", "agents", "connections", "team", "help"] },
  ];
  async function createSpace(event: FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError(undefined);
    try {
      const added = await client.createSpace(createName);
      setCreateName("");
      setSelected(added.id);
      await queryClient.invalidateQueries({ queryKey: ["spaces"] });
    } catch (error) {
      setError(error);
    } finally {
      setCreating(false);
    }
  }
  if (spaces.isPending && !organizationPage) return <Busy />;
  if (!organizationPage && selected && !spaces.data?.items.some(item => item.id === selected)) {
    if (selectedSpace.isPending) return <Busy />;
    if (selectedSpace.isError) return <div className="ws-page"><ErrorNotice error={selectedSpace.error} /><button className="ws-button" onClick={() => setSelected("")}>Return to available spaces</button></div>;
  }
  if (spaces.isError && !organizationPage)
    return (
      <div className="ws-page">
        <ErrorNotice error={spaces.error} />
        <button className="ws-button" onClick={disconnect}>
          Disconnect
        </button>
      </div>
    );
  return (
    <div className="ws-shell">
      <a className="ws-skip-link" href="#workspace-content" onClick={event => {
        event.preventDefault();
        document.getElementById("workspace-content")?.focus();
      }}>Skip to workspace content</a>
      <aside className="ws-sidebar">
        <Link to="/workspace" className="ws-brand">
          <BrandMark />
          mnemion<span>studio</span>
        </Link>
        <div className="ws-workspace-name">{me.tenant_name}</div>
        <label className="ws-space-picker">
          <span>Memory space</span>
          <select
            data-update-safe
            aria-label="Memory space"
            value={space?.id ?? ""}
            onChange={(event) => {
              setSelected(event.target.value);
              navigate("/workspace/memories");
            }}
          >
            {!space && <option value="">No memory space selected</option>}
            {spaces.data?.items
              .filter((item) => item.role)
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
          </select>
        </label>
        <nav aria-label="Workspace navigation">
          {navigationGroups.map(group => <Fragment key={group.label}>
            <span className="ws-nav-section">{group.label}</span>
            {group.pages.flatMap(page => links.filter(link => link.to === page)).map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={`/workspace/${to}`}
                className={({ isActive }) => (isActive ? "active" : "")}
              >
                <Icon size={17} />
                {label}
              </NavLink>
            ))}
          </Fragment>)}
        </nav>
        <div className="ws-sidebar-bottom">
          <div>
            <span className="ws-avatar">
              {me.name.slice(0, 1).toUpperCase()}
            </span>
            <div>
              <strong>{me.name}</strong>
              <small>{me.administrator ? "Organization administrator" : space?.role ?? "No space access"}</small>
            </div>
            <button
              title="Disconnect"
              aria-label="Disconnect"
              className="ws-icon-button"
              onClick={disconnect}
            >
              <LogOut size={17} />
            </button>
          </div>
          <small className="ws-preview">Mnemion {version} · Perseus XR</small>
        </div>
      </aside>
      <main className="ws-main" id="workspace-content" tabIndex={-1}>
        {organizationPage ? (
          <>
            <div className="ws-topbar"><span><Users size={14} />{me.tenant_name}</span><Badge>{me.administrator ? 'Organization administrator' : 'Member'}</Badge><button className="ws-icon-button ws-mobile-disconnect" aria-label="Disconnect workspace" onClick={disconnect}><LogOut size={17} /></button></div>
            <div className="ws-scroll"><ErrorBoundary key={location.pathname}><Suspense fallback={<Busy />}><Routes>
              <Route path="team" element={<Team connection={connection} initialSpace={space} />} />
              <Route path="connections" element={<Connections client={client} administrator={me.administrator} endpoint={connection.endpoint} selectSpace={setSelected} />} />
              <Route path="setup" element={<Setup client={client} endpoint={connection.endpoint} administrator={me.administrator} />} />
              <Route path="help" element={<Documentation />} />
            </Routes></Suspense></ErrorBoundary></div>
          </>
        ) : !space ? (
          <div className="ws-page">
            <Title title="Welcome to your workspace">
              {me.administrator ? 'Manage your organization now, or create a memory space when you need one.' : 'Ask your administrator for access to a team space.'}
            </Title>
            {me.administrator && <Link className="ws-button ws-primary" to="/workspace/team"><Users size={16} />Open workspace administration</Link>}
            {me.administrator && (
              <form onSubmit={createSpace} className="ws-card ws-form">
                <Field label="Space name">
                  <input
                    value={createName}
                    onChange={(event) => setCreateName(event.target.value)}
                    required
                    maxLength={200}
                  />
                </Field>
                <button className="ws-button ws-primary" disabled={creating}>
                  Create space
                </button>
              </form>
            )}
            <ErrorNotice error={error} />
          </div>
        ) : (
          <SessionContext.Provider
            value={{
              ...connection,
              space,
              reviewer,
              writer: role !== "reader",
              disconnect,
              selectSpace: setSelected,
            }}
          >
            <div className="ws-topbar">
              <span>
                <Database size={14} />
                {space.name}
              </span>
              <Badge>{role}</Badge>
              <button className="ws-icon-button ws-mobile-disconnect" aria-label="Disconnect workspace" onClick={disconnect}>
                <LogOut size={17} />
              </button>
            </div>
            <div className="ws-scroll" key={space.id}>
              <ErrorBoundary key={location.pathname}>
              <Routes>
                <Route index element={<Navigate to="memories" replace />} />
                <Route path="memories" element={<Memories />} />
                <Route path="new" element={<CreateMemory />} />
                <Route path="memory/:id" element={<MemoryDetail />} />
                <Route path="sources/:id" element={<SourceDetail />} />
                <Route path="search" element={<SearchMemory />} />
                <Route path="knowledge" element={<KnowledgeView key={space.id} client={client} space={space.id} reviewer={reviewer} administrator={me.administrator} />} />
                <Route path="review" element={<Memories review />} />
                <Route path="blocks" element={<CoreContext />} />
                <Route path="operations" element={<Operations />} />
                <Route path="insights" element={<Suspense fallback={<Busy />}><InsightsView client={client} space={space.id} reviewer={reviewer} administrator={me.administrator} /></Suspense>} />
                <Route path="obsidian" element={<Obsidian />} />
                <Route path="models" element={<Suspense fallback={<Busy />}><EmbeddingModels key={space.id} client={client} space={space.id} administrator={space.role === "administrator"} /></Suspense>} />
                <Route path="librarian" element={<Suspense fallback={<Busy />}><Librarian key={space.id} client={client} space={space.id} reviewer={reviewer} administrator={space.role === "administrator"} /></Suspense>} />
                <Route path="agents" element={<Agents endpoint={connection.endpoint} space={space.id} />} />
                <Route
                  path="*"
                  element={<Navigate to="/workspace/memories" replace />}
                />
              </Routes>
              </ErrorBoundary>
            </div>
          </SessionContext.Provider>
        )}
      </main>
    </div>
  );
}

function MemoryCard({ memory }: { memory: Memory }) {
  return (
    <Link
      to={`/workspace/memory/${memory.memory_id}`}
      className="ws-memory-card"
    >
      <div className="ws-card-top">
        <Badge>{memory.kind}</Badge>
        <Badge tone={memory.review_state === "quarantined" ? "warn" : ""}>
          {memory.review_state === "quarantined"
            ? "Quarantined"
            : memory.claim_status}
        </Badge>
        <time dateTime={memory.recorded_at}>{date(memory.recorded_at)}</time>
      </div>
      <h3>{memory.subject || memory.evidence.title}</h3>
      <p className="ws-excerpt">{memory.content}</p>
      <div className="ws-card-bottom">
        <span>
          <FileText size={13} />
          {memory.evidence.title}
        </span>
        <span>
          Revision {memory.revision_version}
          <ArrowRight size={14} />
        </span>
      </div>
    </Link>
  );
}
function Memories({ review = false }: { review?: boolean }) {
  const { client, space, writer, reviewer } = useSession();
  const [cursor, setCursor] = useState<string>();
  const query = useQuery({
    queryKey: ["memories", space.id, cursor, review],
    queryFn: () => client.list(space.id, { limit: 30, cursor, review }),
  });
  if (review && !reviewer)
    return (
      <Empty title="Review access required">
        A reviewer can inspect quarantined evidence.
      </Empty>
    );
  const items = query.data?.items ?? [];
  return (
    <div className="ws-page">
      <Title
        eyebrow={space.name}
        title={review ? "Review evidence" : "Shared memory"}
        action={
          writer && (
            <Link className="ws-button ws-primary" to="/workspace/new">
              <Plus size={16} />
              Save memory
            </Link>
          )
        }
      >
        {review
          ? "Inspect current trust decisions, quarantine uncertain evidence, and preserve its history."
          : "Decisions and context your apps and assistants can recall, with their sources attached."}
      </Title>
      <ErrorNotice error={query.error} />
      {review && reviewer && <SourceProposals client={client} space={space.id} />}
      {query.isPending ? (
        <Busy />
      ) : (
        !query.isError &&
        (items.length ? (
          <div className="ws-memory-grid">
            {items.map((memory) => (
              <MemoryCard key={memory.memory_id} memory={memory} />
            ))}
          </div>
        ) : (
          <Empty title="This space is ready for its first memory">
            {writer ? (
              <Link className="ws-link" to="/workspace/new">
                Save a decision, preference, or project note.
              </Link>
            ) : (
              "Memories shared with this space will appear here."
            )}
          </Empty>
        ))
      )}
      <div className="ws-pagination">
        {cursor && (
          <button className="ws-button" onClick={() => setCursor(undefined)}>
            First page
          </button>
        )}
        {query.data?.next_cursor && (
          <button
            className="ws-button"
            onClick={() => setCursor(query.data!.next_cursor!)}
          >
            Next page
            <ArrowRight size={14} />
          </button>
        )}
      </div>
    </div>
  );
}

function MemoryForm({
  initial,
  onSave,
  busy,
}: {
  initial?: Memory;
  onSave: (input: MemoryInput, reason: string) => void;
  busy: boolean;
}) {
  const [content, setContent] = useState(initial?.content ?? "");
  const [subject, setSubject] = useState(initial?.subject ?? "");
  const [kind, setKind] = useState<Kind>(initial?.kind ?? "fact");
  const [title, setTitle] = useState("");
  const [uri, setUri] = useState("");
  const [source, setSource] = useState("");
  const [reason, setReason] = useState("");
  return (
    <form
      className="ws-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSave(
          {
            content,
            subject: subject || null,
            kind,
            ...(title || source || uri
              ? {
                  source: {
                    title: title || "Captured evidence",
                    uri: uri || null,
                    content: source || null,
                  },
                }
              : {}),
          },
          reason,
        );
      }}
    >
      <div className="ws-form-row">
        <Field label="Subject">
          <input
            value={subject}
            onChange={(event) => setSubject(event.target.value)}
            maxLength={500}
            placeholder="e.g. Billing project"
          />
        </Field>
        <Field label="Memory type">
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value as Kind)}
          >
            {["fact", "event", "preference", "procedure", "note"].map(
              (kind) => (
                <option key={kind}>{kind}</option>
              ),
            )}
          </select>
        </Field>
      </div>
      <Field label="Memory content">
        <textarea
          value={content}
          onChange={(event) => setContent(event.target.value)}
          required
          maxLength={65536}
          rows={8}
          placeholder="What should this workspace remember?"
        />
      </Field>
      <details className="ws-details">
        <summary>Attach source evidence</summary>
        <div className="ws-form">
          <Field label="Source title">
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={300}
              placeholder="Project decision · 9 October"
            />
          </Field>
          <Field label="Source URL (optional)">
            <input
              value={uri}
              onChange={(event) => setUri(event.target.value)}
              maxLength={4096}
              placeholder="https://…"
            />
          </Field>
          <Field label="Original source text (optional)">
            <textarea
              value={source}
              onChange={(event) => setSource(event.target.value)}
              rows={5}
              maxLength={1000000}
              placeholder="Paste the original evidence. Otherwise the memory text is retained as its source."
            />
          </Field>
        </div>
      </details>
      {initial && (
        <Field label="Reason for this revision">
          <input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            required
            maxLength={1000}
          />
        </Field>
      )}
      <div>
        <button
          className="ws-button ws-primary"
          disabled={busy || !content.trim()}
        >
          {busy ? (
            <LoaderCircle size={16} className="ws-spin" />
          ) : (
            <Check size={16} />
          )}
          {initial ? "Save revision" : "Save memory"}
        </button>
      </div>
    </form>
  );
}
function CreateMemory() {
  const { client, space, writer } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const request = useRef<{ body: string; key: string } | null>(null);
  const navigate = useNavigate();
  const cache = useQueryClient();
  async function save(input: MemoryInput) {
    setBusy(true);
    setError(undefined);
    const body = JSON.stringify(input);
    if (request.current?.body !== body)
      request.current = { body, key: crypto.randomUUID() };
    try {
      const receipt = await client.save(space.id, input, request.current.key);
      await cache.invalidateQueries({ queryKey: ["memories", space.id] });
      navigate(`/workspace/memory/${receipt.memory_id}`);
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  if (!writer)
    return (
      <Empty title="Contributor access required">
        Your current space role allows reading shared memory.
      </Empty>
    );
  return (
    <div className="ws-page ws-narrow">
      <Link className="ws-back" to="/workspace/memories">
        <ArrowLeft size={15} />
        Memories
      </Link>
      <Title title="Save a memory">
        Give your apps and assistants useful context, with evidence they can
        follow.
      </Title>
      <ErrorNotice error={error} />
      <div className="ws-card">
        <MemoryForm onSave={save} busy={busy} />
      </div>
    </div>
  );
}

function MemoryDetail() {
  const { id = "" } = useParams();
  const { client, reviewer, writer } = useSession();
  const cache = useQueryClient();
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ["memory", id, reviewer],
    queryFn: () => client.fetch(id, { review: reviewer }),
  });
  const history = useQuery({
    queryKey: ["history", id, reviewer],
    queryFn: () => client.history(id, reviewer),
  });
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [receipt, setReceipt] = useState<Receipt>();
  const [reason, setReason] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const request = useRef<{ body: string; key: string } | null>(null);
  const operation = useQuery({
    queryKey: ["operation", receipt?.operation_id],
    queryFn: () => client.operation(receipt!.operation_id),
    enabled: !!receipt,
    refetchInterval: (query) =>
      ["ready", "failed", "cancelled"].includes(query.state.data?.state ?? "")
        ? false
        : 2000,
  });
  async function refresh() {
    await Promise.all([
      cache.invalidateQueries({ queryKey: ["memory", id] }),
      cache.invalidateQueries({ queryKey: ["history", id] }),
      cache.invalidateQueries({ queryKey: ["memories"] }),
    ]);
  }
  async function revise(input: MemoryInput, reason: string) {
    if (!query.data) return;
    setBusy(true);
    setError(undefined);
    const revision = { ...input, reason, expected_version: query.data.version };
    const body = JSON.stringify(revision);
    if (request.current?.body !== body)
      request.current = { body, key: crypto.randomUUID() };
    try {
      setReceipt(await client.revise(id, revision, request.current.key));
      setEditing(false);
      await refresh();
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  async function review() {
    if (!query.data) return;
    setBusy(true);
    setError(undefined);
    try {
      await client.review(
        id,
        query.data.review_state === "ordinary" ? "quarantined" : "ordinary",
        query.data.version,
        reason,
      );
      setReason("");
      await refresh();
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  async function forget() {
    if (!query.data) return;
    setBusy(true);
    setError(undefined);
    const body = `delete:${id}:${query.data.version}`;
    if (request.current?.body !== body)
      request.current = { body, key: crypto.randomUUID() };
    try {
      await client.forget(id, query.data.version, request.current.key);
      await cache.invalidateQueries({ queryKey: ["memories"] });
      navigate("/workspace/operations");
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  if (query.isPending) return <Busy />;
  if (query.isError)
    return (
      <div className="ws-page">
        <ErrorNotice error={query.error} />
        <Link className="ws-link" to="/workspace/memories">
          Return to memories
        </Link>
      </div>
    );
  const memory = query.data;
  return (
    <div className="ws-page">
      <Link className="ws-back" to="/workspace/memories">
        <ArrowLeft size={15} />
        Memories
      </Link>
      <Title
        eyebrow={`${memory.kind} · version ${memory.version}`}
        title={memory.subject || memory.evidence.title}
        action={
          writer && (
            <button className="ws-button" onClick={() => setEditing(!editing)}>
              {editing ? "Cancel revision" : "Revise memory"}
            </button>
          )
        }
      >
        Recorded {date(memory.recorded_at)}
      </Title>
      <ErrorNotice error={error} />
      {receipt && (
        <div className="ws-notice" role="status">
          Revision saved. Search indexing:{" "}
          {operation.data?.state ?? receipt.state}.
        </div>
      )}
      <div className="ws-detail-grid">
        <section>
          <div className="ws-card">
            {editing ? (
              <MemoryForm
                key={memory.version}
                initial={memory}
                onSave={revise}
                busy={busy}
              />
            ) : (
              <>
                <div className="ws-card-top">
                  <Badge>{memory.claim_status}</Badge>
                  <Badge
                    tone={
                      memory.review_state === "quarantined" ? "warn" : "good"
                    }
                  >
                    {memory.review_state}
                  </Badge>
                </div>
                <div className="ws-prose">{memory.content}</div>
              </>
            )}
          </div>
          <div className="ws-card">
            <h2>Source evidence</h2>
            <Link
              className="ws-source-link"
              to={`/workspace/sources/${memory.evidence.source_revision_id}`}
            >
              <FileText size={18} />
              <span>
                {memory.evidence.title}
                <small>Open original source and content hash</small>
              </span>
              <ArrowRight size={16} />
            </Link>
            <blockquote>{memory.evidence.excerpt.slice(0, 4000)}</blockquote>
          </div>
          {(reviewer || memory.can_forget === true) && (
            <div className="ws-card">
              <h2>{reviewer ? 'Review & lifecycle' : 'Withdraw your memory'}</h2>
              <p>
                {reviewer ? 'Quarantined memory stays available to reviewers and is excluded from ordinary search and exports.'
                  : 'You can withdraw your own ordinary, unverified memory when nobody else has revised it. Other memories require a reviewer.'}
              </p>
              <div className="ws-form">
                {reviewer && <Field label="Review reason">
                  <input
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    maxLength={1000}
                    placeholder="Explain this decision"
                  />
                </Field>}
                <div className="ws-actions">
                  {reviewer && <button
                    className="ws-button"
                    disabled={busy || !reason.trim()}
                    onClick={review}
                  >
                    {memory.review_state === "ordinary"
                      ? "Quarantine memory"
                      : "Return to ordinary memory"}
                  </button>}
                  {(memory.can_forget === true || (memory.can_forget == null && reviewer)) && <button
                    className="ws-button ws-danger"
                    disabled={busy}
                    onClick={() => setConfirmDelete(true)}
                  >
                    {reviewer ? 'Delete memory' : 'Withdraw memory'}
                  </button>}
                </div>
                {confirmDelete && (
                  <div className="ws-notice ws-delete-confirm">
                    <strong>Delete this memory and its saved sources?</strong>
                    <p>
                      Access is removed immediately. The worker then purges
                      content and retains a deletion receipt.
                    </p>
                    <div className="ws-actions">
                      <button
                        className="ws-button ws-danger"
                        disabled={busy}
                        onClick={forget}
                      >
                        Delete this memory
                      </button>
                      <button
                        className="ws-button"
                        onClick={() => setConfirmDelete(false)}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </section>
        <aside className="ws-card ws-history">
          <h2>Revision history</h2>
          <ErrorNotice error={history.error} />
          {history.isPending ? (
            <Busy />
          ) : (
            history.data?.items.map((revision) => (
              <details key={revision.revision_id}>
                <summary>
                  <span>Revision {revision.revision_version}</span>
                  <small>{date(revision.recorded_at)}</small>
                </summary>
                <p className="ws-prose">{revision.content}</p>
                <Link
                  className="ws-link"
                  to={`/workspace/sources/${revision.evidence.source_revision_id}`}
                >
                  View evidence
                </Link>
              </details>
            ))
          )}
          <div className="ws-identifier">
            <span>Memory ID</span>
            <code>{memory.memory_id}</code>
            <CopyButton text={memory.memory_id} />
          </div>
        </aside>
      </div>
    </div>
  );
}

function SourceDetail() {
  const { id = "" } = useParams();
  const { client, reviewer } = useSession();
  const [downloadError, setDownloadError] = useState<unknown>();
  const [downloading, setDownloading] = useState<string>();
  const query = useQuery({
    queryKey: ["source", id, reviewer],
    queryFn: () => client.source(id, reviewer),
  });
  if (query.isPending) return <Busy />;
  if (query.isError)
    return (
      <div className="ws-page">
        <ErrorNotice error={query.error} />
      </div>
    );
  const source = query.data;
  return (
    <div className="ws-page ws-narrow">
      <Title eyebrow="Source evidence" title={source.title}>
        Captured {date(source.recorded_at)} · {source.media_type}
      </Title>
      {source.uri && (
        <div className="ws-notice">
          Origin:{" "}
          {/^https?:\/\//i.test(source.uri) ? (
            <a href={source.uri} target="_blank" rel="noopener noreferrer">
              {source.uri}
            </a>
          ) : (
            source.uri
          )}
        </div>
      )}
      <div className="ws-card ws-prose">{source.content}</div>
      <ErrorNotice error={downloadError} />
      {source.attachments?.length > 0 && <div className="ws-card">
        <h3>Original files and migration evidence</h3>
        <div className="ws-actions">
          {source.attachments.map(file => <button className="ws-button" key={file.attachment_id} disabled={!!downloading} onClick={async () => {
            setDownloading(file.attachment_id); setDownloadError(undefined);
            try {
              const bytes = await client.attachment(id, file.attachment_id, reviewer);
              const actual = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), n => n.toString(16).padStart(2, "0")).join("");
              if (actual !== file.content_hash) throw new Error("The downloaded file failed its checksum. Please retry.");
              const url = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
              const link = document.createElement("a"); link.href = url; link.download = file.name; link.click();
              setTimeout(() => URL.revokeObjectURL(url), 30_000);
            } catch (error) { setDownloadError(error); }
            finally { setDownloading(undefined); }
          }}><Download size={16} />{file.name} · {Math.ceil(file.size_bytes / 1024)} KB</button>)}
        </div>
      </div>}
      <div className="ws-identifier">
        <span>SHA-256</span>
        <code>{source.content_hash}</code>
      </div>
    </div>
  );
}

function SearchMemory() {
  const { client, me, space, selectSpace } = useSession();
  const [allAccessible, setAllAccessible] = useState(true);
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"hybrid" | "lexical" | "semantic">("hybrid");
  const [busyPolicy, setBusyPolicy] = useState<"error" | "lexical">("error");
  const serviceParts = me.service_version?.match(/^(\d{1,5})\.(\d{1,5})\.(\d{1,5})$/)?.slice(1).map(Number);
  const supportsBusyFallback = !!serviceParts && (serviceParts[0] > 4 ||
    (serviceParts[0] === 4 && (serviceParts[1] > 1 || (serviceParts[1] === 1 && serviceParts[2] >= 2))));
  const [result, setResult] = useState<Recall>();
  const [context, setContext] = useState<ContextPack>();
  const [budget, setBudget] = useState(2048);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  async function search(event?: FormEvent, pack = false) {
    event?.preventDefault();
    setBusy(true);
    setError(undefined);
    setContext(undefined);
    setResult(undefined);
    try {
      const input = {
        query: text, ...(allAccessible ? { all_accessible: true } : { space_ids: [space.id] }), mode, limit: 20,
        ...(supportsBusyFallback && busyPolicy === "lexical" ? { on_inference_busy: "lexical" as const } : {}),
      };
      if (pack)
        setContext(await client.context({ ...input, token_budget: budget }));
      else setResult(await client.search(input));
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="ws-page">
      <Title title="Find the context that matters">
        Search permitted sources, follow the evidence, or prepare context for an
        assistant.
      </Title>
      <form className="ws-search-form" onSubmit={search}>
        <div className="ws-search-input">
          <Search size={20} />
          <input
            aria-label="Search shared memory"
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="What does your team need to remember?"
            required
            maxLength={4000}
          />
        </div>
        <button
          className="ws-button ws-primary"
          disabled={busy || !text.trim()}
        >
          Search
        </button>
      </form>
      <div className="ws-search-options">
        <Field label="Search scope"><select value={allAccessible ? "all" : "space"} onChange={event => setAllAccessible(event.target.value === "all")}><option value="all">All accessible memory</option><option value="space">This space</option></select></Field>
        <Field label="Search method">
          <select
            value={mode}
            onChange={(event) => setMode(event.target.value as typeof mode)}
          >
            <option value="hybrid">Meaning + exact text</option>
            <option value="lexical">Exact text</option>
            <option value="semantic">Meaning</option>
          </select>
        </Field>
        <Field label="Context token budget">
          <input
            type="number"
            min={64}
            max={32768}
            value={budget}
            onChange={(event) => setBudget(Number(event.target.value))}
          />
        </Field>
        <Field label="If the model is busy">
          <select
            value={supportsBusyFallback ? busyPolicy : "error"}
            disabled={busy || !supportsBusyFallback}
            onChange={event => setBusyPolicy(event.target.value as typeof busyPolicy)}
          >
            <option value="error">Wait, then retry</option>
            <option value="lexical">Use exact text</option>
          </select>
        </Field>
        <button
          className="ws-button"
          disabled={busy || !text.trim() || budget < 64 || budget > 32768}
          onClick={() => search(undefined, true)}
        >
          <BookOpen size={16} />
          Build context
        </button>
      </div>
      {!supportsBusyFallback && <p className="ws-helper">Exact-text fallback needs workspace server 4.1.2 or later. <Link to="/workspace/setup">Check app & server versions</Link>, then reconnect after the server update.</p>}
      <ErrorNotice error={error} />
      {busy && <Busy />}
      {result && (
        <>
          <WarningList warnings={result.warnings} />
          <div className="ws-result-summary">
            {result.hits.length} results · {result.timing_ms.toFixed(0)} ms ·{" "}
            {result.index.indexed_records}/{result.index.eligible_records}{" "}
            memories indexed
          </div>
          {result.hits.length ? (
            result.hits.map((hit) => (
              <article className="ws-card ws-search-result" key={hit.memory_id}>
                <div className="ws-card-top">
                  <Badge>{hit.claim_status}</Badge>
                  <time>{date(hit.recorded_at)}</time>
                </div>
                <h2>
                  <Link to={`/workspace/memory/${hit.memory_id}`} onClick={() => selectSpace(hit.space_id)}>
                    {hit.subject || hit.evidence.title}
                  </Link>
                </h2>
                <p className="ws-prose">{hit.text}</p>
                <Link
                  className="ws-link"
                  to={`/workspace/sources/${hit.evidence.source_revision_id}`}
                  onClick={() => selectSpace(hit.space_id)}
                >
                  {hit.evidence.title} <ArrowRight size={13} />
                </Link>
                <details className="ws-details">
                  <summary>Why this result?</summary>
                  <p>
                    Combined relevance: {hit.relevance_score.toFixed(3)}. This
                    rank measures a match to your question, not whether the
                    claim is true.
                  </p>
                  <p>
                    {hit.ranking.ranks.lexical
                      ? `Exact-text rank ${hit.ranking.ranks.lexical}. `
                      : ""}
                    {hit.ranking.ranks.semantic
                      ? `Semantic rank ${hit.ranking.ranks.semantic}.`
                      : ""}
                  </p>
                  <blockquote>{hit.evidence.excerpt}</blockquote>
                </details>
              </article>
            ))
          ) : (
            <Empty title="No matching evidence">
              Try another phrase or check that the memory belongs to this space.
            </Empty>
          )}
        </>
      )}
      {context && (
        <>
          <WarningList warnings={context.warnings} />
          <div className="ws-result-summary">
            {context.token_count}/{context.token_budget} {context.token_count_unit === "utf8_bytes" ? "UTF-8 bytes" : "tokens"} ·{" "}
            {context.citations.length} citations · {context.omitted_items}{" "}
            omitted
          </div>
          <div className="ws-card">
            <div className="ws-section-title">
              <h2>Context pack</h2>
              <CopyButton text={context.text} label="Copy context" />
            </div>
            <pre className="ws-prose">
              {context.text || "No evidence fits this request."}
            </pre>
            <p className="ws-helper">
              Budget measured with {context.tokenizer}. An assistant’s tokenizer
              may count differently.
            </p>
            {context.citations.map((citation) => (
              <Link
                className="ws-citation"
                key={citation.number}
                to={`/workspace/memory/${citation.memory_id}`}
                onClick={() => selectSpace(citation.space_id)}
              >
                [{citation.number}] Open cited memory
                <ArrowRight size={13} />
              </Link>
            ))}
          </div>
        </>
      )}
      {!result && !context && !busy && (
        <Empty title="Start with a question">
          Search returns evidence your team can inspect. Context packs include
          source citations.
        </Empty>
      )}
    </div>
  );
}

function CoreContext() {
  const { client, space, reviewer } = useSession();
  const query = useQuery({
    queryKey: ["blocks", space.id],
    queryFn: () => client.blocks(space.id),
  });
  const cache = useQueryClient();
  const [editing, setEditing] = useState<CoreBlock | "new">();
  const [key, setKey] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await client.putBlock(
        space.id,
        key,
        content,
        editing && editing !== "new" ? editing.version : 0,
      );
      setEditing(undefined);
      await cache.invalidateQueries({ queryKey: ["blocks", space.id] });
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="ws-page ws-narrow">
      <Title
        title="Core context"
        action={
          reviewer && (
            <button
              className="ws-button ws-primary"
              onClick={() => {
                setEditing("new");
                setKey("");
                setContent("");
              }}
            >
              <Plus size={16} />
              New block
            </button>
          )
        }
      >
        Keep concise team context available when assistants build a context
        pack.
      </Title>
      <ErrorNotice error={query.error || error} />
      {editing && (
        <form className="ws-card ws-form" onSubmit={save}>
          <Field label="Block key">
            <input
              value={key}
              onChange={(event) => setKey(event.target.value)}
              disabled={editing !== "new"}
              required
              maxLength={100}
              pattern="[\p{L}\p{N}_\-]+"
              placeholder="team_context"
            />
          </Field>
          <Field label="Block content">
            <textarea
              value={content}
              onChange={(event) => setContent(event.target.value)}
              rows={6}
              maxLength={16000}
            />
          </Field>
          <div className="ws-actions">
            <button className="ws-button ws-primary" disabled={busy}>
              Save block
            </button>
            <button
              type="button"
              className="ws-button"
              onClick={() => setEditing(undefined)}
            >
              Cancel
            </button>
          </div>
        </form>
      )}
      {query.isPending ? (
        <Busy />
      ) : (
        !query.isError &&
        (query.data?.items.length ? (
          query.data.items.map((block) => (
            <div key={block.key} className="ws-card">
              <div className="ws-section-title">
                <h2>{block.key}</h2>
                {reviewer && (
                  <button
                    className="ws-button ws-quiet"
                    onClick={() => {
                      setEditing(block);
                      setKey(block.key);
                      setContent(block.content);
                    }}
                  >
                    Edit
                  </button>
                )}
              </div>
              <p className="ws-prose">{block.content || "Empty block"}</p>
              <small>
                Version {block.version} · Updated {date(block.updated_at)}
              </small>
            </div>
          ))
        ) : (
          <Empty title="No core context yet">
            A reviewer can add team conventions or a project overview.
          </Empty>
        ))
      )}
    </div>
  );
}

function Operations() {
  const { client, space, reviewer } = useSession();
  const activity = useQuery({
    queryKey: ["activity", space.id],
    queryFn: () => client.activity(space.id),
    enabled: reviewer,
    refetchInterval: 5000,
  });
  const query = useQuery({
    queryKey: ["operations", space.id],
    queryFn: () => client.operations(space.id),
    refetchInterval: 5000,
  });
  const status = useQuery({
    queryKey: ["status", space.id],
    queryFn: () =>
      client.request<{
        memories: number;
        operations: { state: string; count: number }[];
      }>("GET", `/v1/spaces/${space.id}/status`),
    refetchInterval: 5000,
  });
  const [error, setError] = useState<unknown>();
  async function retry(id: string) {
    try {
      await client.retryOperation(id);
      await query.refetch();
    } catch (error) {
      setError(error);
    }
  }
  const count = (states: string[]) =>
    status.data?.operations
      .filter((item) => states.includes(item.state))
      .reduce((total, item) => total + item.count, 0) ?? 0;
  return (
    <div className="ws-page">
      <Title
        title="Activity & recovery"
        action={
          <button
            className="ws-button"
            onClick={() => {
              void query.refetch();
              void status.refetch();
              if (reviewer) void activity.refetch();
            }}
          >
            <RefreshCw size={15} />
            Refresh
          </button>
        }
      >
        A save is durable as soon as it is accepted. The worker adds semantic
        search and completes content purges.
      </Title>
      <ErrorNotice error={query.error || status.error || activity.error || error} />
      <div className="ws-stats">
        <div>
          <span>Current memories</span>
          <strong>{status.data?.memories ?? "—"}</strong>
        </div>
        <div>
          <span>Waiting / indexing</span>
          <strong>{status.data ? count(["accepted", "indexing"]) : "—"}</strong>
        </div>
        <div>
          <span>Needs attention</span>
          <strong>{status.data ? count(["failed"]) : "—"}</strong>
        </div>
      </div>
      {query.isPending ? (
        <Busy />
      ) : (
        !query.isError &&
        (query.data?.items.length ? (
          <div className="ws-table-wrap">
            <table className="ws-table">
              <thead>
                <tr>
                  <th>Operation</th>
                  <th>State</th>
                  <th>Updated</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {query.data.items.map((operation) => (
                  <tr key={operation.operation_id}>
                    <td>
                      <strong>
                        {operation.kind === "delete"
                          ? "Content purge"
                          : operation.kind === "revise"
                            ? "Revision indexing"
                            : "Memory indexing"}
                      </strong>
                      <small>{operation.operation_id}</small>
                    </td>
                    <td>
                      <Badge
                        tone={
                          operation.state === "failed"
                            ? "warn"
                            : operation.state === "ready"
                              ? "good"
                              : ""
                        }
                      >
                        {operation.state}
                      </Badge>
                      {operation.error_code && (
                        <small>{operation.error_code}</small>
                      )}
                    </td>
                    <td>{date(operation.updated_at)}</td>
                    <td>
                      {operation.state === "failed" && reviewer ? (
                        <button
                          className="ws-button"
                          onClick={() => retry(operation.operation_id)}
                        >
                          Retry
                        </button>
                      ) : operation.kind !== "delete" && !operation.memory_deleted && operation.memory_id ? (
                        <Link
                          className="ws-link"
                          to={`/workspace/memory/${operation.memory_id}`}
                        >
                          View memory
                        </Link>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No operations yet">
            Accepted saves and deletion receipts appear here.
          </Empty>
        ))
      )}
      <p className="ws-helper">
        The most recent 100 operations are shown. If work stays accepted, check
        that the indexing worker is running.
      </p>
      {reviewer && <section aria-label="Recent changes">
        <h2>Recent changes</h2>
        <p className="ws-helper">Review and correction notes are visible to reviewers. Notes are removed when their memory is deleted.</p>
        {activity.isPending ? <Busy /> : activity.data?.items.length ? (
          <div className="ws-table-wrap"><table className="ws-table">
            <thead><tr><th>Change</th><th>Note</th><th>When</th></tr></thead>
            <tbody>{activity.data.items.map(event => <tr key={event.id}>
              <td><strong>{event.action.replaceAll(".", " ").replaceAll("_", " ")}</strong><small>{event.resource_id}</small></td>
              <td><p className="ws-prose">{event.reason || "—"}</p></td>
              <td>{date(event.created_at)}</td>
            </tr>)}</tbody>
          </table></div>
        ) : <Empty title="No changes yet">Saves, corrections, reviews, and deletions appear here.</Empty>}
      </section>}
    </div>
  );
}

function Obsidian() {
  const { client, space, reviewer } = useSession();
  const [allAccessible, setAllAccessible] = useState(false);
  const [review, setReview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [downloaded, setDownloaded] = useState(false);
  const [vault, setVault] = useState("Mnemion");
  const [localVault, setLocalVault] = useState<{ id: string; path: string } | null>(null);
  const [refreshed, setRefreshed] = useState<Awaited<ReturnType<NonNullable<NonNullable<Window["mnemion"]>["refreshVault"]>>> | null>(null);
  async function refreshLocal() {
    setBusy(true);
    setError(undefined);
    setRefreshed(null);
    try {
      const chosen = localVault || await window.mnemion!.chooseVault!();
      if (!chosen) return;
      setLocalVault(chosen);
      const bundle = await client.exportObsidian(allAccessible ? [] : [space.id], review, allAccessible);
      const result = await window.mnemion!.refreshVault!(chosen.id, new Uint8Array(bundle));
      setRefreshed(result);
    } catch (error) {
      setError(error);
    } finally { setBusy(false); }
  }
  async function download() {
    setBusy(true);
    setError(undefined);
    setDownloaded(false);
    try {
      const bundle = await client.exportObsidian(allAccessible ? [] : [space.id], review, allAccessible);
      const url = URL.createObjectURL(
        new Blob([bundle], { type: "application/zip" }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = "mnemion-obsidian.zip";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
      setDownloaded(true);
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  const command = `mnemion-service --credentials owner.mnemion-credentials.json vault --path "Mnemion" ${allAccessible ? "--all-accessible" : `--spaces ${space.id}`}${review ? " --review" : ""}`;
  return (
    <div className="ws-page ws-narrow">
      <Title eyebrow="Connected visualization" title="Your memory, in Obsidian">
        Explore the same memories as Markdown notes, linked sources, and a
        native knowledge graph.
      </Title>
      <ErrorNotice error={error} />
      <div className="ws-card ws-obsidian-card">
        <div className="ws-obsidian-symbol">
          <Workflow size={34} />
        </div>
        <h2>Open a connected vault</h2>
        <p>
          Download selected memory as a vault and extract it into a new folder. In
          Obsidian, choose “Open folder as vault”. The Mnemion index links
          memories, sources, revisions, and subjects.
        </p>
        <label className="ws-checkbox"><input type="checkbox" checked={allAccessible} onChange={event => { setAllAccessible(event.target.checked); setLocalVault(null); setRefreshed(null); setDownloaded(false); }} />Include all accessible memory</label>
        {(reviewer || allAccessible) && (
          <label className="ws-checkbox">
            <input
              type="checkbox"
              checked={review}
              onChange={(event) => setReview(event.target.checked)}
            />
            Include quarantined evidence for review
          </label>
        )}
        <button
          className="ws-button ws-primary"
          disabled={busy}
          onClick={download}
        >
          <Download size={16} />
          {busy ? "Preparing vault…" : "Download Obsidian vault"}
        </button>
        {downloaded && (
          <p className="ws-success" role="status">
            Vault downloaded. Open the extracted folder in Obsidian.
          </p>
        )}
        {window.mnemion?.refreshVault && (
          <div className="ws-native-vault">
            <button className="ws-button" disabled={busy} onClick={refreshLocal}>
              <RefreshCw size={16} />{busy ? "Refreshing…" : localVault ? "Refresh selected vault" : "Choose folder and refresh"}
            </button>
            {localVault && <p className="ws-helper">{localVault.path} <button className="ws-link" onClick={() => { setLocalVault(null); setRefreshed(null); }}>Change folder</button></p>}
            {refreshed?.completed && <p className="ws-success" role="status">Vault refreshed. Personal annotations and Obsidian settings were preserved.</p>}
            {refreshed && !refreshed.completed && <div className="ws-notice" role="alert">Some generated sections were edited. Your files were preserved; review the conflict proposals in the vault before refreshing again.<ul>{refreshed.conflicts.map((conflict) => <li key={conflict.path}>{conflict.path}</li>)}</ul></div>}
          </div>
        )}
      </div>
      <div className="ws-card">
        <h2>Refresh without losing your notes</h2>
        <p>
          The local refresh command keeps personal annotations and unmanaged
          files. If a generated section was edited, it preserves your version
          and creates a conflict proposal. Use a copied vault for the first
          migration.
        </p>
        <Field label="Registered Obsidian vault name">
          <input
            value={vault}
            onChange={(event) => setVault(event.target.value)}
            placeholder="Mnemion"
          />
        </Field>
        <div className="ws-code">
          <code>{command}</code>
          <CopyButton text={command} label="Copy command" />
        </div>
        <small>
          The credentials file belongs to your local client. The service does
          not write to a folder on your computer.
        </small>
      </div>
      <div className="ws-card">
        <h2>Already registered in Obsidian?</h2>
        <p>
          After importing or refreshing, open the vault by its registered name.
        </p>
        <a
          className="ws-button"
          href={`obsidian://open?vault=${encodeURIComponent(vault.split(/[\\/]/).filter(Boolean).at(-1) || "Mnemion")}`}
        >
          Open in Obsidian
          <ArrowRight size={15} />
        </a>
      </div>
    </div>
  );
}

function Team({ connection, initialSpace }: { connection: Connection; initialSpace?: Space }) {
  const { client, me } = connection;
  const cache = useQueryClient();
  const [spaceId, setSpaceId] = useState(initialSpace?.id ?? '');
  const spaces = useQuery({ queryKey: ['spaces'], queryFn: () => client.spaces(), enabled: me.administrator });
  const space = spaces.data?.items.find(item => item.id === spaceId);
  const people = useQuery({
    queryKey: ["principals"],
    queryFn: () => client.principals(),
    enabled: me.administrator,
  });
  const keys = useQuery({
    queryKey: ["keys"],
    queryFn: () => client.keys(),
    enabled: me.administrator,
  });
  const grants = useQuery({
    queryKey: ["grants", space?.id],
    queryFn: () =>
      client.request<
        Page<{ principal_id: string; name: string; kind: string; role: Role }>
      >("GET", `/v1/spaces/${space!.id}/grants`),
    enabled: me.administrator && !!space,
  });
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"human" | "application">("application");
  const [newAdministrator, setNewAdministrator] = useState(false);
  const [createdIdentity, setCreatedIdentity] = useState<{ name: string; administrator: boolean }>();
  const [disablingIdentity, setDisablingIdentity] = useState<string>();
  const [administrationNotice, setAdministrationNotice] = useState("");
  const keyForm = useRef<HTMLFormElement>(null);
  const [principal, setPrincipal] = useState("");
  const [role, setRole] = useState<Role>("reader");
  const [keyName, setKeyName] = useState("");
  const [keyPrincipal, setKeyPrincipal] = useState("");
  const [newKey, setNewKey] = useState<ApiKey & { api_key: string }>();
  const [newSpace, setNewSpace] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  async function act(work: () => Promise<unknown>) {
    setBusy(true);
    setError(undefined);
    try {
      await work();
      await Promise.all(
        ["principals", "keys", "grants", "spaces"].map((key) =>
          cache.invalidateQueries({ queryKey: [key] }),
        ),
      );
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  if (!me.administrator)
    return <Empty title="Organization administrator access required" />;
  const options =
    people.data?.items.filter((person) => !person.disabled_at) ?? [];
  const retiring = options.find(person => person.id === disablingIdentity && person.id !== me.principal_id);
  return (
    <div className="ws-page">
      <Title title="People & apps">
        Give each person and application its own identity, then grant access to
        specific spaces.
      </Title>
      <ErrorNotice
        error={error || people.error || keys.error || grants.error || spaces.error}
      />
      {administrationNotice && <div className="ws-notice" role="status">{administrationNotice}</div>}
      <section className="ws-card">
        <div className="ws-section-title"><h2>Independent workspace administration</h2><ShieldCheck size={20} /></div>
        <p>You are an organization administrator. Give another trusted person their own administrator identity and key, then verify their connection from a second device. Administration will no longer depend on one assistant’s session.</p>
        <p className="ws-helper">Organization administrators manage identities, keys and space grants. Reading memory still requires a space grant. Starting or recovering a remote host requires separately configured operator access.</p>
        <Link className="ws-link" to="/workspace/help?doc=docs%2Fservice%2Forganizations.md">Administration and recovery guide<ArrowRight size={13} /></Link>
      </section>
      {createdIdentity && <div className="ws-notice" role="status">Created <strong>{createdIdentity.name}</strong> as {createdIdentity.administrator ? 'an organization administrator' : 'a member'}. <button type="button" className="ws-link" onClick={() => { keyForm.current?.scrollIntoView({ block: 'start' }); keyForm.current?.querySelector('select')?.focus({ preventScroll: true }); }}>Create their individual key</button> and verify their connection. Space access is assigned separately.</div>}
      <div className="ws-team-grid">
        <form
          className="ws-card ws-form"
          onSubmit={(event) => {
            event.preventDefault();
            void act(async () => {
              const person = await client.createPrincipal(name.trim(), kind, { administrator: newAdministrator });
              setCreatedIdentity(person);
              setKeyPrincipal(person.id);
              setKeyName(person.kind === 'human' ? 'Personal access' : 'Application access');
              setPrincipal(person.id);
              setName("");
              setNewAdministrator(false);
            });
          }}
        >
          <h2>Add an identity</h2>
          <Field label="Name">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              maxLength={200}
              placeholder="Billing assistant"
            />
          </Field>
          <Field label="Identity type">
            <select
              value={kind}
              onChange={(event) => { setKind(event.target.value as typeof kind); setNewAdministrator(false); }}
            >
              <option value="application">Application / assistant</option>
              <option value="human">Person</option>
            </select>
          </Field>
          <Field label="Organization role">
            <select value={newAdministrator ? 'administrator' : 'member'} onChange={event => setNewAdministrator(event.target.value === 'administrator')}>
              <option value="member">Member — assigned spaces only</option>
              <option value="administrator">Organization administrator</option>
            </select>
          </Field>
          {newAdministrator && <p className="ws-helper">This identity will be able to manage organization members, issue keys and change space permissions. {kind === 'application' ? 'Use this authority only for a specifically trusted administration agent.' : 'Give the person their own key; do not share the original administrator’s key.'}</p>}
          <button className="ws-button ws-primary" disabled={busy || !name.trim()}>
            {newAdministrator ? 'Create administrator' : 'Create identity'}
          </button>
          <small>
            New identities have no memory access until you grant it.
          </small>
        </form>
        <form
          className="ws-card ws-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (space) void act(() => client.grant(space.id, principal, role));
          }}
        >
          <h2>Grant access to {space?.name ?? 'a memory space'}</h2>
          <Field label="Memory space to administer">
            <select value={spaceId} onChange={event => setSpaceId(event.target.value)} required>
              <option value="">Choose a memory space</option>
              {spaces.data?.items.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </Field>
          <Field label="Identity">
            <select
              required
              value={principal}
              onChange={(event) => setPrincipal(event.target.value)}
            >
              <option value="">Select a person or app</option>
              {options.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Space role">
            <select
              value={role}
              onChange={(event) => setRole(event.target.value as Role)}
            >
              {["reader", "contributor", "reviewer", "administrator"].map(
                (role) => (
                  <option key={role}>{role}</option>
                ),
              )}
            </select>
          </Field>
          <button className="ws-button" disabled={busy || !principal || !space}>
            Save access
          </button>
          <small>
            Readers recall. Contributors also save and revise observed memories.
            Reviewers manage truth and deletion.
          </small>
        </form>
      </div>
      <section className="ws-card">
        <div className="ws-section-title"><h2>Organization identities</h2><button type="button" className="ws-button ws-quiet" disabled={busy || people.isFetching} onClick={() => void people.refetch()}><RefreshCw size={14} />Refresh</button></div>
        {people.isPending ? <Busy /> : <div className="ws-table-wrap"><table className="ws-table ws-identities-table" role="table" aria-label="Organization identities">
          <thead><tr><th>Identity</th><th>Type</th><th>Organization role</th><th>Status</th><th>Access control</th></tr></thead>
          <tbody role="rowgroup">{people.data?.items.map(person => <tr key={person.id} role="row">
            <td role="cell">{person.name}{person.id === me.principal_id && <small>You</small>}</td>
            <td role="cell" data-label="Type">{person.kind === 'human' ? 'Person' : 'Application / assistant'}</td>
            <td role="cell" data-label="Authority">{person.administrator ? 'Organization administrator' : 'Member'}</td>
            <td role="cell" data-label="Status">{person.disabled_at ? 'Disabled' : 'Active identity'}</td>
            <td role="cell" data-label="Control">{!person.disabled_at && person.id !== me.principal_id && <button type="button" className="ws-button ws-quiet" disabled={busy} aria-label={`Disable ${person.name}`} onClick={() => { setDisablingIdentity(person.id); setAdministrationNotice(""); }}>Disable</button>}{person.id === me.principal_id && <small>Use another administrator to disable this identity.</small>}</td>
          </tr>)}</tbody>
        </table></div>}
        {retiring && <div className="ws-notice ws-delete-confirm" role="group" aria-label="Confirm disabling identity">
          <strong>Disable {retiring.name}?</strong>
          <p>All of this {retiring.kind === 'human' ? 'person’s' : 'application’s'} keys and linked sign-ins will stop working. Its recorded memories and history are retained. Disabling is permanent; future access requires a new identity and explicit grants.</p>
          {retiring.administrator && <p>Verify another administrator’s independent access before retiring this administrator.</p>}
          <div className="ws-actions"><button type="button" className="ws-button" disabled={busy} onClick={() => void act(async () => {
            await client.disablePrincipal(retiring.id);
            setDisablingIdentity(undefined);
            setCreatedIdentity(undefined);
            if (keyPrincipal === retiring.id) setKeyPrincipal("");
            if (principal === retiring.id) setPrincipal("");
            if (newKey?.principal_id === retiring.id) setNewKey(undefined);
            setAdministrationNotice(`Disabled ${retiring.name}. Its keys and linked sign-ins no longer grant access; recorded memories and history are retained.`);
          })}>Disable identity</button><button type="button" className="ws-button ws-quiet" disabled={busy} onClick={() => setDisablingIdentity(undefined)}>Keep access</button></div>
        </div>}
        <p className="ws-helper">An active identity still needs a valid individual credential. This list does not confirm that its owner has signed in or that the workspace host is recoverable.</p>
        {(people.data?.items.length ?? 0) >= 1000 && <p className="ws-helper">Showing the first 1,000 identities returned by this server.</p>}
      </section>
      <div className="ws-card">
        <h2>Space access</h2>
        {!space ? <p className="ws-helper">Choose a memory space above to inspect and manage its grants. You do not need to read its memories to administer access.</p> : grants.isPending ? (
          <Busy />
        ) : (
          <div className="ws-table-wrap">
            <table className="ws-table">
              <thead>
                <tr>
                  <th>Identity</th>
                  <th>Type</th>
                  <th>Role</th>
                  <th>Access</th>
                </tr>
              </thead>
              <tbody>
                {grants.data?.items.map((grant) => (
                  <tr key={grant.principal_id}>
                    <td>{grant.name}</td>
                    <td>{grant.kind}</td>
                    <td>{grant.role}</td>
                    <td>
                      {grant.principal_id !== me.principal_id && (
                        <button
                          className="ws-button ws-quiet"
                          disabled={busy}
                          onClick={() =>
                            act(() =>
                              client.revokeGrant(space.id, grant.principal_id),
                            )
                          }
                        >
                          Remove
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div className="ws-team-grid">
        <form id="ws-create-key" ref={keyForm}
          className="ws-card ws-form"
          onSubmit={(event) => {
            event.preventDefault();
            void act(async () => {
              setNewKey(await client.createKey(keyPrincipal, keyName));
              setKeyName("");
            });
          }}
        >
          <h2>Create an API key</h2>
          <Field label="Key identity">
            <select
              value={keyPrincipal}
              onChange={(event) => setKeyPrincipal(event.target.value)}
              required
            >
              <option value="">Select a person or app</option>
              {options.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Key name">
            <input
              value={keyName}
              onChange={(event) => setKeyName(event.target.value)}
              required
              maxLength={200}
              placeholder="Production assistant"
            />
          </Field>
          <button className="ws-button" disabled={busy || !keyPrincipal}>
            Create API key
          </button>
        </form>
        <form
          className="ws-card ws-form"
          onSubmit={(event) => {
            event.preventDefault();
            void act(async () => {
              const created = await client.createSpace(newSpace);
              setSpaceId(created.id);
              setNewSpace("");
            });
          }}
        >
          <h2>Create another space</h2>
          <p>
            Separate projects or private work. You choose which apps and people
            can use each space.
          </p>
          <Field label="New space name">
            <input
              value={newSpace}
              onChange={(event) => setNewSpace(event.target.value)}
              required
              maxLength={200}
            />
          </Field>
          <button className="ws-button" disabled={busy}>
            Create space
          </button>
        </form>
      </div>
      {newKey && (
        <div className="ws-card ws-new-key" role="status">
          <h2>Save this key now</h2>
          <p>
            Its full value is shown once. Give it only to{" "}
            {options.find((person) => person.id === newKey.principal_id)
              ?.name ?? "the selected identity"}
            .
          </p>
          <div className="ws-code">
            <code>{newKey.api_key}</code>
            <CopyButton text={newKey.api_key} label="Copy API key" />
          </div>
          <button className="ws-button" onClick={() => setNewKey(undefined)}>
            I’ve saved the key
          </button>
        </div>
      )}
      <div className="ws-card">
        <h2>API keys</h2>
        {keys.isPending ? (
          <Busy />
        ) : (
          <div className="ws-table-wrap">
            <table className="ws-table">
              <thead>
                <tr>
                  <th>Key</th>
                  <th>Identity</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {keys.data?.items.map((key) => (
                  <tr key={key.id}>
                    <td>
                      <strong>{key.name}</strong>
                      <small>{key.prefix}…</small>
                    </td>
                    <td>
                      {options.find((person) => person.id === key.principal_id)
                        ?.name ?? "Disabled identity"}
                    </td>
                    <td>
                      {key.revoked_at
                        ? "Revoked"
                        : key.expires_at &&
                            new Date(key.expires_at) < new Date()
                          ? "Expired"
                          : "Active"}
                    </td>
                    <td>
                      {!key.revoked_at &&
                        key.principal_id !== me.principal_id && (
                          <button
                            className="ws-button ws-quiet"
                            disabled={busy}
                            onClick={() => act(() => client.revokeKey(key.id))}
                          >
                            Revoke
                          </button>
                        )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default function Workspace() {
  const [connection, setConnection] = useState<Connection>();
  const [disconnectError, setDisconnectError] = useState<unknown>();
  const queryClient = useMemo(
    () =>
      new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: 10000 } },
      }),
    [connection],
  );
  return (
    <div className="workspace">
      {connection ? (
        <QueryClientProvider client={queryClient}>
          <Shell
            connection={connection}
            disconnect={async () => {
              void queryClient.cancelQueries();
              queryClient.clear();
              setDisconnectError(undefined);
              try { await window.mnemion?.workspaceDisconnect?.(); }
              catch (error) { setDisconnectError(error); }
              setConnection(undefined);
            }}
          />
        </QueryClientProvider>
      ) : (
        <Connect onConnect={setConnection} initialError={disconnectError} />
      )}
    </div>
  );
}
