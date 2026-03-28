// Shared workspace_focus resolution for exec tools.
import * as path from 'node:path'
import { fileExists, readJson } from '../store/io.js'
import type { ExecContext } from '../types/exec.js'

export async function resolveWorkspace(ctx: ExecContext): Promise<string | null> {
  if (!await fileExists(ctx.layout.state.workspaceFocus)) return null
  try {
    const raw = await readJson(ctx.layout.state.workspaceFocus) as Record<string, unknown>
    const p = typeof raw['path'] === 'string' ? raw['path'].trim() : null
    // Normalize to remove trailing slashes so startsWith check in checkInsideWorkspace is reliable
    return p ? path.normalize(p) : null
  } catch {
    return null
  }
}

// Returns error string if path is outside workspace, null if ok.
export function checkInsideWorkspace(absPath: string, workspace: string): string | null {
  if (!absPath.startsWith(workspace + path.sep) && absPath !== workspace) {
    return 'path is outside workspace_focus'
  }
  return null
}
