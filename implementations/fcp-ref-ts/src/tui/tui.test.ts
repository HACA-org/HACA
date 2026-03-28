// TUI unit tests — renderer primitives, layout, history, status, applyEvent.
// Does NOT test TTY rendering (no real TTY in test environment).
import { describe, it, expect } from 'vitest'
import { moveTo, eraseToEOL, bold, dim, color, C_CYAN, writeLine } from './renderer.js'
import { computeLayout, chatLines } from './layout.js'
import { renderHistory } from './history.js'
import { initialAppState, applyEvent } from '../types/tui.js'
import type { AppMessage } from '../types/tui.js'
import type { Output } from './renderer.js'

function makeOutput(cols: number, rows: number): Output {
  const written: string[] = []
  return {
    write: (s) => { written.push(s) },
    get columns() { return cols },
    get rows()    { return rows },
    written,
  } as Output & { written: string[] }
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
    const joined = (out as unknown as { written: string[] }).written.join('')
    expect(joined).toContain('…')
  })
})

// ─── Layout ───────────────────────────────────────────────────────────────────

describe('TUI — layout', () => {
  it('computeLayout allocates all rows correctly', () => {
    const out    = makeOutput(80, 24)
    const layout = computeLayout(out)
    expect(layout.statusRow).toBe(1)
    expect(layout.chatStart).toBe(2)
    expect(layout.chatEnd).toBe(22)
    expect(layout.inputRow).toBe(24)
  })

  it('chatLines returns correct count', () => {
    const out    = makeOutput(80, 24)
    const layout = computeLayout(out)
    expect(chatLines(layout)).toBe(21)
  })

  it('enforces minimum dimensions', () => {
    const out    = makeOutput(10, 3)
    const layout = computeLayout(out)
    expect(layout.inputRow).toBeGreaterThanOrEqual(layout.chatEnd + 1)
  })
})

// ─── History ─────────────────────────────────────────────────────────────────

describe('TUI — history', () => {
  it('renders operator and assistant messages', () => {
    const out    = makeOutput(80, 24)
    const layout = computeLayout(out)
    const msgs: AppMessage[] = [
      { role: 'operator',  content: 'Hello',        ts: '' },
      { role: 'assistant', content: 'Hi there!',    ts: '' },
    ]
    const lines = renderHistory(msgs, layout)
    expect(lines.some(l => l.text.includes('Hello'))).toBe(true)
    expect(lines.some(l => l.text.includes('Hi there!'))).toBe(true)
  })

  it('truncates to the last chatLines entries', () => {
    const out    = makeOutput(80, 10)
    const layout = computeLayout(out)
    const msgs: AppMessage[] = Array.from({ length: 20 }, (_, i) => ({
      role: 'assistant' as const, content: `Line ${i}`, ts: '',
    }))
    const lines = renderHistory(msgs, layout)
    // chatLines(layout) = rows-2 - 2 + 1 = 10-2-2+1 = 7
    expect(lines.length).toBeLessThanOrEqual(chatLines(layout))
  })
})

// ─── applyEvent ───────────────────────────────────────────────────────────────

describe('TUI — applyEvent', () => {
  it('cycle_start transitions to thinking', () => {
    const s = initialAppState('sid', 'HACA-Core', 200000)
    const n = applyEvent(s, { type: 'cycle_start', cycleNum: 3 })
    expect(n.status).toBe('thinking')
    expect(n.cycleCount).toBe(3)
  })

  it('cpe_response appends assistant message and waits for input', () => {
    const s = initialAppState('sid', 'HACA-Core', 200000)
    const n = applyEvent(s, { type: 'cpe_response', content: 'Hello!', toolUses: [] })
    expect(n.status).toBe('waiting_input')
    expect(n.messages).toHaveLength(1)
    expect(n.messages[0]!.content).toBe('Hello!')
    expect(n.messages[0]!.role).toBe('assistant')
  })

  it('cpe_response with tool_uses transitions to tool_running', () => {
    const s = initialAppState('sid', 'HACA-Core', 200000)
    const n = applyEvent(s, {
      type: 'cpe_response', content: '', toolUses: [
        { type: 'tool_use', id: '1', name: 'fcp_file_read', input: {} },
      ],
    })
    expect(n.status).toBe('tool_running')
  })

  it('operator_msg appends operator message', () => {
    const s = initialAppState('sid', 'HACA-Core', 200000)
    const n = applyEvent(s, { type: 'operator_msg', content: 'test input' })
    expect(n.messages[0]!.role).toBe('operator')
    expect(n.messages[0]!.content).toBe('test input')
  })

  it('session_close transitions to closing', () => {
    const s = initialAppState('sid', 'HACA-Core', 200000)
    const n = applyEvent(s, { type: 'session_close', reason: 'normal' })
    expect(n.status).toBe('closing')
  })
})
