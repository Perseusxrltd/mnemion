/** A small local vector mark; no raster scaling or external asset request. */
export default function BrandMark() {
  return <svg className="mn-brand-mark" width="30" height="30" viewBox="0 0 32 32" fill="none" aria-hidden="true">
    <rect x=".5" y=".5" width="31" height="31" rx="4" fill="var(--ink-soft)" stroke="var(--line)" />
    <path d="M8 23V9l8 9 8-9v14" stroke="var(--gold-bright)" strokeWidth="1.6" strokeLinejoin="round" />
    <circle cx="8" cy="23" r="2" fill="var(--gold)" />
    <circle cx="24" cy="23" r="2" fill="var(--gold)" />
    <circle cx="16" cy="18" r="2" fill="var(--ivory)" />
  </svg>;
}
