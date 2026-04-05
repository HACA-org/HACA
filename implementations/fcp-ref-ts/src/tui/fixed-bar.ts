// Footer data formatting — pure functions that produce styled strings.
// No terminal positioning or rendering — blessed handles that.
import chalk from 'chalk'
import type { FooterData } from '../types/tui.js'

// ─── Helpers ──────────────────────────────────────────────────────────────────

// Strip ANSI escape sequences to compute visible string length.
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

export function shortenModel(model: string): string {
  return model.replace(/^claude-/, '').replace(/-\d{8}$/, '')
}

function shortenWorkspace(ws: string): string {
  if (!ws) return '(none)'
  const home = process.env['HOME'] ?? ''
  if (home && ws.startsWith(home)) return '~' + ws.slice(home.length)
  return ws.length > 30 ? '...' + ws.slice(-27) : ws
}

// ─── Footer line composition ──────────────────────────────────────────────────

function statusLabel(status: import('../types/tui.js').TUIStatus): string {
  switch (status) {
    case 'thinking':     return chalk.yellow('thinking')
    case 'tool_running': return chalk.cyan('tool')
    case 'waiting_input': return chalk.green('ready')
    case 'closing':      return chalk.red('closing')
    case 'idle':         return chalk.dim('idle')
  }
}

export function formatFooter(data: FooterData, cols: number): string {
  const segments: string[] = [
    chalk.dim('ws: ')      + chalk.cyan(shortenWorkspace(data.workspace)),
    chalk.white(data.provider + ':' + shortenModel(data.model)),
    chalk.dim('cycle: ')   + chalk.white(String(data.cycleNum)),
    chalk.dim('in: ')      + chalk.white(fmtK(data.inputTokens)) + chalk.dim(' / out: ') + chalk.white(fmtK(data.outputTokens)),
    chalk.dim('ctx: ')     + budgetColor(data.contextPct, `${data.contextPct}%`),
    chalk.dim('time: ')    + chalk.white(data.sessionTime),
    chalk.dim('session: ') + chalk.white(data.sessionId.slice(0, 8)),
    statusLabel(data.status),
  ]

  const sep = chalk.dim(' │ ')
  let line = ''
  let visLen = 0
  for (let i = 0; i < segments.length; i++) {
    const part = (i > 0 ? sep : '  ') + segments[i]!
    const partVis = stripped(part).length
    if (visLen + partVis > cols - 1) break
    line += part
    visLen += partVis
  }
  return line
}
