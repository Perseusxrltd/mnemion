import { useId, useMemo, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight, Download, Table2 } from "lucide-react";

export const palette = ["#afa4ff", "#64d4c4", "#f1bd73", "#72b9f8", "#f393a3", "#b7ce87"];
export const number = (value: number | null | undefined, digits = 0) => value == null || !Number.isFinite(value)
  ? "—" : new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(value);
export const percent = (value: number | null | undefined) => value == null ? "—" : `${number(value * 100, 1)}%`;
export const bytes = (value: number | null | undefined) => {
  if (value == null) return "—";
  const scale = value > 0 ? Math.min(4, Math.floor(Math.log(value) / Math.log(1024))) : 0;
  return `${number(value / 1024 ** scale, scale ? 1 : 0)} ${["B", "KiB", "MiB", "GiB", "TiB"][scale]}`;
};
export const duration = (ms: number | null | undefined) => ms == null ? "—" : ms < 1000
  ? `${number(ms, ms < 10 ? 1 : 0)} ms` : ms < 60000 ? `${number(ms / 1000, 1)} s` : `${number(ms / 60000, 1)} min`;
export const label = (text: string) => text.replaceAll("_", " ").replace(/\bKiB\b/g, "KiB");
export const when = (text: string | null | undefined) => text ? new Date(text).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—";

export function download(data: BlobPart, name: string, type = "application/json") {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = name; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function Panel({ title, subtitle, children, action, className = "" }: {
  title: string; subtitle?: string; children: ReactNode; action?: ReactNode; className?: string;
}) {
  return <section className={`ins-panel ${className}`}>
    <header><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</header>{children}
  </section>;
}

export function Stat({ title, value, detail, tone = "", icon, children }: {
  title: string; value: ReactNode; detail?: ReactNode; tone?: string; icon?: ReactNode; children?: ReactNode;
}) {
  return <article className={`ins-stat ${tone}`}><div className="ins-stat-label">{title}{icon}</div>
    <strong>{value}</strong>{detail && <p>{detail}</p>}{children}</article>;
}

export function EmptyChart({ children = "No measured samples in this time window." }: { children?: ReactNode }) {
  return <div className="ins-empty-chart"><span aria-hidden="true">···</span><p>{children}</p></div>;
}

export function DataTable({ columns, rows, name }: { columns: string[]; rows: ReactNode[][]; name: string }) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(0);
  const pages = Math.max(1, Math.ceil(rows.length / 50));
  const current = Math.min(page, pages - 1);
  return <div className="ins-chart-table">
    <button className="ws-button ws-quiet" onClick={() => setOpen(!open)} aria-expanded={open}>
      <Table2 size={13} />{open ? "Hide data" : "View data"}<span>{number(rows.length)} rows</span>
    </button>
    {open && <><div className="ws-table-wrap"><table className="ws-table"><caption className="ins-sr-only">{name}</caption>
      <thead><tr>{columns.map((column, index) => <th key={index}>{column}</th>)}</tr></thead>
      <tbody>{rows.slice(current * 50, (current + 1) * 50).map((row, index) => <tr key={current * 50 + index}>{row.map((cell, i) => <td key={i}>{cell}</td>)}</tr>)}</tbody>
    </table></div>{pages > 1 && <div className="ins-pagination">
      <button className="ws-button ws-quiet" disabled={current === 0} onClick={() => setPage(current - 1)} aria-label="Previous chart data page"><ChevronLeft size={16} /></button>
      <span>Page {current + 1} of {pages}</span>
      <button className="ws-button ws-quiet" disabled={current + 1 >= pages} onClick={() => setPage(current + 1)} aria-label="Next chart data page"><ChevronRight size={16} /></button>
    </div>}</>}
  </div>;
}

export interface LineSeries { key: string; label: string; color?: string }
export interface LinePoint { at: string; values: Record<string, number | null | undefined> }

export function TimeChart({ name, points, series, unit, format = v => number(v, 2), since, until, bucketSeconds = 60 }: {
  name: string; points: LinePoint[]; series: LineSeries[]; unit: string;
  format?: (value: number) => string; since?: string; until?: string; bucketSeconds?: number;
}) {
  const id = useId();
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [active, setActive] = useState<number | null>(null);
  const W = 780, H = 240, left = 62, right = 14, top = 20, bottom = 37;
  const data = useMemo(() => [...points].sort((a, b) => +new Date(a.at) - +new Date(b.at)), [points]);
  const visible = series.filter(item => !hidden.has(item.key));
  const minimum = since ? +new Date(since) : data.length ? +new Date(data[0].at) : 0;
  const maximum = until ? +new Date(until) : data.length ? +new Date(data[data.length - 1].at) : minimum + 1;
  const width = W - left - right, height = H - top - bottom;
  const maxValue = Math.max(0, ...data.flatMap(point => visible.map(item => point.values[item.key] ?? 0))) || 1;
  const ymax = maxValue * 1.12;
  const x = (at: string) => left + (+new Date(at) - minimum) / Math.max(1, maximum - minimum) * width;
  const y = (value: number) => top + height - value / ymax * height;
  const selected = active != null && data.length ? Math.min(data.length - 1, active) : null;
  const toggle = (key: string) => setHidden(old => { const next = new Set(old); next.has(key) ? next.delete(key) : next.add(key); return next; });
  if (!data.length) return <EmptyChart />;
  return <div className="ins-time-chart">
    <div className="ins-chart-legend">{series.map((item, i) => <button key={item.key} aria-pressed={!hidden.has(item.key)} onClick={() => toggle(item.key)}>
      <i style={{ background: item.color || palette[i % palette.length] }} />{item.label}</button>)}<span>{unit}</span></div>
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby={`${id}-title ${id}-help`} tabIndex={0}
      onKeyDown={event => { if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) { event.preventDefault(); setActive(event.key === "Home" ? 0 : event.key === "End" ? data.length - 1 : Math.max(0, Math.min(data.length - 1, (selected ?? 0) + (event.key === "ArrowRight" ? 1 : -1)))); } }}
      onPointerMove={event => { const rect = event.currentTarget.getBoundingClientRect(); const px = (event.clientX - rect.left) / rect.width * W;
        let index = 0; for (let i = 1; i < data.length; i++) if (Math.abs(x(data[i].at) - px) < Math.abs(x(data[index].at) - px)) index = i; setActive(index); }}
      onPointerLeave={() => setActive(null)}>
      <title id={`${id}-title`}>{name}</title><desc id={`${id}-help`}>Use left and right arrow keys to inspect samples, or use the data table below. Missing samples are gaps.</desc>
      {Array.from({ length: 5 }, (_, i) => { const value = ymax * i / 4, py = y(value); return <g key={i}>
        <line x1={left} x2={W - right} y1={py} y2={py} className="ins-grid-line" />
        <text x={left - 11} y={py + 4} textAnchor="end" className="ins-axis">{format(value)}</text>
      </g>; })}
      {Array.from({ length: 4 }, (_, i) => { const time = minimum + (maximum - minimum) * i / 3; return <text key={i} x={left + width * i / 3} y={H - 11} textAnchor={i === 0 ? "start" : i === 3 ? "end" : "middle"} className="ins-axis">{new Date(time).toLocaleString(undefined, maximum - minimum > 86400000 ? { month: "short", day: "numeric", hour: "2-digit" } : { hour: "2-digit", minute: "2-digit" })}</text>; })}
      {series.filter(item => !hidden.has(item.key)).map(item => {
        const color = item.color || palette[series.indexOf(item) % palette.length];
        let previous = -Infinity;
        const path = data.map(point => { const value = point.values[item.key], time = +new Date(point.at);
          if (value == null) { previous = -Infinity; return ""; }
          const command = time - previous > bucketSeconds * 1500 ? "M" : "L"; previous = time;
          return `${command}${x(point.at).toFixed(2)},${y(value).toFixed(2)}`;
        }).join(" ");
        return <g key={item.key}><path d={path} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
          {data.map((point, i) => {
            const value = point.values[item.key];
            if (value == null) return null;
            const connected = (neighbor: LinePoint | undefined) => neighbor?.values[item.key] != null
              && Math.abs(+new Date(point.at) - +new Date(neighbor.at)) <= bucketSeconds * 1500;
            // An isolated sample has only a move command in the line path.
            // Keep it visible without drawing a line through unmeasured time.
            if (data.length > 10 && (connected(data[i - 1]) || connected(data[i + 1]))) return null;
            return <circle key={i} cx={x(point.at)} cy={y(value)} r={3} fill={color} />;
          })}</g>;
      })}
      {selected != null && <g><line x1={x(data[selected].at)} x2={x(data[selected].at)} y1={top} y2={top + height} className="ins-crosshair" />
        {visible.map(item => data[selected].values[item.key] == null ? null : <circle key={item.key} cx={x(data[selected].at)} cy={y(data[selected].values[item.key]!)} r={4.5} fill={item.color || palette[series.indexOf(item) % palette.length]} stroke="#161922" strokeWidth={2} />)}</g>}
    </svg>
    <div className="ins-chart-readout" aria-live="polite">{selected == null ? <span>Hover or focus the chart to inspect measured samples.</span> : <><time>{when(data[selected].at)}</time>{visible.map(item => <span key={item.key}>{item.label} <b>{data[selected].values[item.key] == null ? "—" : format(data[selected].values[item.key]!)}</b></span>)}</>}</div>
    <DataTable name={name} columns={["Observed at", ...series.map(item => `${item.label} · ${unit}`)]}
      rows={data.map(point => [when(point.at), ...series.map(item => point.values[item.key] == null ? "—" : format(point.values[item.key]!))])} />
  </div>;
}

export function Bars({ name, values, format = number, total, logarithmic = false }: {
  name: string; values: { label: string; value: number; color?: string; interval?: number[] | null }[];
  format?: (value: number) => string; total?: number; logarithmic?: boolean;
}) {
  if (!values.length) return <EmptyChart />;
  const maximum = Math.max(Number.EPSILON, total ?? Math.max(1, ...values.map(item => Math.max(item.value, item.interval?.[1] ?? 0))));
  const scale = (value: number) => Math.min(100, (logarithmic ? Math.log1p(value) / Math.log1p(maximum) : value / maximum) * 100);
  return <div className="ins-bars" role="group" aria-label={name}>{values.map((item, i) => <div className="ins-bar-row" key={item.label}>
    <span>{item.label}</span><div className="ins-bar-track"><div className="ins-bar-fill" style={{ width: `${scale(item.value)}%`, background: item.color || palette[i % palette.length] }} />
      {item.interval && <div className="ins-bar-interval" title={`95% interval ${format(item.interval[0])} to ${format(item.interval[1])}`} style={{ left: `${scale(item.interval[0])}%`, width: `${scale(item.interval[1]) - scale(item.interval[0])}%` }} />}
    </div><strong>{format(item.value)}</strong>{item.interval && <small>95%: {format(item.interval[0])}–{format(item.interval[1])}</small>}
  </div>)}<DataTable name={name} columns={["Group", "Value", "95% interval"]} rows={values.map(item => [item.label, format(item.value), item.interval ? item.interval.map(format).join(" – ") : "—"])} /></div>;
}

export function Composition({ name, values }: { name: string; values: { label: string; count: number; color?: string }[] }) {
  const total = values.reduce((sum, item) => sum + item.count, 0);
  if (!total) return <EmptyChart>No memories in this distribution yet.</EmptyChart>;
  return <div className="ins-composition"><div className="ins-composition-track" role="img" aria-label={`${name}: ${values.map(item => `${item.label} ${item.count}`).join(", ")}`}>
    {values.filter(item => item.count).map(item => <span key={item.label} title={`${item.label}: ${number(item.count)}`} style={{ flexGrow: item.count, background: item.color || palette[values.indexOf(item) % palette.length] }} />)}
  </div><div className="ins-composition-legend">{values.map((item, i) => <div key={item.label}><i style={{ background: item.color || palette[i % palette.length] }} /><span>{item.label}</span><strong>{number(item.count)}</strong><small>{percent(item.count / total)}</small></div>)}</div></div>;
}

export function Ring({ value, total, title }: { value: number; total: number; title: string }) {
  const ratio = total ? Math.min(1, value / total) : 0;
  return <div className="ins-ring"><svg viewBox="0 0 140 140" role="img" aria-label={`${title}: ${total ? percent(ratio) : "no eligible memories"}`}>
    <circle cx={70} cy={70} r={58} fill="none" stroke="#2b3040" strokeWidth={8} />
    <circle cx={70} cy={70} r={58} fill="none" stroke="#64d4c4" strokeWidth={8} strokeLinecap="round" strokeDasharray={`${ratio * 364.425} 364.425`} transform="rotate(-90 70 70)" />
    <text x={70} y={73} textAnchor="middle" className="ins-ring-value">{total ? percent(ratio) : "—"}</text><text x={70} y={94} textAnchor="middle" className="ins-axis">{title}</text>
  </svg><p>{number(value)} of {number(total)} eligible memories</p></div>;
}

export function ExportButton({ onClick, children = "Export JSON", disabled }: { onClick: () => void; children?: ReactNode; disabled?: boolean }) {
  return <button className="ws-button ws-quiet" onClick={onClick} disabled={disabled}><Download size={14} />{children}</button>;
}
