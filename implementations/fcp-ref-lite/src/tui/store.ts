import { useReducer, useCallback } from 'react'
import type {
  TuiState, ChatEntry, ToolEvent, SessionEvent,
  SidebarState, FooterState, AllowlistPrompt, InputMode,
} from './types.js'

// ─── Actions ──────────────────────────────────────────────────────────────────

type Action =
  | { type: 'SESSION_EVENT'; event: SessionEvent }
  | { type: 'SET_INPUT_MODE'; mode: InputMode }
  | { type: 'SET_ALLOWLIST_PROMPT'; prompt: AllowlistPrompt | null }
  | { type: 'SET_CTRL_C_PENDING'; value: boolean }
  | { type: 'SET_ACTIVE_POPUP'; name: string | null }
  | { type: 'UPDATE_SIDEBAR'; patch: Partial<SidebarState> }

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeId(): string {
  return Math.random().toString(36).slice(2, 10)
}

function updateEntry(entries: ChatEntry[], id: string, patch: Partial<ChatEntry>): ChatEntry[] {
  return entries.map(e => e.id === id ? { ...e, ...patch } : e)
}

function updateToolEvent(entries: ChatEntry[], entryId: string, eventId: string, patch: Partial<ToolEvent>): ChatEntry[] {
  return entries.map(e => {
    if (e.id !== entryId) return e
    return {
      ...e,
      toolEvents: e.toolEvents.map(te => te.id === eventId ? { ...te, ...patch } : te),
    }
  })
}

// ─── Reducer ──────────────────────────────────────────────────────────────────

function applySessionEvent(state: TuiState, event: SessionEvent): TuiState {
  switch (event.type) {
    case 'user_message': {
      const entry: ChatEntry = {
        id: event.id,
        role: 'user',
        text: event.text,
        streaming: false,
        ts: event.ts,
        toolEvents: [],
      }
      return { ...state, entries: [...state.entries, entry] }
    }

    case 'agent_start': {
      const entry: ChatEntry = {
        id: event.id,
        role: 'agent',
        text: '',
        streaming: true,
        ts: event.ts,
        toolEvents: [],
      }
      return { ...state, entries: [...state.entries, entry], footer: { ...state.footer, agentState: 'thinking', activeTool: null } }
    }

    case 'agent_token': {
      const entries = updateEntry(state.entries, event.id, {
        text: (state.entries.find(e => e.id === event.id)?.text ?? '') + event.token,
      })
      return { ...state, entries }
    }

    case 'agent_end': {
      const entries = updateEntry(state.entries, event.id, { text: event.text, streaming: false })
      return { ...state, entries, footer: { ...state.footer, agentState: 'idle', activeTool: null } }
    }

    case 'tool_start': {
      const { entryId, event: toolEvent } = event
      // attach tool event to the agent entry, update footer
      const entries = updateEntry(state.entries, entryId, {
        toolEvents: [...(state.entries.find(e => e.id === entryId)?.toolEvents ?? []), toolEvent],
      })
      return {
        ...state,
        entries,
        footer: { ...state.footer, agentState: 'tool' as const, activeTool: toolEvent.name },
      }
    }

    case 'tool_done': {
      const entries = updateToolEvent(state.entries, event.entryId, event.eventId, event.patch)
      return { ...state, entries, footer: { ...state.footer, agentState: 'thinking' as const, activeTool: null } }
    }

    case 'system_message': {
      const entry: ChatEntry = {
        id: event.id,
        role: 'system',
        text: event.text,
        streaming: false,
        ts: event.ts,
        toolEvents: [],
      }
      return { ...state, entries: [...state.entries, entry] }
    }

    case 'cycle_update':
      return { ...state, footer: { ...state.footer, cycleCount: event.cycleCount } }

    case 'tokens_update':
      return {
        ...state,
        sidebar: {
          ...state.sidebar,
          tokensIn: event.input,
          tokensOut: event.output,
          contextWindow: event.contextWindow,
        },
      }

    case 'session_reset':
      return { ...state, entries: [] }

    case 'stop_requested':
      return { ...state, footer: { ...state.footer, agentState: 'idle' as const, activeTool: null } }

    case 'sleep_start':
      return { ...state, footer: { ...state.footer, agentState: 'sleeping' } }

    case 'sleep_done':
      return { ...state, footer: { ...state.footer, agentState: 'idle' } }

    default:
      return state
  }
}

function reducer(state: TuiState, action: Action): TuiState {
  switch (action.type) {
    case 'SESSION_EVENT':
      return applySessionEvent(state, action.event)
    case 'SET_INPUT_MODE':
      return { ...state, inputMode: action.mode }
    case 'SET_ALLOWLIST_PROMPT':
      return {
        ...state,
        allowlistPrompt: action.prompt,
        inputMode: action.prompt ? 'allowlist' : 'normal',
        footer: { ...state.footer, agentState: action.prompt ? 'awaiting_approval' : state.footer.agentState },
      }
    case 'SET_CTRL_C_PENDING':
      return { ...state, ctrlCPending: action.value }
    case 'SET_ACTIVE_POPUP':
      return { ...state, activePopup: action.name, inputMode: action.name ? 'popup' : 'normal' }
    case 'UPDATE_SIDEBAR':
      return { ...state, sidebar: { ...state.sidebar, ...action.patch } }
    default:
      return state
  }
}

// ─── Initial state factory ────────────────────────────────────────────────────

export function makeInitialState(opts: {
  sessionId: string
  profile: 'haca-core' | 'haca-evolve'
  version: string
  verbose: boolean
  debug: boolean
  model: string
  provider: string
  contextWindow: number
  workspaceFocus: string | null
}): TuiState {
  const sidebar: SidebarState = {
    provider: opts.provider,
    model: opts.model,
    tokensIn: 0,
    tokensOut: 0,
    contextWindow: opts.contextWindow,
    workspaceFocus: opts.workspaceFocus,
    scopeFiles: [],
    inbox: [],
    connections: { cmi: 'offline', mcp: 'offline', gateway: 'offline', pairing: 'offline' },
  }

  const footer: FooterState = {
    agentState: 'idle' as const,
    activeTool: null,
    cycleCount: 0,
    sessionId: opts.sessionId,
    sessionStartTs: new Date().toISOString(),
    verbose: opts.verbose,
    debug: opts.debug,
    profile: opts.profile,
    version: opts.version,
  }

  return {
    entries: [],
    sidebar,
    footer,
    inputMode: 'normal',
    allowlistPrompt: null,
    ctrlCPending: false,
    activePopup: null,
  }
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useTuiStore(initial: TuiState) {
  const [state, dispatch] = useReducer(reducer, initial)

  const dispatchEvent = useCallback((event: SessionEvent) => {
    dispatch({ type: 'SESSION_EVENT', event })
  }, [])

  const setInputMode = useCallback((mode: InputMode) => {
    dispatch({ type: 'SET_INPUT_MODE', mode })
  }, [])

  const setAllowlistPrompt = useCallback((prompt: AllowlistPrompt | null) => {
    dispatch({ type: 'SET_ALLOWLIST_PROMPT', prompt })
  }, [])

  const setCtrlCPending = useCallback((value: boolean) => {
    dispatch({ type: 'SET_CTRL_C_PENDING', value })
  }, [])

  const setActivePopup = useCallback((name: string | null) => {
    dispatch({ type: 'SET_ACTIVE_POPUP', name })
  }, [])

  const updateSidebar = useCallback((patch: Partial<SidebarState>) => {
    dispatch({ type: 'UPDATE_SIDEBAR', patch })
  }, [])

  return { state, dispatchEvent, setInputMode, setAllowlistPrompt, setCtrlCPending, setActivePopup, updateSidebar }
}

export { makeId }
