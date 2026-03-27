// ─── Tool event types ─────────────────────────────────────────────────────────

export type ToolEventType =
  | 'fileRead' | 'fileWrite' | 'shellRun' | 'webFetch'
  | 'memory' | 'workerSkill' | 'skillCreate' | 'skillAudit' | 'generic'

export interface ToolEvent {
  id: string
  type: ToolEventType
  name: string
  status: 'pending' | 'running' | 'done' | 'error' | 'denied' | 'interrupted'
  filePath?: string
  diff?: string
  url?: string
  httpStatus?: number
  memorySlug?: string
  memoryPreview?: string
  summary?: string
  error?: string
}

// ─── Session events ───────────────────────────────────────────────────────────

export type SessionEvent =
  | { type: 'user_message';    id: string; text: string; ts: string }
  | { type: 'agent_start';     id: string; ts: string }
  | { type: 'agent_token';     id: string; token: string }
  | { type: 'agent_end';       id: string; text: string; ts: string }
  | { type: 'tool_start';      entryId: string; event: ToolEvent }
  | { type: 'tool_done';       entryId: string; eventId: string; patch: Partial<ToolEvent> }
  | { type: 'system_message';  id: string; text: string; ts: string }
  | { type: 'cycle_update';    cycleCount: number }
  | { type: 'tokens_update';   input: number; output: number; contextWindow: number }
  | { type: 'session_reset' }
  | { type: 'stop_requested' }
  | { type: 'sleep_start' }
  | { type: 'sleep_done' }

// ─── Allowlist approval ───────────────────────────────────────────────────────

export type AllowDecision = 'once' | 'session' | 'persist' | 'deny'

export interface AllowlistPrompt {
  toolName: string
  toolInput: Record<string, unknown>
  resolve: (decision: AllowDecision) => void
}
