// Shared workspace_focus resolution for exec tools.
import * as fs from 'node:fs/promises'
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
// Resolves symlinks to prevent bypass via symlink pointing outside workspace.
// For paths that don't exist yet, resolves the nearest existing ancestor.
export async function checkInsideWorkspace(absPath: string, workspace: string): Promise<string | null> {
  try {
    // Resolve workspace root once (it should exist)
    const realWorkspace = await fs.realpath(workspace).catch(() => workspace)
    const wsNorm = realWorkspace.endsWith(path.sep) ? realWorkspace : realWorkspace + path.sep

    // Try to resolve the full path; if it doesn't exist, resolve the nearest existing ancestor
    let realTarget: string
    try {
      realTarget = await fs.realpath(absPath)
    } catch {
      // Path doesn't exist — resolve the parent directory instead
      const dir  = path.dirname(absPath)
      const base = path.basename(absPath)
      const realDir = await fs.realpath(dir).catch(() => dir)
      realTarget = path.join(realDir, base)
    }

    if (!realTarget.startsWith(wsNorm) && realTarget !== realWorkspace) {
      return 'path is outside workspace_focus'
    }
    return null
  } catch {
    // If resolution fails entirely, fall back to string-based check
    const wsNorm = workspace.endsWith(path.sep) ? workspace : workspace + path.sep
    if (!absPath.startsWith(wsNorm) && absPath !== workspace) {
      return 'path is outside workspace_focus'
    }
    return null
  }
}
