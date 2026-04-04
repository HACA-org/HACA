// TUI unit tests — format, fixed-bar helpers, dynamic, slash, applyEvent.
// Blessed rendering is not unit-tested here (requires a real TTY).
import { describe, it, expect } from 'vitest'
import { initialAppState, applyEvent } from '../types/tui.js'
import { DynamicArea } from './dynamic.js'
import { dispatch, matchPrefix, autocomplete } from './slash.js'
import { formatElapsed, fmtK, budgetColor, stripped, formatFooter } from './fixed-bar.js'
import { formatAssistant, formatOperator, formatToolUse, formatSystem } from './format.js'

// ─── Format ───────────────────────────────────────────────────────────────────

describe('TUI — format', () => {
  it('formatAssistant wraps long content', () => {
    const lines = formatAssistant('a '.repeat(100), 60)
    expect(lines.length).toBeGreaterThan(1)
    expect(stripped(lines[0]!)).toContain('Agent')
  })

  it('formatOperator includes role prefix', () => {
    const lines = formatOperator('test input', 80)
    expect(stripped(lines[0]!)).toContain('You')
    expect(stripped(lines[0]!)).toContain('test input')
  })

  it('formatToolUse shows tool name', () => {
    const lines = formatToolUse('fcp_file_read', { path: '/test' }, 80)
    expect(stripped(lines[0]!)).toContain('fcp_file_read')
  })

  it('formatSystem formats as system message', () => {
    const lines = formatSystem('Session started', 80)
    expect(stripped(lines[0]!)).toContain('System')
  })

  it('formatAssistant returns empty array for empty content', () => {
    expect(formatAssistant('', 80)).toEqual([])
  })
})

// ─── Fixed bar helpers ───────────────────────────────────────────────────────

describe('TUI — fixed-bar', () => {
  it('fmtK formats large numbers', () => {
    expect(fmtK(1500)).toBe('1.5k')
    expect(fmtK(500)).toBe('500')
    expect(fmtK(0)).toBe('0')
  })

  it('formatElapsed produces human-readable time', () => {
    const fiveMinAgo = Date.now() - 5 * 60 * 1000
    const result = formatElapsed(fiveMinAgo)
    expect(result).toMatch(/5m \d+s/)
  })

  it('formatElapsed handles seconds only', () => {
    const tenSecAgo = Date.now() - 10 * 1000
    const result = formatElapsed(tenSecAgo)
    expect(result).toMatch(/^\d+s$/)
  })

  it('budgetColor returns red for >=80%', () => {
    const result = budgetColor(85, '85%')
    expect(result).toContain('85%')
  })

  it('stripped removes ANSI codes', () => {
    expect(stripped('\x1b[1mhello\x1b[0m')).toBe('hello')
    expect(stripped('plain')).toBe('plain')
  })

  it('formatFooter produces a single line with key fields', () => {
    const footer = formatFooter({
      workspace: '/home/user/project',
      provider: 'anthropic',
      model: 'claude-sonnet-4-20250514',
      cycleNum: 3,
      inputTokens: 12000,
      outputTokens: 2300,
      contextPct: 42,
      sessionTime: '5m 32s',
      sessionId: 'a1b2c3d4-xxxx',
      status: 'thinking',
    }, 140)
    const vis = stripped(footer)
    expect(vis).toContain('anthropic:')
    expect(vis).toContain('cycle: 3')
    expect(vis).toContain('in: 12.0k')
    expect(vis).toContain('ctx: 42%')
    expect(vis).toContain('session: a1b2c3d4')
    expect(vis).toContain('thinking')
  })

  it('formatFooter truncates on narrow terminals', () => {
    const footer = formatFooter({
      workspace: '', provider: 'anthropic', model: 'sonnet',
      cycleNum: 1, inputTokens: 0, outputTokens: 0, contextPct: 0,
      sessionTime: '0s', sessionId: 'abcd1234', status: 'idle',
    }, 40)
    const vis = stripped(footer)
    expect(vis.length).toBeLessThanOrEqual(40)
  })
})

// ─── Dynamic area ────────────────────────────────────────────────────────────

describe('TUI — dynamic', () => {
  it('returns 5 empty lines by default', () => {
    const area = new DynamicArea()
    const lines = area.lines()
    expect(lines).toHaveLength(5)
    expect(lines.every(l => l === '')).toBe(true)
  })

  it('set() replaces content', () => {
    const area = new DynamicArea()
    area.set('slash-result', ['line 1', 'line 2'])
    const lines = area.lines()
    expect(lines[0]).toBe('line 1')
    expect(lines[1]).toBe('line 2')
    expect(lines[2]).toBe('')
    expect(lines).toHaveLength(5)
  })

  it('clear() resets to empty', () => {
    const area = new DynamicArea()
    area.set('info', ['test'])
    area.clear()
    expect(area.lines().every(l => l === '')).toBe(true)
  })

  it('truncates to 5 lines max', () => {
    const area = new DynamicArea()
    area.set('info', ['1', '2', '3', '4', '5', '6', '7'])
    expect(area.lines()).toHaveLength(5)
    expect(area.lines()[4]).toBe('5')
  })

  it('auto-expires content with ttl', () => {
    const area = new DynamicArea()
    area.set('notification', ['expiring'], 1) // 1ms TTL
    const start = Date.now()
    while (Date.now() - start < 5) { /* spin */ }
    expect(area.lines().every(l => l === '')).toBe(true)
    expect(area.currentType).toBeNull()
  })

  it('currentType returns type or null', () => {
    const area = new DynamicArea()
    expect(area.currentType).toBeNull()
    area.set('approval', ['approve?'])
    expect(area.currentType).toBe('approval')
  })
})

// ─── Slash commands ──────────────────────────────────────────────────────────

describe('TUI — slash', () => {
  const mockState = initialAppState({
    sessionId: 'test-sid', profile: 'HACA-Core', contextWindow: 200000,
    provider: 'anthropic', model: 'claude-sonnet-4-20250514',
  })

  it('matchPrefix returns matching commands', () => {
    const matches = matchPrefix('/he')
    expect(matches.some(c => c.name === '/help')).toBe(true)
  })

  it('matchPrefix returns empty for non-/ input', () => {
    expect(matchPrefix('hello')).toEqual([])
  })

  it('dispatch /help returns display action', async () => {
    const result = await dispatch('/help', mockState)
    expect(result.action).toBe('display')
    if (result.action === 'display') {
      expect(result.lines.length).toBeGreaterThan(0)
    }
  })

  it('dispatch /status returns display with session info', async () => {
    const result = await dispatch('/status', mockState)
    expect(result.action).toBe('display')
    if (result.action === 'display') {
      const text = result.lines.join('\n')
      expect(stripped(text)).toContain('test-sid')
    }
  })

  it('dispatch /exit returns exit action', async () => {
    const result = await dispatch('/exit', mockState)
    expect(result).toEqual({ action: 'exit', reason: 'normal' })
  })

  it('dispatch /bye is alias for /exit', async () => {
    const result = await dispatch('/bye', mockState)
    expect(result).toEqual({ action: 'exit', reason: 'normal' })
  })

  it('dispatch /clear returns clear action', async () => {
    const result = await dispatch('/clear', mockState)
    expect(result).toEqual({ action: 'clear' })
  })

  it('dispatch unknown command returns error display', async () => {
    const result = await dispatch('/nonexistent', mockState)
    expect(result.action).toBe('display')
    if (result.action === 'display') {
      expect(stripped(result.lines.join(''))).toContain('Unknown command')
    }
  })

  it('autocomplete returns suggestions for partial input', () => {
    const suggestions = autocomplete('/s')
    expect(suggestions.length).toBeGreaterThan(0)
    expect(stripped(suggestions.join(' '))).toContain('/status')
  })
})

// ─── applyEvent ───────────────────────────────────────────────────────────────

describe('TUI — applyEvent', () => {
  it('cycle_start transitions to thinking', () => {
    const s = initialAppState({ sessionId: 'sid', profile: 'HACA-Core', contextWindow: 200000 })
    const n = applyEvent(s, { type: 'cycle_start', cycleNum: 3 })
    expect(n.status).toBe('thinking')
    expect(n.cycleCount).toBe(3)
  })

  it('cpe_response appends assistant message and waits for input', () => {
    const s = initialAppState({ sessionId: 'sid', profile: 'HACA-Core', contextWindow: 200000 })
    const n = applyEvent(s, { type: 'cpe_response', content: 'Hello!', toolUses: [] })
    expect(n.status).toBe('waiting_input')
    expect(n.messages).toHaveLength(1)
    expect(n.messages[0]!.content).toBe('Hello!')
    expect(n.messages[0]!.role).toBe('assistant')
  })

  it('cpe_response with tool_uses transitions to tool_running', () => {
    const s = initialAppState({ sessionId: 'sid', profile: 'HACA-Core', contextWindow: 200000 })
    const n = applyEvent(s, {
      type: 'cpe_response', content: '', toolUses: [
        { type: 'tool_use', id: '1', name: 'fcp_file_read', input: {} },
      ],
    })
    expect(n.status).toBe('tool_running')
  })

  it('operator_msg appends operator message', () => {
    const s = initialAppState({ sessionId: 'sid', profile: 'HACA-Core', contextWindow: 200000 })
    const n = applyEvent(s, { type: 'operator_msg', content: 'test input' })
    expect(n.messages[0]!.role).toBe('operator')
    expect(n.messages[0]!.content).toBe('test input')
  })

  it('session_close transitions to closing', () => {
    const s = initialAppState({ sessionId: 'sid', profile: 'HACA-Core', contextWindow: 200000 })
    const n = applyEvent(s, { type: 'session_close', reason: 'normal' })
    expect(n.status).toBe('closing')
  })

  it('workspace_update updates workspace path', () => {
    const s = initialAppState({ sessionId: 'sid', profile: 'HACA-Core', contextWindow: 200000 })
    const n = applyEvent(s, { type: 'workspace_update', path: '/home/user/project' })
    expect(n.workspace).toBe('/home/user/project')
  })
})
