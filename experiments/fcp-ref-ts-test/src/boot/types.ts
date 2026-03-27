export interface OperatorBound {
  name: string
  email: string
  hash: string // SHA256 of "name<email>"
}

export interface ImprintRecord {
  version: '1.0'
  activatedAt: string // ISO8601
  hacaProfile: 'haca-core' | 'haca-evolve'
  operatorBound: OperatorBound
  structuralBaseline: string // SHA256 of baseline.json at FAP time
  integrityDocument: string  // SHA256 of integrity.json at FAP time
  skillsIndex: string        // SHA256 of skills/index.json at FAP time
  genesisOmega: string       // SHA256 of this imprint (self-referential, computed last)
}

export interface ContextWindowConfig {
  warnPct: number    // default 0.90 — show warning in TUI
  compactPct: number // default 0.95 — SIL triggers compaction
}

export interface BootResult {
  sessionId: string
  isFirstBoot: boolean
  crashRecovered: boolean
  pendingProposals: EvolutionProposal[]
  history: import('../cpe/types.js').Message[]
  contextWindowConfig: ContextWindowConfig
}

export interface EvolutionProposal {
  id: string
  type: string
  description: string
  createdAt: string
}

export class BootError extends Error {
  constructor(message: string, public readonly phase: string) {
    super(`[boot:${phase}] ${message}`)
    this.name = 'BootError'
  }
}

export class FAPError extends Error {
  constructor(message: string, public readonly step: number) {
    super(`[fap:step${step}] ${message}`)
    this.name = 'FAPError'
  }
}
