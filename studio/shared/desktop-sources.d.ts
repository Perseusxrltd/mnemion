export type DesktopSource = {
  id: string; endpoint: string; tenant_id: string; connector_id: string; principal_id: string;
  name: string; provider: 'filesystem' | 'conversations' | 'slack' | 'gdrive'; path?: string; members: string[];
  slack?: { team_id: string; channels: string[]; include_threads: boolean };
  gdrive?: { folder_ids: string[]; file_ids: string[]; recursive: boolean };
  publish_to_mapped_members: true; poll_seconds: number; memory_limit_mib: number; max_files: number; enabled: boolean;
}
export type SourceReport = {
  completed: boolean; timestamp: string; duration_seconds: number; changed: number; removed: number;
  unchanged: number; conflicts: number; remote_sync_available: boolean;
}
export type SourceActivity = {
  phase: 'waiting' | 'scanning' | 'paused' | 'complete' | 'attention';
  message?: string; report?: SourceReport; next_scan_at?: string;
}
export type DesktopSourceView = {
  revision: string; secure_storage: boolean; running: boolean; memory_bytes: number;
  sources: Array<DesktopSource & { activity: SourceActivity }>;
}
export type SourceConfigure = {
  expected_revision: string; source: Omit<DesktopSource, 'id'> & { id?: string }; credential?: string;
  provider_credential?: string;
}
export type SourceControl = { expected_revision: string; id: string; enabled?: boolean; confirm?: boolean }
