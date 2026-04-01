// Fixed bar — renders the 9-row zone pinned at the bottom of the terminal:
// separator, input, separator, footer, dynamic (5 lines).
// All writes use absolute cursor positioning (outside the scroll region).
import chalk from 'chalk'
import type { Output } from './renderer.js'
import type { TUILayout } from './layout.js'
import type { FooterData } from '../types/tui.js'
import { moveTo, eraseLine } from './renderer.js'

// ─── Helpers ──────────────────────────────────────────────────────────────────

// Strip ANSI escape sequences to compute visible string length.
// Covers: CSI sequences (colors, styles, cursor), OSC, and other common escapes.
export function stripped(s: string): string {
  // eslint-disable-next-line no-control-regex
  return s.replace(/\x1b(?:\[[0-9;]*[A-Za-z]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[^[\]])/g, '')
}

export function fmtK(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`
}

export function budgetColor(pct: number, s: string): string {
  if (pct >= 80) return chalk.red(s)
  if (pct >= 65) return chalk.yellow(s)
  return chalk.green(s)
}

export function formatElapsed(startMs: number): string {
  const elapsed = Math.max(0, Math.floor((Date.now() - startMs) / 1000))
  const m = Math.floor(elapsed / 60)
  const s = elapsed % 60
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

function shortenModel(model: string): string {
  // "claude-sonnet-4-20250514" → "sonnet-4"
  // "gpt-4o-2024-08-06" → "gpt-4o"
  return model.replace(/^claude-/, '').replace(/-\d{8}$/, '')
}

function shortenWorkspace(ws: string): string {
  if (!ws) return '(none)'
  const home = process.env['HOME'] ?? ''
  if (home && ws.startsWith(home)) return '~' + ws.slice(home.length)
  return ws.length > 30 ? '...' + ws.slice(-27) : ws
}

// ─── Footer line composition ──────────────────────────────────────────────────

export function formatFooter(data: FooterData, cols: number): string {
  // Build segments from left to right; drop rightmost if too wide.
  const segments: string[] = [
    chalk.dim('ws:') + chalk.cyan(shortenWorkspace(data.workspace)),
    chalk.dim(data.provider + ':') + chalk.white(shortenModel(data.model)),
    chalk.dim('#') + String(data.cycleNum),
    chalk.dim('↑') + fmtK(data.inputTokens) + chalk.dim(' ↓') + fmtK(data.outputTokens),
    budgetColor(data.contextPct, `${data.contextPct}%`),
    chalk.dim(data.sessionTime),
    chalk.dim(data.sessionId.slice(0, 8)),
    data.profile === 'HACA-Evolve' ? chalk.cyan('Evolve') : chalk.green('Core'),
    chalk.dim('FCP ' + data.fcpVersion),
  ]

  const sep = chalk.dim(' │ ')
  let line = ''
  let visLen = 0
  for (let i = 0; i < segments.length; i++) {
    const part = (i > 0 ? sep : ' ') + segments[i]!
    const partVis = stripped(part).length
    if (visLen + partVis > cols - 1) break  // drop if would overflow
    line += part
    visLen += partVis
  }
  return line
}

// ─── Rendering ────────────────────────────────────────────────────────────────

function renderSeparator(out: Output, row: number, cols: number): void {
  out.write(moveTo(row, 1) + eraseLine() + chalk.dim('─'.repeat(cols)))
}

export function renderInputRow(
  out: Output, row: number, inputText: string, label = '> ',
): void {
  out.write(moveTo(row, 1) + eraseLine() + chalk.bold(label) + inputText)
}

export function renderFooterRow(
  out: Output, row: number, data: FooterData, cols: number,
): void {
  out.write(moveTo(row, 1) + eraseLine() + formatFooter(data, cols))
}

export function renderDynamicArea(
  out: Output, startRow: number, lines: string[], cols: number,
): void {
  for (let i = 0; i < 5; i++) {
    out.write(moveTo(startRow + i, 1) + eraseLine())
    const line = lines[i]
    if (line) {
      const vis = stripped(line)
      out.write(vis.length > cols ? line.slice(0, cols - 1) + '…' : line)
    }
  }
}

// Render the entire fixed bar (9 rows).
export function renderFixedBar(
  out: Output,
  layout: TUILayout,
  footer: FooterData,
  inputText: string,
  dynamicLines: string[],
  inputLabel?: string,
): void {
  renderSeparator(out, layout.sepAboveInput, layout.columns)
  renderInputRow(out, layout.inputRow, inputText, inputLabel)
  renderSeparator(out, layout.sepBelowInput, layout.columns)
  renderFooterRow(out, layout.footerRow, footer, layout.columns)
  renderDynamicArea(out, layout.dynamicStart, dynamicLines, layout.columns)
}

// Position cursor at the end of the input text (for live typing).
export function positionInputCursor(
  out: Output, inputRow: number, inputText: string, label = '> ',
): void {
  const col = stripped(label).length + inputText.length + 1
  out.write(moveTo(inputRow, col))
}
