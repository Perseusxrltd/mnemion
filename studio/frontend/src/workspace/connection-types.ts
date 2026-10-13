import type { MnemionClient } from "@mnemion/client";

export type WorkspaceIdentity = Awaited<ReturnType<MnemionClient["me"]>>;
export type Connection = { client: MnemionClient; me: WorkspaceIdentity; endpoint: string; authentication?: 'password'; signOut?: () => Promise<void>; close?: () => void; subscribeClosed?: (listener: () => void) => () => void };
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
};
export type WorkspaceSession = {
  endpoint: string;
  sessionToken: string;
  me: WorkspaceIdentity;
  remembered: boolean;
  bookmarkId?: string;
  authentication?: 'password';
};
export type WorkspaceStatus = {
  secureStorage: boolean;
  activeId: string | null;
  bookmarks: WorkspaceBookmark[];
  active: WorkspaceSession | null;
};
