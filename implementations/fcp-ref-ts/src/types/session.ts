import type { Layout }        from './store.js'
import type { Baseline }      from './formats/baseline.js'
import type { ClosurePayload } from './formats/memory.js'
import type { CPEAdapter, ToolUseBlock } from './cpe.js'
import type { Logger }        from './logger.js'
import type { AllowlistPolicy, ToolHandler, ToolResult } from './exec.js'

export type CloseReason =
  | 'normal'
  | 'budget_critical'
  | 'critical_condition'
  | 'operator_forced'

// Internal events emitted by the session loop; consumed by the TUI.
export type SessionEvent =
  | { type: 'cycle_start';   cycleNum: number }
  | { type: 'cpe_invoke' }
  | { type: 'cpe_response';  content: string; toolUses: ToolUseBlock[] }
  | { type: 'tool_dispatch'; skillName: string; input: unknown }
  | { type: 'tool_result';   skillName: string; result: ToolResult }
  | { type: 'operator_msg';  content: string }
  | { type: 'session_close'; reason: CloseReason }
  | { type: 'error';         error: unknown }

// Per-cycle bookkeeping; never escapes the loop module.
export interface CycleState {
  cycleNum:    number
  inputTokens: number   // last authoritative count from CPE, 0 before first cycle
  fingerprint: string   // loop-detection hash of last CPE output
}

export type AllowDecision =
  | { granted: true;  tier: 'one-time' | 'session' | 'persistent' }
  | { granted: false }

// IO surface the session loop uses — injected, never imported directly.
export interface SessionIO {
  prompt(): Promise<string>
  write(text: string): void
  emit(event: SessionEvent): void
}

export interface SessionOptions {
  readonly layout:     Layout
  readonly baseline:   Baseline
  readonly cpe:        CPEAdapter
  readonly policy:     AllowlistPolicy
  readonly tools:      ToolHandler[]
  readonly logger:     Logger
  readonly io:         SessionIO
  readonly sessionId:  string
  readonly profile:    'HACA-Core' | 'HACA-Evolve'
  // Initial messages from boot context assembly (Phase 5).
  readonly contextMessages?: import('./cpe.js').CPEMessage[]
}

export type LoopResult =
  | { closed: 'normal';  closurePayload: ClosurePayload }
  | { closed: 'forced';  reason: CloseReason }
  | { closed: 'error';   error: unknown }
