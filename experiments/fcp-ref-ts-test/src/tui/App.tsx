import { useState, useRef, useCallback } from 'react'
import { Box, Text, useApp, useStdout, useInput, useStdin } from 'ink'
import TextInput from 'ink-text-input'
import type { SessionEvent, ToolEvent, AllowDecision, AllowlistPrompt } from './types.js'

// ─── Types ────────────────────────────────────────────────────────────────────

export type AgentState = 'idle' | 'thinking' | 'tool' | 'sleeping' | 'awaiting_approval'

/** A rendered line of text in the chat area (pre-formatted ANSI) */
interface ChatLine {
  key: string
  text: string
}

interface StatusState {
  provider: string
  model: string
  tokensIn: number
  tokensOut: number
  contextWindow: number
  workspaceFocus: string | null
  agentState: AgentState
  activeTool: string | null
  cycleCount: number
  sessionId: string
  sessionStartTs: string
  profile: 'haca-core' | 'haca-evolve'
  version: string
  ctrlCPending: boolean
}

export interface AppState {
  status: StatusState
  /** All finalized chat lines — virtual-scrolled, never re-rendered */
  lines: ChatLine[]
  /** Accumulated tokens for the current streaming response */
  streamingText: string
  streamingTs: string | null
  isStreaming: boolean
  allowlistPrompt: AllowlistPrompt | null
  inputLocked: boolean
  /** Current scroll offset (lines from top) */
  scrollTop: number
}

export interface AppProps {
  initial: AppState
  onReady: (dispatch: (e: SessionEvent) => void, setAllowlist: (p: AllowlistPrompt | null) => void) => void
  onUserMessage: (text: string) => void
  onStop: () => void
  onExit: (withPayload: boolean) => Promise<void>
}

// ─── ANSI helpers ─────────────────────────────────────────────────────────────

const R = '\x1b[0m'
const b   = (s: string) => `\x1b[1m${s}${R}`
const dim = (s: string) => `\x1b[2m${s}${R}`
const blue    = (s: string) => `\x1b[34m${s}${R}`
const cyan    = (s: string) => `\x1b[36m${s}${R}`
const green   = (s: string) => `\x1b[32m${s}${R}`
const yellow  = (s: string) => `\x1b[33m${s}${R}`
const red     = (s: string) => `\x1b[31m${s}${R}`
const gray    = (s: string) => `\x1b[90m${s}${R}`

function shortTime(iso: string): string {
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function roleHeader(role: 'user' | 'agent' | 'system', ts: string): string {
  const labels  = { user: 'User', agent: 'Entity', system: 'System' }
  const colorFn = { user: blue, agent: green, system: yellow }
  return `${dim(shortTime(ts))} ${colorFn[role](b(labels[role] + ':'))}`
}

const TOOL_ICON: Record<string, string> = {
  pending: dim('○'), running: cyan('⟳'), done: green('✓'),
  error: red('✗'), denied: gray('⊘'), interrupted: gray('⊘'),
}

function toolLine(te: ToolEvent): string {
  const icon   = TOOL_ICON[te.status] ?? '?'
  const detail = te.summary ?? te.filePath ?? te.url ?? te.memorySlug ?? te.error ?? ''
  return `  ${icon} ${cyan(te.name)}${detail ? dim(' ' + detail) : ''}`
}

/** Word-wrap a single line to maxWidth characters */
function wrapLine(line: string, maxWidth: number): string[] {
  if (line.length <= maxWidth) return [line]
  const out: string[] = []
  let remaining = line
  while (remaining.length > maxWidth) {
    // Try to break at a space
    let breakAt = remaining.lastIndexOf(' ', maxWidth)
    if (breakAt <= 0) breakAt = maxWidth
    out.push(remaining.slice(0, breakAt))
    remaining = '  ' + remaining.slice(breakAt).trimStart() // indent continuation
  }
  if (remaining.length > 0) out.push(remaining)
  return out
}

/** Convert a block of text (possibly multi-line) into ChatLines with a given key prefix */
function textToLines(prefix: string, text: string, maxWidth = 200): ChatLine[] {
  const rawLines = text.split('\n')
  const chatLines: ChatLine[] = []
  rawLines.forEach((raw, i) => {
    const wrapped = wrapLine(raw, maxWidth)
    wrapped.forEach((w, j) => chatLines.push({ key: `${prefix}-${i}-${j}`, text: w }))
  })
  return chatLines
}

// ─── Status bar helpers ───────────────────────────────────────────────────────

function tokenBar(used: number, total: number, w = 8): string {
  if (total === 0) return '░'.repeat(w)
  const f = Math.min(w, Math.round((used / total) * w))
  return '█'.repeat(f) + '░'.repeat(w - f)
}

function elapsed(startIso: string): string {
  const s = Math.floor((Date.now() - new Date(startIso).getTime()) / 1000)
  return [Math.floor(s / 3600), Math.floor((s % 3600) / 60), s % 60]
    .map(n => String(n).padStart(2, '0')).join(':')
}

function shortPath(p: string): string {
  const home = process.env['HOME'] ?? ''
  return home ? p.replace(home, '~') : p
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusBar({ s, cols }: { s: StatusState; cols: number }) {
  if (s.ctrlCPending) {
    return (
      <Box flexDirection="column" height={2}>
        <Text color="yellow">⚠ ctrl+c novamente para fechar  <Text dimColor>(sem closure payload)</Text></Text>
        <Text> </Text>
      </Box>
    )
  }

  const totalTok = s.tokensIn + s.tokensOut
  const ctxPct   = s.contextWindow > 0 ? Math.round((totalTok / s.contextWindow) * 100) : 0
  const barColor = ctxPct >= 95 ? 'red' : ctxPct >= 90 ? 'yellow' : 'green'
  const bar      = tokenBar(totalTok, s.contextWindow)
  const workspace = s.workspaceFocus ? shortPath(s.workspaceFocus) : '(none)'

  const stateColor: Record<AgentState, string> = {
    idle: 'green', thinking: 'cyan', tool: 'yellow', sleeping: 'magenta', awaiting_approval: 'red',
  }
  const stateLabel: Record<AgentState, string> = {
    idle: 'idle', thinking: 'thinking',
    tool: `tool:${s.activeTool ?? '?'}`,
    sleeping: 'sleeping', awaiting_approval: '⏸ awaiting',
  }

  // Clamp workspace to available cols
  const wsMax = Math.max(10, cols - 70)

  return (
    <Box flexDirection="column" height={2}>
      {/* Line 1: state · cycle · provider:model · tokens · ctx bar */}
      <Box>
        <Text color={stateColor[s.agentState]}>{stateLabel[s.agentState]}</Text>
        <Text dimColor>  ·  cycle {s.cycleCount}  ·  </Text>
        <Text dimColor>{s.provider}:</Text><Text bold>{s.model}</Text>
        <Text dimColor>  ·  ↑{(s.tokensIn / 1000).toFixed(1)}k ↓{(s.tokensOut / 1000).toFixed(1)}k  ·  </Text>
        <Text color={barColor}>{bar}</Text>
        <Text dimColor>  {ctxPct}%</Text>
      </Box>
      {/* Line 2: workspace · session · elapsed · profile · version */}
      <Box>
        <Text dimColor>⌂ {workspace.slice(0, wsMax)}  ·  {s.sessionId.slice(0, 8)}  ·  {elapsed(s.sessionStartTs)}  ·  </Text>
        <Text color={s.profile === 'haca-core' ? 'blue' : 'magenta'}>{s.profile}</Text>
        <Text dimColor>  ·  v{s.version}</Text>
      </Box>
    </Box>
  )
}

function AllowlistWidget({ prompt }: { prompt: AllowlistPrompt }) {
  const [sel, setSel] = useState(0)
  const opts: Array<{ label: string; value: AllowDecision }> = [
    { label: 'allow once',         value: 'once'    },
    { label: 'allow this session', value: 'session' },
    { label: 'add to allowlist',   value: 'persist' },
    { label: 'deny',               value: 'deny'    },
  ]

  const { isRawModeSupported: rawSupported } = useStdin()
  useInput((_input, key) => {
    if (key.upArrow)   { setSel(s => Math.max(0, s - 1)); return }
    if (key.downArrow) { setSel(s => Math.min(opts.length - 1, s + 1)); return }
    if (key.return)    { prompt.resolve(opts[sel]!.value); return }
    if (key.escape)    { prompt.resolve('deny'); return }
    const n = parseInt(_input, 10)
    if (n >= 1 && n <= opts.length) prompt.resolve(opts[n - 1]!.value)
  }, { isActive: rawSupported ?? true })

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text color="yellow">⚠ allow <Text bold color="cyan">{prompt.toolName}</Text>?</Text>
      {opts.map((o, i) => (
        <Box key={o.value}>
          <Text color={i === sel ? 'cyan' : 'gray'}>{i === sel ? '> ' : '  '}</Text>
          <Text dimColor={i !== sel}>[{i + 1}] {o.label}</Text>
        </Box>
      ))}
    </Box>
  )
}

// ─── App ──────────────────────────────────────────────────────────────────────

export function App({ initial, onReady, onUserMessage, onStop, onExit }: AppProps) {
  const { exit }              = useApp()
  const { stdout }            = useStdout()
  const { isRawModeSupported } = useStdin()
  const cols             = stdout?.columns ?? 120
  const rows             = stdout?.rows    ?? 40

  const [state, setState] = useState<AppState>(initial)
  const [inputValue, setInputValue] = useState('')
  const stateRef = useRef(state)
  stateRef.current = state

  // ── Layout heights ─────────────────────────────────────────────────────────
  // rows = chatArea + streamLine(1) + allowlist(0|4+1) + inputLine(1) + statusBar(2)
  const allowlistHeight = state.allowlistPrompt ? 6 : 0  // header + 4 opts + margin
  const reservedRows    = 1 + allowlistHeight + 1 + 2    // stream + allowlist + input + status
  const chatHeight      = Math.max(3, rows - reservedRows)
  const chatHeightRef   = useRef(chatHeight)
  chatHeightRef.current = chatHeight
  const colsRef         = useRef(cols)
  colsRef.current       = cols

  // ── Expose dispatch once on mount (sync, before first render) ──────────────
  const readyFired = useRef(false)
  if (!readyFired.current) {
    readyFired.current = true
    const dispatch = (event: SessionEvent) =>
      setState(prev => applyEvent(prev, event, chatHeightRef.current, colsRef.current - 4))
    const setAllowlist = (p: AllowlistPrompt | null) => {
      setState(prev => ({
        ...prev,
        allowlistPrompt: p,
        inputLocked: p !== null,
        status: { ...prev.status, agentState: p ? 'awaiting_approval' : prev.status.agentState },
      }))
    }
    onReady(dispatch, setAllowlist)
  }

  // ── Virtual scroll: auto-scroll handled inside the reducer (see applyEvent) ─

  // isRawModeSupported guard — passed to both useInput calls
  // When false (non-TTY), useInput is inactive and Ink won't try to set raw mode
  const rawOpts = { isActive: isRawModeSupported ?? true }

  // ── Keyboard: scroll + ctrl combos ────────────────────────────────────────
  useInput((_input, key) => {
    const s = stateRef.current
    // Scroll (when not in allowlist and not streaming input)
    if (!s.allowlistPrompt && !s.inputLocked) {
      if (key.upArrow) {
        setState(prev => ({ ...prev, scrollTop: Math.max(0, prev.scrollTop - 1) }))
        return
      }
      if (key.downArrow) {
        setState(prev => ({
          ...prev,
          scrollTop: Math.min(Math.max(0, prev.lines.length - chatHeight), prev.scrollTop + 1),
        }))
        return
      }
      if (key.pageUp) {
        setState(prev => ({ ...prev, scrollTop: Math.max(0, prev.scrollTop - chatHeight) }))
        return
      }
      if (key.pageDown) {
        setState(prev => ({
          ...prev,
          scrollTop: Math.min(Math.max(0, prev.lines.length - chatHeight), prev.scrollTop + chatHeight),
        }))
        return
      }
    }

    // Ctrl+X → stop current generation
    if (!s.inputLocked && !s.allowlistPrompt && key.ctrl && _input === 'x') {
      onStop()
      return
    }

    // Ctrl+C → exit with warning
    if (key.ctrl && _input === 'c') {
      if (s.status.ctrlCPending) {
        setState(prev => ({ ...prev, status: { ...prev.status, ctrlCPending: false } }))
        void onExit(false).then(() => exit())
      } else {
        setState(prev => ({ ...prev, status: { ...prev.status, ctrlCPending: true } }))
        setTimeout(() =>
          setState(prev => ({ ...prev, status: { ...prev.status, ctrlCPending: false } })),
          3000,
        )
      }
    }
  }, rawOpts)

  // ── Input submit ───────────────────────────────────────────────────────────
  const handleSubmit = useCallback((text: string) => {
    const t = text.trim()
    if (!t || stateRef.current.inputLocked) return
    setInputValue('')

    if (t === '/exit' || t === '/close') {
      setState(prev => ({ ...prev, inputLocked: true }))
      void onExit(true).then(() => exit())
      return
    }

    onUserMessage(t)
  }, [onUserMessage, onExit, exit])

  // ── Derived render values ──────────────────────────────────────────────────
  const inputDisabled  = state.inputLocked || state.allowlistPrompt !== null
  const visibleLines   = state.lines.slice(state.scrollTop, state.scrollTop + chatHeight)
  const totalLines     = state.lines.length
  const atBottom       = state.scrollTop >= Math.max(0, totalLines - chatHeight)
  const scrollIndicator = !atBottom
    ? dim(`  ↑ ${totalLines - state.scrollTop - chatHeight} more lines  (↑/↓ to scroll)`)
    : ''

  // ── Streaming line (shown below chat, above input) ─────────────────────────
  const streamLine = state.isStreaming
    ? `${dim(shortTime(state.streamingTs ?? new Date().toISOString()))} ${green(b('Entity:'))}  ${state.streamingText}▋`
    : ''

  return (
    <Box flexDirection="column" height={rows}>

      {/* ── Chat area (virtual scroll) ──────────────────────────────────────── */}
      <Box flexDirection="column" height={chatHeight} overflow="hidden">
        {visibleLines.map(line => (
          <Text key={line.key} wrap="truncate">{line.text || ' '}</Text>
        ))}
        {/* Pad remaining rows with blank lines so Box fills its height */}
        {Array.from({ length: Math.max(0, chatHeight - visibleLines.length) }).map((_, i) => (
          <Text key={`pad-${i}`}> </Text>
        ))}
      </Box>

      {/* ── Streaming line ──────────────────────────────────────────────────── */}
      <Box height={1}>
        <Text>{streamLine || scrollIndicator}</Text>
      </Box>

      {/* ── Allowlist prompt (conditional) ─────────────────────────────────── */}
      {state.allowlistPrompt && <AllowlistWidget prompt={state.allowlistPrompt} />}

      {/* ── Input line ──────────────────────────────────────────────────────── */}
      <Box height={1}>
        <Text bold color={inputDisabled ? 'gray' : 'cyan'}>{inputDisabled ? '  ' : '> '}</Text>
        {inputDisabled
          ? <Text dimColor>aguardando...</Text>
          : <TextInput
              value={inputValue}
              onChange={setInputValue}
              onSubmit={handleSubmit}
              placeholder="mensagem ou '/' para comandos"
            />
        }
      </Box>

      {/* ── Status bar (2 fixed lines) ──────────────────────────────────────── */}
      <StatusBar s={state.status} cols={cols} />

    </Box>
  )
}

// ─── Event reducer (pure — called inside setState) ────────────────────────────

function scrollToBottom(state: AppState, chatHeight: number): AppState {
  const maxScroll = Math.max(0, state.lines.length - chatHeight)
  return state.scrollTop < maxScroll ? { ...state, scrollTop: maxScroll } : state
}

function applyEvent(prev: AppState, event: SessionEvent, chatHeight = 9999, chatWidth = 200): AppState {
  switch (event.type) {

    case 'user_message': {
      const newLines: ChatLine[] = [
        { key: `${event.id}-hdr`, text: roleHeader('user', event.ts) },
        ...textToLines(event.id, '  ' + event.text, chatWidth),
        { key: `${event.id}-sep`, text: '' },
      ]
      return scrollToBottom({ ...prev, lines: [...prev.lines, ...newLines] }, chatHeight)
    }

    case 'agent_start':
      return {
        ...prev,
        streamingTs: event.ts,
        streamingText: '',
        isStreaming: true,
        status: { ...prev.status, agentState: 'thinking', activeTool: null },
      }

    case 'agent_token':
      return { ...prev, streamingText: prev.streamingText + event.token }

    case 'agent_end': {
      // Use event.text if non-empty, otherwise fall back to accumulated streaming tokens
      const bodyText  = (event.text && event.text.length > 0) ? event.text : prev.streamingText
      const newLines: ChatLine[] = [
        { key: `${event.id}-hdr`, text: roleHeader('agent', event.ts) },
        ...textToLines(event.id, '  ' + bodyText, chatWidth),
        { key: `${event.id}-sep`, text: '' },
      ]
      const next = {
        ...prev,
        isStreaming: false,
        streamingTs: null,
        streamingText: '',
        lines: [...prev.lines, ...newLines],
        status: { ...prev.status, agentState: 'idle' as AgentState, activeTool: null },
      }
      return scrollToBottom(next, chatHeight)
    }

    case 'tool_start': {
      const te = event.event
      return scrollToBottom({
        ...prev,
        lines: [...prev.lines, { key: `tool-start-${te.id}`, text: toolLine(te) }],
        status: { ...prev.status, agentState: 'tool', activeTool: te.name },
      }, chatHeight)
    }

    case 'tool_done': {
      const patch = event.patch
      if (patch.status && patch.status !== 'running' && patch.status !== 'pending') {
        const fakeTe: ToolEvent = {
          id: event.eventId,
          name: patch.summary ?? patch.name ?? '',
          type: patch.type ?? 'generic',
          status: patch.status,
          ...patch,
        }
        // Replace the tool_start line with the completed line
        const startKey = `tool-start-${event.eventId}`
        const doneKey  = `tool-done-${event.eventId}`
        const lines    = prev.lines.map(l =>
          l.key === startKey ? { key: doneKey, text: toolLine(fakeTe) } : l,
        )
        return {
          ...prev,
          lines,
          status: { ...prev.status, agentState: 'thinking', activeTool: null },
        }
      }
      return { ...prev, status: { ...prev.status, agentState: 'thinking', activeTool: null } }
    }

    case 'system_message': {
      const newLines: ChatLine[] = [
        { key: `${event.id}-hdr`, text: roleHeader('system', event.ts) },
        ...textToLines(event.id, '  ' + event.text, chatWidth),
        { key: `${event.id}-sep`, text: '' },
      ]
      return scrollToBottom({ ...prev, lines: [...prev.lines, ...newLines] }, chatHeight)
    }

    case 'cycle_update':
      return { ...prev, status: { ...prev.status, cycleCount: event.cycleCount } }

    case 'tokens_update':
      return {
        ...prev,
        status: {
          ...prev.status,
          tokensIn: event.input,
          tokensOut: event.output,
          contextWindow: event.contextWindow,
        },
      }

    case 'session_reset':
      return { ...prev, lines: [], streamingText: '', isStreaming: false, scrollTop: 0 }

    case 'stop_requested':
      return { ...prev, status: { ...prev.status, agentState: 'idle', activeTool: null } }

    case 'sleep_start':
      return { ...prev, status: { ...prev.status, agentState: 'sleeping' } }

    case 'sleep_done':
      return { ...prev, status: { ...prev.status, agentState: 'idle' } }

    default:
      return prev
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
}): AppState {
  return {
    status: {
      provider: opts.provider,
      model: opts.model,
      tokensIn: 0,
      tokensOut: 0,
      contextWindow: opts.contextWindow,
      workspaceFocus: opts.workspaceFocus,
      agentState: 'idle',
      activeTool: null,
      cycleCount: 0,
      sessionId: opts.sessionId,
      sessionStartTs: new Date().toISOString(),
      profile: opts.profile,
      version: opts.version,
      ctrlCPending: false,
    },
    lines: [],
    streamingText: '',
    streamingTs: null,
    isStreaming: false,
    allowlistPrompt: null,
    inputLocked: false,
    scrollTop: 0,
  }
}
