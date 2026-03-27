// TUI status bar — renders row 1 with cycle count, token budget, and profile.
import type { AppState, TUIStatus } from '../types/tui.js'
import type { Output } from './renderer.js'
import type { TUILayout } from './layout.js'
import { moveTo, eraseLine, bold, dim, color, C_CYAN, C_GREEN, C_YELLOW, C_RED } from './renderer.js'

const STATUS_LABEL: Record<TUIStatus, string> = {
  idle:          'idle',
  thinking:      'thinking',
  waiting_input: 'waiting',
  tool_running:  'tool',
  closing:       'closing',
}

function budgetColor(pct: number, s: string): string {
  if (pct >= 80) return color(s, C_RED)
  if (pct >= 65) return color(s, C_YELLOW)
  return color(s, C_GREEN)
}

export function renderStatus(out: Output, state: AppState, layout: TUILayout): void {
  const profile  = state.profile === 'HACA-Evolve' ? color('Evolve', C_CYAN) : color('Core', C_GREEN)
  const statusTxt = STATUS_LABEL[state.status] ?? state.status
  const budget   = `${state.budgetPct}%`
  const cycles   = `#${state.cycleCount}`
  const sid      = dim(state.sessionId.slice(0, 8))

  const left  = ` FCP ${profile}  ${dim(statusTxt)}`
  const right = ` ${cycles}  ${budgetColor(state.budgetPct, budget)}  ${sid} `
  const gap   = Math.max(1, layout.columns - stripped(left).length - stripped(right).length)

  out.write(moveTo(layout.statusRow, 1) + eraseLine() + left + ' '.repeat(gap) + right)
}

// Strip ANSI codes to compute visible string length
function stripped(s: string): string {
  return s.replace(/\x1b\[[^m]*m/g, '')
}

export function renderSeparator(out: Output, layout: TUILayout): void {
  const sep = dim('─'.repeat(layout.columns))
  out.write(moveTo(layout.chatEnd + 1, 1) + eraseLine() + sep)
}

export function renderInputPrompt(out: Output, layout: TUILayout, inputLine: string): void {
  out.write(moveTo(layout.inputRow, 1) + eraseLine() + bold('> ') + inputLine)
  // Move cursor to after the input text
  const col = 3 + inputLine.length  // '> ' = 2 chars + 1-based
  out.write(moveTo(layout.inputRow, col))
}
