import type { WorkingMemory } from './formats/memory.js'

export interface EpisodicEntry {
  path:      string
  ts:        string
  sessionId: string
  sizeBytes: number
}

export interface SemanticEntry {
  slug: string
  path: string
  ts:   string
}

export interface RecallMatch {
  source:    'episodic' | 'semantic' | 'working'
  path:      string
  relevance: number   // 0–1; higher = more relevant
}

export type RecallResult =
  | { found: true;  matches: RecallMatch[] }
  | { found: false }

// MIL is the exclusive writer to memory/. All writes go through this interface.
export interface MemoryStore {
  recall(query: string): Promise<RecallResult>
  writeEpisodic(slug: string, content: string): Promise<EpisodicEntry>
  writeSemantic(slug: string, content: string): Promise<SemanticEntry>
  promoteSlugs(slugs: string[]): Promise<void>
  getWorkingMemory(): Promise<WorkingMemory>
  setWorkingMemory(wm: WorkingMemory): Promise<void>
}

export class MILError extends Error {
  constructor(
    message: string,
    public override readonly cause?: unknown,
  ) {
    super(message)
    this.name = 'MILError'
  }
}
