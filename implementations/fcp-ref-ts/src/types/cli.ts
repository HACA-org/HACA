import type { Topology } from './formats/baseline.js'

export type Profile = 'HACA-Core' | 'HACA-Evolve'

export interface InitOptions {
  readonly entityRoot:    string
  readonly operatorName:  string
  readonly operatorEmail: string
  readonly backend:       string   // format: "<provider>:<model>"
  readonly topology:      Topology
  readonly profile:       Profile
  readonly fallbackTokens: number
  readonly verbose:       boolean
}

// Minimal set of fields the `fcp init` template generator needs.
// The rest (entity_id, timestamps, etc.) are generated at init time.
export interface BaselineTemplate {
  readonly entityId:    string
  readonly backend:     string
  readonly topology:    Topology
  readonly fallbackTokens: number
}

export class CLIError extends Error {
  constructor(
    message: string,
    public readonly exitCode: number = 1,
  ) {
    super(message)
    this.name = 'CLIError'
  }
}
