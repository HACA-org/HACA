import type { Layout }   from './store.js'
import type { Baseline } from './formats/baseline.js'
import type { Logger }   from './logger.js'

export type ToolResult =
  | { ok: true;  output: string }
  | { ok: false; error: string }

// Minimal IO surface needed by exec tools for approval gating.
// Structural subset of SessionIO — avoids circular import with session.ts.
export interface GateIO {
  prompt(): Promise<string>
  write(text: string): void
}

// Three-namespace allowlist policy (§9.8).
// Backed by state/allowlist.json; mutable during session via add* methods.
export interface AllowlistPolicy {
  readonly commands: string[]
  readonly domains:  string[]
  readonly skills:   string[]
  addCommand(cmd: string,    tier: 'session' | 'persistent'): Promise<void>
  addDomain(domain: string,  tier: 'session' | 'persistent'): Promise<void>
  addSkill(skill: string,    tier: 'session' | 'persistent'): Promise<void>
}

export interface ExecContext {
  readonly layout:         Layout
  readonly baseline:       Baseline
  readonly logger:         Logger
  readonly sessionId:      string
  readonly sessionMode:    'main' | 'auto'
  readonly policy:         AllowlistPolicy
  readonly io:             GateIO
  readonly firstWriteDone: { value: boolean }
}

// A ToolHandler is a pure, stateless handler for one named tool.
// It receives raw params (validated internally) and returns a ToolResult.
export interface ToolHandler {
  readonly name:         string
  readonly description:  string                    // passed to CPE tool declaration
  readonly inputSchema:  Record<string, unknown>   // JSON Schema — passed as input_schema
  execute(params: unknown, ctx: ExecContext): Promise<ToolResult>
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
