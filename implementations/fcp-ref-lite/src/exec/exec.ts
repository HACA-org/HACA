import { homedir } from 'node:os'
import { resolve } from 'node:path'
import type { Layout } from '../store/layout.js'
import type { Logger } from '../logger/logger.js'
import type { ToolHandler } from '../session/loop.js'
import type { CPEAdapter } from '../cpe/types.js'
import type { ExecContext } from './types.js'
import { createShellRunTool } from './tools/shellRun.js'
import { createWebFetchTool } from './tools/webFetch.js'
import { createFileReadTool } from './tools/fileRead.js'
import { createFileWriteTool } from './tools/fileWrite.js'
import { createWorkerSkillTool } from './tools/workerSkill.js'

export { ExecContext }

const FCP_DIR = resolve(homedir(), '.fcp')

/**
 * Resolve workspace focus from cwd.
 * Returns null if invoked from inside ~/.fcp (no auto-focus).
 */
export function resolveWorkspaceFocus(cwd: string = process.cwd()): string | null {
  const abs = resolve(cwd)
  if (abs === FCP_DIR || abs.startsWith(FCP_DIR + '/')) return null
  return abs
}

/**
 * Create all built-in tool handlers.
 * sessionGrants is shared with the session loop for workerSkill session-scoped approvals.
 */
export function createBuiltinTools(
  layout: Layout,
  logger: Logger,
  ctx: ExecContext,
  adapter: CPEAdapter,
  sessionGrants: Set<string>,
  requestApproval: (prompt: string) => Promise<'once' | 'session' | 'allow' | 'deny'>,
): ToolHandler[] {
  return [
    createShellRunTool(layout, logger, ctx, requestApproval),
    createWebFetchTool(layout, logger, requestApproval),
    createFileReadTool(logger, ctx),
    createFileWriteTool(logger, ctx),
    createWorkerSkillTool(layout, logger, adapter, sessionGrants, requestApproval),
  ]
}
