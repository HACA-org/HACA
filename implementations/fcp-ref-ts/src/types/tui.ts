import type { Profile }       from './cli.js'
import type { SessionEvent }  from './session.js'

// TUI consumes SessionEvent directly — no translation layer needed.
export type { SessionEvent }

export type TUIStatus =
  | 'idle'
  | 'thinking'
  | 'waiting_input'
  | 'tool_running'
  | 'closing'

export interface AppMessage {
  readonly role:    'operator' | 'assistant' | 'tool' | 'system'
  readonly content: string
  readonly ts:      string
}

// ─── Dynamic area ─────────────────────────────────────────────────────────────

export type DynamicContentType =
  | 'slash-autocomplete'
  | 'slash-result'
  | 'approval'
  | 'notification'
  | 'file-scope'
  | 'info'

export interface DynamicContent {
  readonly type:       DynamicContentType
  readonly lines:      string[]      // max 5 lines
  readonly expiresAt?: number        // Date.now() + ttlMs; undefined = manual clear
}

// ─── Footer ───────────────────────────────────────────────────────────────────

export interface FooterData {
  readonly workspace:    string
  readonly provider:     string
  readonly model:        string
  readonly cycleNum:     number
  readonly inputTokens:  number
  readonly outputTokens: number
  readonly contextPct:   number      // budgetPct 0-100
  readonly sessionTime:  string      // formatted elapsed "5m 32s"
  readonly sessionId:    string
  readonly status:       TUIStatus
}

// ─── App state ────────────────────────────────────────────────────────────────

export interface AppState {
  readonly status:        TUIStatus
  readonly sessionId:     string
  readonly cycleCount:    number
  readonly inputTokens:   number
  readonly outputTokens:  number
  readonly contextWindow: number     // model context window; 0 = unknown
  readonly budgetPct:     number     // 0-100, relative to contextWindow * 0.95
  readonly profile:       Profile
  readonly messages:      AppMessage[]

  // Extended fields for the new TUI footer/dynamic area
  readonly provider:      string     // e.g. "anthropic"
  readonly model:         string     // e.g. "claude-sonnet-4-20250514"
  readonly workspace:     string     // workspace_focus path or ""
  readonly fcpVersion:    string     // from package.json
  readonly sessionStart:  number     // Date.now() at session start
}

export interface TUIInitOptions {
  readonly sessionId:     string
  readonly profile:       Profile
  readonly contextWindow: number
  readonly provider?:     string
  readonly model?:        string
  readonly workspace?:    string
  readonly fcpVersion?:   string
  readonly headerLines?:  string[]   // lines to render at top of scroll region on init
}

export function initialAppState(opts: TUIInitOptions): AppState {
  return {
    status:        'idle',
    sessionId:     opts.sessionId,
    cycleCount:    0,
    inputTokens:   0,
    outputTokens:  0,
    contextWindow: opts.contextWindow,
    budgetPct:     0,
    profile:       opts.profile,
    messages:      [],
    provider:      opts.provider   ?? '',
    model:         opts.model      ?? '',
    workspace:     opts.workspace  ?? '',
    fcpVersion:    opts.fcpVersion ?? '',
    sessionStart:  Date.now(),
  }
}

// Backwards-compatible overload for existing call sites and tests.
export function initialAppStateLegacy(
  sessionId: string, profile: Profile, contextWindow: number,
): AppState {
  return initialAppState({ sessionId, profile, contextWindow })
}

export function applyEvent(state: AppState, event: SessionEvent): AppState {
  switch (event.type) {
    case 'cycle_start':
      return { ...state, status: 'thinking', cycleCount: event.cycleNum }
    case 'cpe_invoke':
      return { ...state, status: 'thinking' }
    case 'cpe_response':
      return {
        ...state,
        status:   event.toolUses.length > 0 ? 'tool_running' : 'waiting_input',
        messages: [
          ...state.messages,
          { role: 'assistant', content: event.content, ts: new Date().toISOString() },
        ],
      }
    case 'token_update':
      return {
        ...state,
        inputTokens:  event.inputTokens,
        outputTokens: event.outputTokens,
        budgetPct:    event.budgetPct,
      }
    case 'operator_msg':
      return {
        ...state,
        status:   'thinking',
        messages: [
          ...state.messages,
          { role: 'operator', content: event.content, ts: new Date().toISOString() },
        ],
      }
    case 'tool_dispatch':
      return { ...state, status: 'tool_running' }
    case 'tool_result':
      return { ...state, status: 'thinking' }
    case 'session_close':
      return { ...state, status: 'closing' }
    case 'error':
      return { ...state, status: 'idle' }
    case 'workspace_update':
      return { ...state, workspace: event.path }
  }
}
