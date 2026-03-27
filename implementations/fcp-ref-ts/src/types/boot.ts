import type { Layout }        from './store.js'
import type { Baseline, ImprintRecord } from './formats/baseline.js'
import type { Logger }         from './logger.js'
import type { CPEAdapter }     from './cpe.js'

export type BootPhaseId = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7

export interface BootContext {
  readonly layout:   Layout
  readonly baseline: Baseline
  readonly imprint:  ImprintRecord
  readonly cpe:      CPEAdapter
  readonly logger:   Logger
}

// A BootPhase is a pure function that mutates nothing outside its contract:
// it reads state, validates it, and throws BootError on failure.
export interface BootPhase {
  readonly id:   BootPhaseId
  readonly name: string
  run(ctx: BootContext): Promise<void>
}

export type BootResult =
  | { ok: true;  sessionId: string }
  | { ok: false; phase: BootPhaseId; reason: string }

export interface FAPOptions {
  readonly layout:        Layout
  readonly operatorName:  string
  readonly operatorEmail: string
  readonly logger:        Logger
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
