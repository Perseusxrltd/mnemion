import type { MnemionClient, RecoveryDirectoryRecord } from "@mnemion/client";

export type WorkspaceIdentity = Awaited<ReturnType<MnemionClient["me"]>>;
export type Connection = { client: MnemionClient; me: WorkspaceIdentity; endpoint: string; authentication?: 'password' | 'company'; signOut?: () => Promise<void>; close?: () => void; subscribeClosed?: (listener: () => void) => () => void; refreshRecovery?: () => Promise<WorkspaceInspection> };
export type WorkspaceBookmark = {
  id: string;
  endpoint: string;
  label: string;
  principalName: string;
  principalId: string;
  tenantId: string;
  updatedAt: string;
};
export type WorkspaceInspection = {
  bookmark: WorkspaceBookmark;
  access: { identity: Pick<WorkspaceIdentity, 'tenant_id' | 'principal_id' | 'tenant_name' | 'name' | 'administrator'>; verifiedAt: string } | null;
  accessStatus: 'recorded' | 'not-recorded' | 'locked' | 'unavailable';
  recovery?: { record: RecoveryDirectoryRecord; savedAt: string } | null;
  recoveryStatus?: 'recorded' | 'unavailable';
};
export type WorkspaceSession = {
  endpoint: string;
  sessionToken: string;
  me: WorkspaceIdentity;
  remembered: boolean;
  bookmarkId?: string;
  authentication?: 'password' | 'company';
};
export type WorkspaceStatus = {
  secureStorage: boolean;
  activeId: string | null;
  bookmarks: WorkspaceBookmark[];
  active: WorkspaceSession | null;
};
