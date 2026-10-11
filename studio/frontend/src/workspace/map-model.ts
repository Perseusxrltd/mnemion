import type { Knowledge, KnowledgeNode } from "@mnemion/client";

export type Point = { x: number; y: number; z: number };
export type MapNode = KnowledgeNode & Point & { degree: number };
export type MapGraph = { nodes: MapNode[]; edges: Knowledge["edges"]; matched: number };
export const kindColors = { space: "#e2b967", entity: "#98bde5", memory: "#80d5b9", source: "#baa5e0" };
export const kindLabels = { space: "Space", entity: "Subject / idea", memory: "Memory", source: "Source" };

function hash(value: string): number {
  let result = 2166136261;
  for (let i = 0; i < value.length; i++) result = Math.imul(result ^ value.charCodeAt(i), 16777619);
  return (result >>> 0) / 4294967296;
}
function offset(key: string, radius: number): Point {
  const theta = hash(key) * Math.PI * 2;
  const z = hash(key + "/depth") * 2 - 1;
  const r = Math.sqrt(1 - z * z) * radius;
  return { x: Math.cos(theta) * r, y: Math.sin(theta) * r, z: z * radius };
}
function plus(a: Point, b: Point): Point { return { x: a.x + b.x, y: a.y + b.y, z: a.z + b.z }; }
function average(points: Point[]): Point {
  if (!points.length) return { x: 0, y: 0, z: 0 };
  return points.reduce((result, point) => plus(result, { x: point.x / points.length, y: point.y / points.length, z: point.z / points.length }), { x: 0, y: 0, z: 0 });
}

/** Deterministic geometry only. Every displayed relationship comes from the service. */
export function positionGraph(result: Knowledge): MapGraph {
  const nodes = new Map(result.nodes.map(node => [node.id, node]));
  const neighbors = new Map<string, string[]>();
  const edges = result.edges.filter(edge => nodes.has(edge.source) && nodes.has(edge.target));
  for (const edge of edges) {
    neighbors.set(edge.source, [...(neighbors.get(edge.source) || []), edge.target]);
    neighbors.set(edge.target, [...(neighbors.get(edge.target) || []), edge.source]);
  }
  const points = new Map<string, Point>();
  // Fixed identity-derived anchors keep unchanged nodes in place across live snapshots.
  const anchor = (node: KnowledgeNode) => offset(node.space_id, 130);
  for (const node of result.nodes) {
    if (node.kind === "space") points.set(node.id, anchor(node));
    if (node.kind === "entity") points.set(node.id, plus(anchor(node), offset(node.id, 150)));
  }
  for (const node of result.nodes.filter(node => node.kind === "memory")) {
    const subjects = (neighbors.get(node.id) || []).filter(id => nodes.get(id)?.kind === "entity").map(id => points.get(id)!);
    points.set(node.id, plus(subjects.length ? average(subjects) : anchor(node), offset(node.id, subjects.length ? 46 : 115)));
  }
  for (const node of result.nodes.filter(node => node.kind === "source")) {
    const memories = (neighbors.get(node.id) || []).filter(id => nodes.get(id)?.kind === "memory").map(id => points.get(id)!);
    points.set(node.id, plus(memories.length ? average(memories) : anchor(node), offset(node.id, 32)));
  }
  return { nodes: result.nodes.map(node => ({ ...node, ...points.get(node.id)!, degree: neighbors.get(node.id)?.length || 0 })), edges, matched: nodes.size };
}

export function filterGraph(graph: MapGraph, result: Knowledge, options: {
  search: string; kind: string; creator: string; since: number; focus: string; limit: number;
}): MapGraph {
  const memoryIds = new Set(result.memories.filter(memory => (!options.creator || memory.created_by === options.creator) &&
    (!options.since || Date.parse(memory.updated_at) >= options.since)).map(memory => "memory:" + memory.memory_id));
  const scoped = new Set(memoryIds);
  for (const edge of graph.edges) {
    if (memoryIds.has(edge.source)) scoped.add(edge.target);
    if (memoryIds.has(edge.target)) scoped.add(edge.source);
  }
  const words = options.search.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const matches = new Set(graph.nodes.filter(node => scoped.has(node.id) && words.every(word => node.label.toLocaleLowerCase().includes(word))).map(node => node.id));
  let allowed = scoped;
  const center = options.focus && scoped.has(options.focus) ? new Set([options.focus]) : words.length ? matches : null;
  if (center) {
    allowed = new Set(center);
    for (const edge of graph.edges) {
      if (center.has(edge.source) && scoped.has(edge.target)) allowed.add(edge.target);
      if (center.has(edge.target) && scoped.has(edge.source)) allowed.add(edge.source);
    }
  }
  const candidates = graph.nodes.filter(node => allowed.has(node.id) && (!options.kind || node.kind === options.kind));
  const priority = (node: MapNode) => node.id === options.focus ? 1e9 : words.length && matches.has(node.id) ? 1e6 : node.degree;
  candidates.sort((a, b) => priority(b) - priority(a) || a.id.localeCompare(b.id));
  const budget = Math.max(1, Math.min(600, Math.floor(options.limit) || 120));
  // Reserve room for each kind, then use remaining room; hubs cannot crowd out all evidence.
  const picked = new Set<string>();
  for (const kind of ["space", "entity", "memory", "source"]) {
    for (const node of candidates.filter(node => node.kind === kind).slice(0, Math.floor(budget / 4))) picked.add(node.id);
  }
  if (candidates.some(node => node.id === options.focus)) picked.add(options.focus);
  for (const node of candidates) { if (picked.size >= budget) break; picked.add(node.id); }
  const visible = candidates.filter(node => picked.has(node.id)).slice(0, budget);
  const ids = new Set(visible.map(node => node.id));
  return { nodes: visible, edges: graph.edges.filter(edge => ids.has(edge.source) && ids.has(edge.target)), matched: candidates.length };
}

export function project(point: Point, camera: { yaw: number; pitch: number; zoom: number }, width: number, height: number, flat = false) {
  const x = flat ? point.x : point.x * Math.cos(camera.yaw) + point.z * Math.sin(camera.yaw);
  const rotatedZ = -point.x * Math.sin(camera.yaw) + point.z * Math.cos(camera.yaw);
  const y = flat ? point.y : point.y * Math.cos(camera.pitch) - rotatedZ * Math.sin(camera.pitch);
  const z = flat ? 0 : point.y * Math.sin(camera.pitch) + rotatedZ * Math.cos(camera.pitch);
  const depth = flat ? 1 : 780 / Math.max(240, 780 + z);
  const scale = Math.min(width, height) / 520 * camera.zoom * depth;
  return { x: width / 2 + x * scale, y: height / 2 + y * scale, z, depth };
}
