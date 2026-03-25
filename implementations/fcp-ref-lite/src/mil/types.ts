export interface EpisodicEntry {
  id: string
  sessionId: string
  ts: string
  content: string
  tags?: string[]
}

export interface SemanticEntry {
  id: string
  ts: string
  content: string
  tags?: string[]
  promotedFrom?: string // episodic entry id
}

export interface WorkingMemoryEntry {
  id: string
  ref: string // path to episodic or semantic file
  layer: 'episodic' | 'semantic'
  summary: string
  ts: string
}

export interface WorkingMemory {
  entries: WorkingMemoryEntry[]
  maxEntries: number
}

export interface SessionHandoff {
  sessionId: string
  ts: string
  message: string // handoff note for next session
}

export interface ClosurePayload {
  ts: string
  sessionId: string
  messageCount: number
  summary: string[]
  workingMemoryUpdates: WorkingMemoryEntry[]
  handoff?: SessionHandoff
  promotions: Array<{ episodicId: string; content: string; tags?: string[] }>
}
