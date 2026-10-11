import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Box, CirclePause, CirclePlay, Focus, Maximize2, Minimize2, Minus, Plus, RotateCcw, Search } from "lucide-react";
import type { Knowledge, MnemionClient } from "@mnemion/client";
import { filterGraph, kindColors, kindLabels, positionGraph, project, type MapGraph, type MapNode } from "./map-model";
import "./memory-map.css";

export function compactMapDefault(): boolean {
  const ram = (navigator as Navigator & { deviceMemory?: number }).deviceMemory;
  return (ram !== undefined && ram <= 4) || navigator.hardwareConcurrency <= 4;
}
const short = (value: string) => value.slice(0, 8);
const date = (value: string) => new Date(value).toLocaleString();

export default function MemoryMap({ result, client, space, reviewer, administrator, live, setLive, limit, setLimit, checkedAt, refreshing }: {
  result: Knowledge; client: MnemionClient; space: string; reviewer: boolean; administrator: boolean;
  live: boolean; setLive: (value: boolean) => void; limit: number; setLimit: (value: number) => void;
  checkedAt: number; refreshing: boolean;
}) {
  const [mode, setMode] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "2d" : "3d");
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("");
  const [creator, setCreator] = useState("");
  const [hours, setHours] = useState(0);
  const [selected, setSelected] = useState("");
  const [focused, setFocused] = useState(false);
  const shell = useRef<HTMLElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [displayError, setDisplayError] = useState("");
  useEffect(() => {
    const changed = () => setExpanded(document.fullscreenElement === shell.current);
    document.addEventListener("fullscreenchange", changed);
    return () => { document.removeEventListener("fullscreenchange", changed); };
  }, []);
  const graph = useMemo(() => positionGraph(result), [result]);
  const visible = useMemo(() => filterGraph(graph, result, {
    search, kind, creator, since: hours ? checkedAt - hours * 3_600_000 : 0,
    focus: focused ? selected : "", limit: limit <= 60 ? 120 : limit <= 120 ? 300 : 600,
  }), [graph, result, search, kind, creator, hours, checkedAt, focused, selected, limit]);
  const node = visible.nodes.find(item => item.id === selected);
  const creators = useMemo(() => [...new Set(result.memories.map(memory => memory.created_by))].sort(), [result]);
  const identities = useQuery({ queryKey: ["map-identities", client.baseUrl, space],
    queryFn: ({ signal }) => client.request<{ items: import("@mnemion/client").Principal[] }>("GET", "/v1/principals", { signal }),
    enabled: administrator, refetchInterval: live ? 60_000 : false, refetchIntervalInBackground: false,
    refetchOnWindowFocus: live, refetchOnReconnect: live, retry: 0, gcTime: 0,
  });
  const knownIdentities = new Map((identities.error ? [] : identities.data?.items || []).map(identity => [identity.id, identity]));
  function identityName(id: string) { const identity = knownIdentities.get(id); return identity ? `${identity.name} · ${identity.kind === "human" ? "person" : "agent / app"}` : `Identity ${short(id)}`; }
  const recent = useMemo(() => [...result.memories].sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at)), [result]);
  const evidence = node ? result.memories.filter(memory => memory.memory_id === node.memory_id ||
    result.edges.some(edge => (edge.source === node.id && edge.target === "memory:" + memory.memory_id) || (edge.target === node.id && edge.source === "memory:" + memory.memory_id))) : [];
  const activity = useQuery({ queryKey: ["map-activity", client.baseUrl, space],
    queryFn: ({ signal }) => client.request<{ items: import("@mnemion/client").AuditEvent[] }>("GET", `/v1/spaces/${encodeURIComponent(space)}/activity?limit=40`, { signal }),
    enabled: reviewer, refetchInterval: live ? 20_000 : false, refetchIntervalInBackground: false,
    refetchOnWindowFocus: live, refetchOnReconnect: live, retry: 0, gcTime: 0,
  });
  const visibleMemoryIds = new Set(visible.nodes.filter(node => node.kind === "memory").map(node => node.memory_id));
  const events = activity.error ? [] : activity.data?.items.filter(event => visibleMemoryIds.has(event.resource_id) &&
    ["memory.created", "memory.revised", "memory.reviewed"].includes(event.action)).slice(0, 8) || [];

  function choose(id: string) { setSelected(id); }
  return <section ref={shell} className="mm-shell" aria-label="Live memory map">
    <div className="mm-heading"><p>Follow a subject. Trace the evidence. See where work connects.</p>
      <div className="ws-actions"><button className="ws-button" aria-pressed={live} onClick={() => setLive(!live)}>{live ? <CirclePause size={16} /> : <CirclePlay size={16} />}{live ? "Pause live updates" : "Resume live updates"}</button>
      {document.fullscreenEnabled && <button className="ws-button" onClick={async () => { try { if (expanded) await document.exitFullscreen(); else await shell.current?.requestFullscreen(); setDisplayError(""); } catch { setDisplayError("Full-screen mode is unavailable in this window. The map remains usable here."); } }}>{expanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}{expanded ? "Exit full screen" : "Expand map"}</button>}</div></div>
    {displayError && <p role="status" className="ws-helper">{displayError}</p>}
    <div className="mm-controls">
      <label className="ws-field mm-search"><span><Search size={13} /> Find a connection</span><input type="search" value={search} onChange={event => { setSearch(event.target.value); setFocused(false); }} placeholder="A subject, idea, source…" maxLength={200} /></label>
      <label className="ws-field"><span>Show</span><select data-update-safe aria-label="Show" value={kind} onChange={event => setKind(event.target.value)}><option value="">All node types</option>{Object.entries(kindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label className="ws-field"><span>Created by</span><select data-update-safe aria-label="Created by" value={creator} onChange={event => { setCreator(event.target.value); setFocused(false); }}><option value="">All identities</option>{creators.map(id => <option key={id} value={id}>{identityName(id)}</option>)}</select></label>
      <label className="ws-field"><span>Changed</span><select data-update-safe aria-label="Changed" value={hours} onChange={event => setHours(Number(event.target.value))}><option value={0}>Any time</option><option value={1}>Last hour</option><option value={24}>Last day</option><option value={168}>Last week</option></select></label>
      <label className="ws-field"><span>View size</span><select data-update-safe aria-label="View size" value={limit} onChange={event => setLimit(Number(event.target.value))}><option value={60}>Compact · 60 memories</option><option value={120}>Balanced · 120 memories</option><option value={250}>Detailed · 250 memories</option></select></label>
    </div>
    <div className="mm-grid">
      <div className="mm-scene">
        <div className="mm-scene-top"><span className="mm-status"><i className={live ? "live" : ""} />{refreshing ? "Checking for changes…" : live ? "Live · checks every 20s" : "Updates paused"}</span>
          <div className="mm-modes" role="group" aria-label="Map dimensions">{["3d", "2d"].map(value => <button key={value} aria-pressed={mode === value} onClick={() => setMode(value)}>{value === "3d" && <Box size={13} />}{value.toUpperCase()}</button>)}</div></div>
        <MapCanvas graph={visible} mode={mode} selected={node?.id || ""} onSelect={choose} />
        {!visible.nodes.length && <div className="mm-no-results"><h3>No connections in this view</h3><p>Clear a filter or add memories with subjects and source evidence.</p></div>}
        <div className="mm-scene-bottom"><span>{visible.nodes.length} nodes · {visible.edges.length} connections</span><span>Checked {new Date(checkedAt).toLocaleTimeString()}</span></div>
      </div>
      <aside className="mm-inspector" aria-label="Map evidence inspector">
        {node ? <>
          <div className="mm-inspector-label"><span style={{ color: kindColors[node.kind] }}>{kindLabels[node.kind]}</span><button className="ws-icon-button" aria-label="Clear selection" onClick={() => { setSelected(""); setFocused(false); }}>×</button></div>
          <h3>{node.label}</h3><p>{node.degree} recorded connections</p>
          <button className="ws-button" aria-pressed={focused} onClick={() => setFocused(!focused)}><Focus size={15} />{focused ? "Show wider map" : "Focus connections"}</button>
          <div className="mm-evidence">{evidence.slice(0, 8).map(memory => <article key={memory.memory_id}><span className="ws-badge">{memory.claim_status}</span><p>{memory.content.slice(0, 320)}{memory.content.length > 320 ? "…" : ""}</p><small>Revision {memory.version} · {date(memory.updated_at)}<br />Created by {identityName(memory.created_by)}</small><Link to={`/workspace/memory/${memory.memory_id}`}>Open memory & history ↗</Link><Link to={`/workspace/sources/${memory.evidence.source_revision_id}`}>Source: {memory.evidence.title} ↗</Link></article>)}</div>
          {evidence.length > 8 && <p className="ws-helper">Showing 8 of {evidence.length} related memories. Narrow the subject to inspect more.</p>}
        </> : <><p className="ws-eyebrow">Follow a thread</p><h3>Every connection has a source.</h3><p>Select a point to inspect its memories, review status and original evidence.</p>
          <div className="mm-key">{Object.entries(kindLabels).map(([value, label]) => <div key={value}><i style={{ background: kindColors[value as keyof typeof kindColors] }} /><span>{label}</span><strong>{visible.nodes.filter(node => node.kind === value).length}</strong></div>)}</div>
          <p className="mm-trust">Lines mean “about”, “cites” or “in space”. Distance is a visual layout, not a similarity or truth score.</p>
          <h4>Recently changed memories</h4>{recent.filter(memory => visibleMemoryIds.has(memory.memory_id)).slice(0, 5).map(memory => <button key={memory.memory_id} className="mm-recent" onClick={() => choose("memory:" + memory.memory_id)}><span>{memory.subject || memory.content.slice(0, 70)}</span><small>{date(memory.updated_at)} · revision {memory.version}</small></button>)}
        </>}
      </aside>
    </div>
    {(visible.matched > visible.nodes.length || result.truncated) && <p className="ws-notice" role="status">This is a bounded view: {result.memories.length} loaded memories, {visible.nodes.length} of {visible.matched} matching nodes. Narrow the subject or space, or increase the view budget. Hidden nodes and relationships are not counted as absent.</p>}
    <div className="mm-lower">
      <details className="mm-index"><summary>Browse connections as a list · {visible.nodes.length}</summary><p className="ws-helper">Use this list to select any displayed point with the keyboard or without the canvas.</p><div>{visible.nodes.map(item => <button key={item.id} aria-pressed={node?.id === item.id} onClick={() => choose(item.id)}><i style={{ background: kindColors[item.kind] }} /><span>{item.label}</span><small>{kindLabels[item.kind]}</small></button>)}</div></details>
      <section className="mm-activity" aria-label="Recorded memory activity"><h3>Work behind the map</h3><p>Recorded changes in the selected space, linked to visible memories. Identity IDs can represent a person or an agent.</p>
        {!reviewer ? <p className="ws-helper">A reviewer can inspect the activity trail. Your permitted memories and their evidence remain available above.</p> : activity.error ? <p role="status">Activity is unavailable. Refresh your access or try again.</p> : events.length ? <ol>{events.map(event => <li key={event.id}><button onClick={() => choose("memory:" + event.resource_id)}>{event.action.replace("memory.", "Memory ")}</button><span>{identityName(event.principal_id)} · {date(event.created_at)}</span>{event.reason && <small>{event.reason.slice(0, 180)}</small>}</li>)}</ol> : <p className="ws-helper">No matching changes in the latest 40 activity events. This is a recent window, not the full history.</p>}
      </section>
    </div>
  </section>;
}

function MapCanvas({ graph, mode, selected, onSelect }: { graph: MapGraph; mode: string; selected: string; onSelect: (id: string) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const camera = useRef({ yaw: .32, pitch: -.18, zoom: 1 });
  const points = useRef<{ node: MapNode; x: number; y: number; radius: number; z: number }[]>([]);
  const frame = useRef(0);
  const drag = useRef<{ id: number; x: number; y: number; distance: number } | null>(null);
  const [available, setAvailable] = useState(true);
  const draw = useCallback(() => {
    frame.current = 0;
    const element = canvas.current, context = element?.getContext("2d");
    if (!element || !context) return;
    const { width, height } = element.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
    if (element.width !== Math.round(width * ratio) || element.height !== Math.round(height * ratio)) {
      element.width = Math.round(width * ratio); element.height = Math.round(height * ratio);
    }
    context.setTransform(ratio, 0, 0, ratio, 0, 0); context.clearRect(0, 0, width, height);
    if (!graph.nodes.length) { points.current = []; return; }
    const center = graph.nodes.reduce((value, node) => ({ x: value.x + node.x / graph.nodes.length, y: value.y + node.y / graph.nodes.length, z: value.z + node.z / graph.nodes.length }), { x: 0, y: 0, z: 0 });
    const projected = graph.nodes.map(node => ({ node, ...project({ x: node.x - center.x, y: node.y - center.y, z: node.z - center.z }, camera.current, width, height, mode === "2d"), radius: (node.kind === "space" ? 7 : node.kind === "entity" ? 5 : 3.5) }));
    const byId = new Map(projected.map(point => [point.node.id, point]));
    const connected = new Set([selected]);
    graph.edges.forEach(edge => { if (edge.source === selected) connected.add(edge.target); if (edge.target === selected) connected.add(edge.source); });
    for (const edge of graph.edges) {
      const a = byId.get(edge.source)!, b = byId.get(edge.target)!;
      const lit = selected && (edge.source === selected || edge.target === selected);
      context.strokeStyle = lit ? "rgba(226,185,103,.78)" : selected ? "rgba(137,161,187,.09)" : "rgba(137,161,187,.25)";
      context.lineWidth = lit ? 1.5 : .65; context.beginPath(); context.moveTo(a.x, a.y); context.lineTo(b.x, b.y); context.stroke();
    }
    projected.sort((a, b) => b.z - a.z);
    for (const point of projected) {
      const { node, x, y, depth } = point;
      const radius = point.radius * Math.min(depth, 1.8);
      context.globalAlpha = selected && !connected.has(node.id) ? .2 : Math.min(1, .5 + depth * .45);
      context.fillStyle = kindColors[node.kind];
      context.beginPath(); context.arc(x, y, radius, 0, Math.PI * 2); context.fill();
      if (node.id === selected) { context.strokeStyle = "#f2ead9"; context.lineWidth = 1.5; context.beginPath(); context.arc(x, y, radius + 5, 0, Math.PI * 2); context.stroke(); }
      context.globalAlpha = 1;
    }
    const occupied: { x: number; y: number; w: number; h: number }[] = [];
    const labels = projected.filter(point => point.node.id === selected || ((!selected || connected.has(point.node.id)) && ["entity", "space"].includes(point.node.kind)))
      .sort((a, b) => Number(b.node.id === selected) - Number(a.node.id === selected) || b.node.degree - a.node.degree).slice(0, 24);
    for (const { node, x, y, radius } of labels) {
      const label = node.label.length > 29 ? node.label.slice(0, 28) + "…" : node.label;
      context.font = `${node.id === selected ? 600 : 400} 12px Inter, sans-serif`;
      const w = context.measureText(label).width + 8, h = 18;
      const alternatives = [{ x: x + radius + 5, y: y - 9, w, h }, { x: x - radius - w - 5, y: y - 9, w, h }, { x: x - w / 2, y: y - radius - 22, w, h }, { x: x - w / 2, y: y + radius + 8, w, h }];
      const box = alternatives.find(box => box.x >= 5 && box.y >= 46 && box.x + box.w <= width - 5 && box.y + box.h <= height - 5 &&
        !occupied.some(other => box.x < other.x + other.w + 4 && box.x + box.w + 4 > other.x && box.y < other.y + other.h + 4 && box.y + box.h + 4 > other.y));
      if (!box) continue;
      occupied.push(box);
      context.lineWidth = 4; context.strokeStyle = "#090f1c"; context.strokeText(label, box.x + 4, box.y + 13);
      context.fillStyle = node.id === selected ? "#f4ead8" : "#c8d1df"; context.fillText(label, box.x + 4, box.y + 13);
    }
    points.current = projected;
  }, [graph, mode, selected]);
  const schedule = useCallback(() => { if (!frame.current) frame.current = requestAnimationFrame(draw); }, [draw]);
  useEffect(() => {
    if (!canvas.current?.getContext("2d")) { setAvailable(false); return; }
    const observer = new ResizeObserver(schedule); observer.observe(canvas.current);
    schedule(); return () => { observer.disconnect(); cancelAnimationFrame(frame.current); frame.current = 0; };
  }, [schedule]);
  function zoom(change: number) { camera.current.zoom = Math.max(.4, Math.min(3, camera.current.zoom * change)); schedule(); }
  function reset() { camera.current = { yaw: .32, pitch: -.18, zoom: 1 }; schedule(); }
  return <>
    <canvas ref={canvas} className="mm-canvas" tabIndex={0} role="img" aria-label={`${mode === "3d" ? "Three-dimensional" : "Two-dimensional"} memory map with ${graph.nodes.length} nodes. Use the connection list below to select a point.`} aria-describedby="map-controls-help"
      onPointerDown={event => { if (event.button !== 0) return; drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, distance: 0 }; event.currentTarget.setPointerCapture(event.pointerId); }}
      onPointerMove={event => { const start = drag.current; if (!start || start.id !== event.pointerId) return; const dx = event.clientX - start.x, dy = event.clientY - start.y; start.distance += Math.abs(dx) + Math.abs(dy); start.x = event.clientX; start.y = event.clientY; if (mode === "2d") return; camera.current.yaw += dx * .007; camera.current.pitch = Math.max(-1.5, Math.min(1.5, camera.current.pitch + dy * .007)); schedule(); }}
      onPointerCancel={() => { drag.current = null; }}
      onPointerUp={event => { const start = drag.current; drag.current = null; if (!start || start.id !== event.pointerId || start.distance > 6) return; const bounds = event.currentTarget.getBoundingClientRect(), x = event.clientX - bounds.left, y = event.clientY - bounds.top; const hit = [...points.current].reverse().find(point => Math.hypot(x - point.x, y - point.y) < Math.max(12, point.radius + 7)); onSelect(hit?.node.id || ""); }}
      onKeyDown={event => { if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "+", "=", "-", "0"].includes(event.key)) { event.preventDefault(); if (["+", "="].includes(event.key)) zoom(1.15); else if (event.key === "-") zoom(1 / 1.15); else if (event.key === "0") reset(); else { camera.current.yaw += event.key === "ArrowLeft" ? -.15 : event.key === "ArrowRight" ? .15 : 0; camera.current.pitch = Math.max(-1.5, Math.min(1.5, camera.current.pitch + (event.key === "ArrowUp" ? -.15 : event.key === "ArrowDown" ? .15 : 0))); schedule(); } } }}
    >Use the connection list below to explore the same memories and evidence.</canvas>
    {!available && <p className="mm-no-results">Canvas is unavailable. Use the complete connection list below.</p>}
    <div className="mm-camera"><p id="map-controls-help">{mode === "3d" ? "Drag or use arrow keys to orbit · " : "2D · "}Select a point to inspect</p><div><button className="ws-icon-button" onClick={() => zoom(1 / 1.15)} aria-label="Zoom out"><Minus size={16} /></button><button className="ws-icon-button" onClick={() => zoom(1.15)} aria-label="Zoom in"><Plus size={16} /></button><button className="ws-icon-button" onClick={reset} aria-label="Reset map camera"><RotateCcw size={15} /></button></div></div>
  </>;
}
