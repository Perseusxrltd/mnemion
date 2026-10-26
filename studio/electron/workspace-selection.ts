/** One-use local result metadata. It never enters a session, IPC or saved file. */
export type WorkspaceSelection = 'opened' | 'switched'
let results: WeakMap<object, WorkspaceSelection> | undefined

export function markWorkspaceSelection<T extends object>(result: T, selection: WorkspaceSelection): T {
  if (!results) results = new WeakMap()
  results.set(result, selection)
  return result
}

export function takeWorkspaceSelection(result: unknown): WorkspaceSelection | null {
  if (!results || !result || typeof result !== 'object') return null
  const selection = results.get(result)
  results.delete(result)
  return selection ?? null
}
