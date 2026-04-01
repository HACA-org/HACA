// TUI unit tests — renderer primitives, layout, format, fixed-bar, dynamic, slash, applyEvent.
import { describe, it, expect } from 'vitest'
import { moveTo, eraseToEOL, bold, dim, color, C_CYAN, writeLine,
         setScrollRegion, resetScrollRegion } from './renderer.js'
import { computeLayout, chatLines, MIN_ROWS } from './layout.js'
import { initialAppState, applyEvent } from '../types/tui.js'
import type { Output } from './renderer.js'
import { DynamicArea } from './dynamic.js'
import { dispatch, matchPrefix, autocomplete } from './slash.js'
import { formatElapsed, fmtK, budgetColor, stripped, formatFooter } from './fixed-bar.js'
import { formatAssistant, formatOperator, formatToolUse, formatSystem } from './format.js'
import { appendLine } from './scroll-writer.js'

function makeOutput(cols: number, rows: number): Output & { written: string[] } {
  const written: string[] = []
  return {
    write: (s) => { written.push(s) },
    get columns() { return cols },
    get rows()    { return rows },
    written,
  }
}

// ─── Renderer primitives ──────────────────────────────────────────────────────

describe('TUI — renderer', () => {
  it('moveTo generates correct escape sequence', () => {
    expect(moveTo(5, 10)).toBe('\x1b[5;10H')
  })

  it('eraseToEOL generates correct escape sequence', () => {
    expect(eraseToEOL()).toBe('\x1b[K')
  })

  it('bold wraps text in ANSI bold codes', () => {
    const result = bold('hello')
    expect(result).toMatch(/hello/)
    expect(result).toMatch(/\x1b\[1m/)
  })

  it('dim wraps text in ANSI dim codes', () => {
    const result = dim('hello')
    expect(result).toMatch(/hello/)
  })

  it('color wraps text in ANSI color codes', () => {
    expect(color('hi', C_CYAN)).toContain('36m')
  })

  it('writeLine truncates long text', () => {
    const out = makeOutput(20, 10)
    writeLine(out, 1, 'This is a very long string that exceeds width')
    const joined = out.written.join('')
    expect(joined).toContain('…')
  })

  it('setScrollRegion generates DECSTBM sequence', () => {
    expect(setScrollRegion(1, 15)).toBe('\x1b[1;15r')
  })

  it('resetScrollRegion generates reset sequence', () => {
    expect(resetScrollRegion()).toBe('\x1b[r')
  })
})

// ─── Layout ───────────────────────────────────────────────────────────────────

describe('TUI — layout', () => {
  it('computeLayout allocates 9 fixed rows at bottom', () => {
    const out    = makeOutput(80, 24)
    const layout = computeLayout(out)
    expect(layout.scrollTop).toBe(1)
    expect(layout.scrollBottom).toBe(15)    // 24 - 9
    expect(layout.sepAboveInput).toBe(16)   // 24 - 8
    expect(layout.inputRow).toBe(17)        // 24 - 7
    expect(layout.sepBelowInput).toBe(18)   // 24 - 6
    expect(layout.footerRow).toBe(19)       // 24 - 5
    expect(layout.dynamicStart).toBe(20)    // 24 - 4
    expect(layout.dynamicEnd).toBe(24)      // 24
  })

  it('chatLines returns scroll region height', () => {
    const out    = makeOutput(80, 24)
    const layout = computeLayout(out)
    expect(chatLines(layout)).toBe(15)      // scrollBottom - scrollTop + 1
  })

  it('enforces minimum dimensions', () => {
    const out    = makeOutput(10, 10)
    const layout = computeLayout(out)
    expect(layout.rows).toBeGreaterThanOrEqual(MIN_ROWS)
    expect(layout.scrollBottom).toBeGreaterThan(0)
  })

  it('dynamic area has exactly 5 rows', () => {
    const out    = makeOutput(80, 30)
    const layout = computeLayout(out)
    expect(layout.dynamicEnd - layout.dynamicStart + 1).toBe(5)
  })
})

// ─── Scroll writer ───────────────────────────────────────────────────────────

describe('TUI — scroll-writer', () => {
  it('appendLine emits moveTo + newline + eraseLine + content', () => {
    const out = makeOutput(80, 24)
    appendLine(out, 15, 'Hello world')
    const joined = out.written.join('')
    expect(joined).toContain('\x1b[15;1H')   // moveTo(15,1)
    expect(joined).toContain('\n')
    expect(joined).toContain('\x1b[2K')      // eraseLine
    expect(joined).toContain('Hello world')
  })
})

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
      profile: 'HACA-Core',
      fcpVersion: '1.0.0',
      status: 'thinking',
    }, 120)
    const vis = stripped(footer)
    expect(vis).toContain('anthropic')
    expect(vis).toContain('#3')
    expect(vis).toContain('12.0k')
    expect(vis).toContain('42%')
    expect(vis).toContain('a1b2c3d4')
    expect(vis).toContain('Core')
  })

  it('formatFooter truncates on narrow terminals', () => {
    const footer = formatFooter({
      workspace: '', provider: 'anthropic', model: 'sonnet',
      cycleNum: 1, inputTokens: 0, outputTokens: 0, contextPct: 0,
      sessionTime: '0s', sessionId: 'abcd1234', profile: 'HACA-Core',
      fcpVersion: '1.0.0', status: 'idle',
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
    // Wait for expiry
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
