import type { CapturePreview } from '../../../shared/desktop-sources';

const size = (value: number) => value < 1024 ? `${value} B` : value < 1024 * 1024
  ? `${(value / 1024).toFixed(1)} KiB` : `${(value / (1024 * 1024)).toFixed(1)} MiB`;
const statuses = {
  sampled: 'Prefix sampled', unreadable: 'Could not read', changed: 'Changed during preview',
  too_large: 'Above file limit', record_too_large: 'Above record limit',
  private_control: 'Private control data excluded', invalid_jsonl: 'Invalid JSONL prefix',
};

export default function CapturePreviewPanel({ preview }: { preview: CapturePreview }) {
  return <div className="ws-notice" data-capture-preview="ready">
    <strong>Capture preview</strong>
    <p>{preview.files.length} matching file{preview.files.length === 1 ? '' : 's'} considered · {size(preview.read_bytes)} read · {new Date(preview.observed_at).toLocaleString()}</p>
    <p>{preview.records.selected.toLocaleString()} selected lines · {preview.records.omitted.toLocaleString()} omitted · {preview.records.unsupported.toLocaleString()} unsupported</p>
    {preview.catalog !== 'complete' && <p>{preview.catalog === 'limited' ? 'The preview reached its limit. More selected files may be present.' : 'Part of the folder could not be examined. Collection will report any remaining access problem.'}</p>}
    {!preview.files.length && <p>No matching JSONL file was sampled. Future files matching these rules will be eligible for capture.</p>}
    {preview.files.length > 0 && <ul>{preview.files.map(file => <li key={file.path} style={{ overflowWrap: 'anywhere' }}>
      <strong>{file.path}</strong> — {statuses[file.status]} · {size(file.prefix_bytes)} examined of {size(file.file_bytes)}
    </li>)}</ul>}
    <p className="ws-helper">This is a sample of exposed file prefixes, up to eight files and 1 MiB. Counts can change as sessions grow; duplicate events and later context are reconciled during capture. This preview saves no content and calls no model.</p>
    <p className="ws-helper">Attachments are not read and external links are not followed. Hidden reasoning is unavailable. Field redaction and automatic expiry are not enabled; ordinary message text may contain sensitive information.</p>
    {preview.policy_revision && <details className="ws-details"><summary>Policy identity</summary><code style={{ overflowWrap: 'anywhere' }}>{preview.policy_revision}</code><p className="ws-helper">Each accepted fragment records this policy revision.</p></details>}
  </div>;
}
