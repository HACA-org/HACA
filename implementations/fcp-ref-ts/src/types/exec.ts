import type { Layout }   from './store.js'
import type { Baseline } from './formats/baseline.js'
import type { Logger }   from './logger.js'

export type ToolResult =
  | { ok: true;  output: string }
  | { ok: false; error: string }

export interface ExecContext {
  readonly layout:    Layout
  readonly baseline:  Baseline
  readonly logger:    Logger
  readonly sessionId: string
}

// A ToolHandler is a pure, stateless handler for one named skill.
// It receives raw params (validated internally) and returns a ToolResult.
export interface ToolHandler {
  readonly name: string
  execute(params: unknown, ctx: ExecContext): Promise<ToolResult>
}

// Three-tier session approval policy (§9.8).
export interface AllowlistPolicy {
  isAllowed(skillName: string): boolean
  grant(skillName: string, tier: 'session' | 'persistent'): Promise<void>
}

export class ExecError extends Error {
  constructor(
    public readonly skillName: string,
    message: string,
    public override readonly cause?: unknown,
  ) {
    super(message)
    this.name = 'ExecError'
  }
}
