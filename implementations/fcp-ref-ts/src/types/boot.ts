import type { Layout }                  from './store.js'
import type { Baseline, ImprintRecord } from './formats/baseline.js'
import type { Logger }                  from './logger.js'
import type { CPEMessage }              from './cpe.js'

export type BootPhaseId = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7

// Interface for operator interaction during boot and FAP.
export interface BootIO {
  prompt(question: string): Promise<string>
  write(text: string): void
}

import type { ClosurePayload } from './formats/memory.js'

export interface SleepCycleOpts {
  readonly layout:         Layout
  readonly baseline:       Baseline
  readonly logger:         Logger
  readonly sessionId:      string
  // Present after a normal or compact close; absent on crash recovery.
  readonly closurePayload?: ClosurePayload
  // Model context window — needed by MIL GC to compute compaction target.
  // Only relevant when closurePayload is present and compact was triggered.
  readonly contextWindow:  number
  // Set to true when session ended via compact protocol — triggers MIL GC.
  readonly compact:        boolean
}

// Injected sleep cycle — phases that need it (Phase 2 crash recovery) call this.
export type SleepCycleFn = (opts: SleepCycleOpts) => Promise<void>

export interface BootContext {
  readonly layout:      Layout
  readonly baseline:    Baseline
  readonly imprint:     ImprintRecord
  readonly logger:      Logger
  readonly io:          BootIO
  readonly sleepCycle?: SleepCycleFn
}

// Phase 5 returns contextMessages; Phase 7 returns sessionId.
export interface BootPhasePayload {
  contextMessages?: CPEMessage[]
  sessionId?: string
}

// A BootPhase reads state, validates it, and throws BootError on failure.
// It does not mutate anything outside its documented contract.
export interface BootPhase {
  readonly id:   BootPhaseId
  readonly name: string
  run(ctx: BootContext): Promise<BootPhasePayload | void>
}

export type BootResult =
  | { ok: true;  sessionId: string; contextMessages: CPEMessage[] }
  | { ok: false; phase: BootPhaseId; reason: string }

export interface FAPOptions {
  readonly layout:        Layout
  readonly operatorName:  string
  readonly operatorEmail: string
  readonly logger:        Logger
  readonly io:            BootIO
}

// Options for the boot orchestrator (startEntity).
// operatorName/operatorEmail are only required for cold-start (FAP).
export interface StartEntityOptions {
  readonly layout:         Layout
  readonly logger:         Logger
  readonly io:             BootIO
  readonly sleepCycle?:    SleepCycleFn
  readonly operatorName?:  string
  readonly operatorEmail?: string
}

export type FAPResult =
  | { ok: true;  sessionId: string }
  | { ok: false; step: number; reason: string }

export class BootError extends Error {
  constructor(
    public readonly phase: BootPhaseId,
    message: string,
    public override readonly cause?: unknown,
  ) {
    super(message)
    this.name = 'BootError'
  }
}

export class FAPError extends Error {
  constructor(
    public readonly step: number,
    message: string,
    public override readonly cause?: unknown,
  ) {
    super(message)
    this.name = 'FAPError'
  }
}
