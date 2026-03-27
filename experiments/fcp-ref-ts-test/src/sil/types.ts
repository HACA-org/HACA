export interface HeartbeatConfig {
  cycleThreshold: number    // default 10
  intervalSeconds: number   // default 300
}

export interface ChainEntry {
  seq: number
  type: ChainEntryType
  ts: string
  prevHash: string | null
  data: Record<string, unknown>
}

export type ChainEntryType =
  | 'GENESIS'
  | 'HEARTBEAT'
  | 'ENDURE_COMMIT'
  | 'CRITICAL'
  | 'SEVERANCE_COMMIT'
  | 'CRITICAL_CLEARED'
  | 'SLEEP_COMPLETE'

export interface PendingProposal {
  id: string
  operation: string
  stagePath?: string       // for installSkill
  description: string
  createdAt: string
  profile: 'haca-core' | 'haca-evolve'
  approvedAt?: string      // set when operator approves
}
