import type { Layout }   from './store.js'
import type { Baseline } from './formats/baseline.js'
import type { Logger }   from './logger.js'

export interface HeartbeatContext {
  readonly layout:          Layout
  readonly baseline:        Baseline
  readonly logger:          Logger
  readonly cycleCount:      number
  readonly lastHeartbeatTs: string
  readonly inputTokens:     number
  readonly contextWindow:   number   // actual model context window from CPEAdapter
}

export type VitalSeverity = 'degraded' | 'critical'

export type VitalResult =
  | { ok: true }
  | { ok: false; severity: VitalSeverity; message: string }

// A VitalCheck is a pure, stateless check registered with the heartbeat registry.
// Adding a new check = implementing this interface and registering it. Zero changes
// to heartbeat.ts.
export interface VitalCheck {
  readonly name: string
  run(ctx: HeartbeatContext): Promise<VitalResult>
}

export interface HeartbeatResult {
  readonly ts:         string
  readonly cycleCount: number
  readonly inputTokens: number
  readonly budgetPct:  number
  readonly vitals:     ReadonlyArray<{ check: string } & VitalResult>
}

export interface EndureProposal {
  readonly id:          string
  readonly description: string
  readonly ops:         import('./formats/evolution.js').EvolutionOp[]
  readonly digest:      string    // sha256(JSON.stringify(ops)) — matches EVOLUTION_AUTH chain entry
  readonly queuedAt:   string
  readonly approvedAt?: string
}

export interface DriftReport {
  readonly probeId:  string
  readonly layer:    'deterministic' | 'probabilistic'
  readonly score:    number
  readonly exceeds:  boolean
}

export class SILError extends Error {
  constructor(
    message: string,
    public override readonly cause?: unknown,
  ) {
    super(message)
    this.name = 'SILError'
  }
}
