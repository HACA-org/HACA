// TUI header — ASCII art FCP logo + entity stats panel.
// Rendered once at session start, before the scroll region is configured.
import chalk from 'chalk'
import type { Layout } from '../types/store.js'
import type { Profile } from '../types/cli.js'
import { fileExists, readJson } from '../store/io.js'
import * as fs from 'node:fs/promises'

// ─── Entity stats (computed from on-disk state) ──────────────────────────────

export interface EntityStats {
  readonly fcpVersion:     string
  readonly hacaProfile:    string
  readonly operatorName:   string
  readonly activatedAt:    string      // ISO datetime
  readonly totalSessions:  number
  readonly totalCycles:    number
  readonly totalTimeStr:   string      // e.g. "2h 14m"
}

export async function loadEntityStats(layout: Layout, fcpVersion: string): Promise<EntityStats> {
  let hacaProfile  = 'unknown'
  let operatorName = 'unknown'
  let activatedAt  = 'unknown'

  // From imprint
  if (await fileExists(layout.memory.imprint)) {
    try {
      const imp = await readJson(layout.memory.imprint) as Record<string, unknown>
      hacaProfile  = (imp['hacaProfile']  as string) ?? hacaProfile
      activatedAt  = (imp['activatedAt']  as string) ?? activatedAt
      const bound  = imp['operatorBound'] as Record<string, unknown> | undefined
      if (bound) operatorName = (bound['operatorName'] as string) ?? operatorName
    } catch { /* ignore */ }
  }

  // From heartbeat — cumulative cycle count
  let totalCycles = 0
  if (await fileExists(layout.state.heartbeat)) {
    try {
      const hb = await readJson(layout.state.heartbeat) as Record<string, unknown>
      totalCycles = (hb['cycleCount'] as number) ?? 0
    } catch { /* ignore */ }
  }

  // From integrity.log — count SLEEP_COMPLETE entries + estimate total time
  let totalSessions = 0
  let totalTimeMs   = 0
  if (await fileExists(layout.state.integrityLog)) {
    try {
      const raw   = await fs.readFile(layout.state.integrityLog, 'utf8')
      const lines = raw.split('\n').filter(Boolean)

      for (const line of lines) {
        try {
          const entry = JSON.parse(line) as Record<string, unknown>
          if (entry['event'] === 'SLEEP_COMPLETE') totalSessions++
        } catch { /* skip malformed lines */ }
      }
    } catch { /* ignore */ }
  }

  // From session.jsonl — estimate total time from session_close entries
  if (await fileExists(layout.memory.sessionJsonl)) {
    try {
      const raw   = await fs.readFile(layout.memory.sessionJsonl, 'utf8')
      const lines = raw.split('\n').filter(Boolean)
      // Heuristic: calculate time between consecutive session start/close pairs
      // We approximate using time between first and last entries
      const timestamps: number[] = []
      for (const line of lines) {
        try {
          const entry = JSON.parse(line) as Record<string, unknown>
          if (entry['ts']) timestamps.push(new Date(entry['ts'] as string).getTime())
        } catch { /* skip */ }
      }
      if (timestamps.length >= 2) {
        // Sum gaps between consecutive timestamps that are < 24h apart (same session)
        for (let i = 1; i < timestamps.length; i++) {
          const gap = timestamps[i]! - timestamps[i - 1]!
          if (gap > 0 && gap < 24 * 60 * 60 * 1000) totalTimeMs += gap
        }
      }
    } catch { /* ignore */ }
  }

  return {
    fcpVersion,
    hacaProfile,
    operatorName,
    activatedAt: activatedAt !== 'unknown' ? activatedAt.slice(0, 10) : activatedAt,
    totalSessions,
    totalCycles,
    totalTimeStr: formatTotalTime(totalTimeMs),
  }
}

function formatTotalTime(ms: number): string {
  if (ms <= 0) return '0m'
  const totalMin = Math.floor(ms / 60_000)
  if (totalMin < 60) return `${totalMin}m`
  const h = Math.floor(totalMin / 60)
  const m = totalMin % 60
  if (h < 24) return m > 0 ? `${h}h ${m}m` : `${h}h`
  const d = Math.floor(h / 24)
  const rh = h % 24
  return rh > 0 ? `${d}d ${rh}h` : `${d}d`
}

// ─── ASCII art logo + stats rendering ────────────────────────────────────────

// FCP in large block letters — 6 lines tall
const FCP_LOGO = [
  '███████  ██████ ██████ ',
  '██      ██      ██   ██',
  '█████   ██      ██████ ',
  '██      ██      ██     ',
  '██       ██████ ██     ',
]

export function renderHeader(stats: EntityStats, cols: number): string[] {
  const logoWidth  = 23
  const statsLines = [
    chalk.dim('FCP ') + chalk.white(stats.fcpVersion),
    chalk.dim('Profile  ') + profileColor(stats.hacaProfile),
    chalk.dim('Operator ') + chalk.white(stats.operatorName),
    chalk.dim('Since    ') + chalk.white(stats.activatedAt),
    chalk.dim('Sessions ') + chalk.white(String(stats.totalSessions))
      + chalk.dim(' │ Cycles ') + chalk.white(String(stats.totalCycles))
      + chalk.dim(' │ Time ') + chalk.white(stats.totalTimeStr),
  ]

  const sep    = '   '
  const lines: string[] = []

  // Two-column layout if enough width, otherwise stacked
  if (cols >= logoWidth + 40) {
    const maxRows = Math.max(FCP_LOGO.length, statsLines.length)
    for (let i = 0; i < maxRows; i++) {
      const left  = i < FCP_LOGO.length   ? chalk.cyan(FCP_LOGO[i]!)   : ' '.repeat(logoWidth)
      const right = i < statsLines.length  ? statsLines[i]!             : ''
      lines.push('  ' + left + sep + chalk.dim('│') + ' ' + right)
    }
  } else {
    // Narrow terminal — stacked
    for (const l of FCP_LOGO) lines.push('  ' + chalk.cyan(l))
    lines.push('')
    for (const s of statsLines) lines.push('  ' + s)
  }

  return lines
}

function profileColor(profile: string): string {
  if (profile.includes('Evolve')) return chalk.cyan(profile)
  return chalk.green(profile)
}

// Render header for non-TTY (plain text, no ANSI).
export function renderHeaderPlain(stats: EntityStats, cols: number): string[] {
  const bar = '─'.repeat(cols)
  return [
    bar,
    ...FCP_LOGO.map(l => '  ' + l),
    '',
    `  FCP ${stats.fcpVersion}  │  ${stats.hacaProfile}  │  Operator: ${stats.operatorName}`,
    `  Since ${stats.activatedAt}  │  Sessions: ${stats.totalSessions}  │  Cycles: ${stats.totalCycles}  │  Time: ${stats.totalTimeStr}`,
    bar,
  ]
}
