// Tool dispatch — max 30 lines. No if/elif chains.
import type { ToolUseBlock } from '../types/cpe.js'
import type { ExecContext, ToolResult } from '../types/exec.js'
import type { ToolRegistry } from './registry.js'

export async function dispatch(
  tu:       ToolUseBlock,
  registry: ToolRegistry,
  ctx:      ExecContext,
): Promise<ToolResult> {
  const handler = registry.get(tu.name)
  if (!handler) return { ok: false, error: `Unknown tool: ${tu.name}` }
  try {
    return await handler.execute(tu.input, ctx)
  } catch (e: unknown) {
    return { ok: false, error: `Tool error: ${String(e)}` }
  }
}
