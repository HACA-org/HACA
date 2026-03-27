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

export interface AppState {
  readonly status:      TUIStatus
  readonly sessionId:   string
  readonly cycleCount:  number
  readonly inputTokens: number
  readonly budgetPct:   number
  readonly profile:     Profile
  readonly messages:    AppMessage[]
}

export function initialAppState(sessionId: string, profile: Profile): AppState {
  return {
    status:      'idle',
    sessionId,
    cycleCount:  0,
    inputTokens: 0,
    budgetPct:   0,
    profile,
    messages:    [],
  }
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
  }
}
