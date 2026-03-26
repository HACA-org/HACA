// ─── Tool event types (emitted by loop, rendered in chat) ────────────────────

export type ToolEventType =
  | 'fileRead'
  | 'fileWrite'
  | 'shellRun'
  | 'webFetch'
  | 'memory'
  | 'workerSkill'
  | 'skillCreate'
  | 'skillAudit'
  | 'generic'

export interface ToolEvent {
  id: string
  type: ToolEventType
  name: string        // raw tool name
  status: 'pending' | 'running' | 'done' | 'error' | 'denied' | 'interrupted'
  // tool-specific payloads
  filePath?: string
  diff?: string        // unified diff string for fileWrite
  url?: string         // webFetch
  httpStatus?: number  // webFetch
  memorySlug?: string  // memory write
  memoryPreview?: string // first ~120 chars
  summary?: string     // generic one-liner (shellRun output preview, etc.)
  error?: string
}

// ─── Chat entries ─────────────────────────────────────────────────────────────

export type ChatRole = 'user' | 'agent' | 'system'

export interface ChatEntry {
  id: string
  role: ChatRole
  text: string         // may be partial while streaming
  streaming: boolean
  ts: string           // ISO8601
  toolEvents: ToolEvent[]
}

// ─── Session events (emitted by loop → TUI store) ────────────────────────────

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

// ─── Sidebar state ────────────────────────────────────────────────────────────

export interface ScopeFile {
  path: string
  op: 'R' | 'W' | 'RW'
}

export interface InboxItem {
  id: string
  read: boolean
  text: string
  source: string
  ts: string
}

export interface ConnectionState {
  cmi:     'online' | 'offline'
  mcp:     'online' | 'offline'
  gateway: 'online' | 'offline'
  pairing: 'online' | 'offline'
  mcpClientCount?: number
}

export interface SidebarState {
  provider: string
  model: string
  tokensIn: number
  tokensOut: number
  contextWindow: number
  workspaceFocus: string | null
  scopeFiles: ScopeFile[]
  inbox: InboxItem[]
  connections: ConnectionState
}

// ─── Footer state ─────────────────────────────────────────────────────────────

export type AgentState = 'idle' | 'thinking' | 'tool' | 'sleeping' | 'awaiting_approval'

export interface FooterState {
  agentState: AgentState
  activeTool: string | null
  cycleCount: number
  sessionId: string
  sessionStartTs: string   // ISO8601 — elapsed computed at render time
  verbose: boolean
  debug: boolean
  profile: 'haca-core' | 'haca-evolve'
  version: string
}

// ─── Input zone state ─────────────────────────────────────────────────────────

export type InputMode = 'normal' | 'slash' | 'allowlist' | 'popup' | 'locked'

// ─── Global TUI state ─────────────────────────────────────────────────────────

export interface TuiState {
  entries: ChatEntry[]
  sidebar: SidebarState
  footer: FooterState
  inputMode: InputMode
  allowlistPrompt: AllowlistPrompt | null
  ctrlCPending: boolean         // first ctrl+c pressed, waiting for second
  activePopup: string | null    // name of open popup, e.g. 'inbox', 'model'
}
