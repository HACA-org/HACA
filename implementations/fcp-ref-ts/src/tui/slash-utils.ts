// Utility slash commands: /compact, /work, /inbox.
import * as path from 'node:path'
import * as nodefs from 'node:fs/promises'
import chalk from 'chalk'
import { fileExists } from '../store/io.js'
import type { SlashCommand, SlashResult } from './slash.js'
import type { AppState } from '../types/tui.js'

// ─── /compact ────────────────────────────────────────────────────────────────

export const compactCmd: SlashCommand = {
  name:        '/compact',
  aliases:     [],
  description: 'Trigger context compaction — save state and reboot with fresh context',
  async execute(): Promise<SlashResult> {
    return {
      action: 'inject',
      text:   'SYSTEM: Operator requested context compaction. Call fcp_closure_payload to save state, then call fcp_session_close with reboot: true.',
    }
  },
}

// ─── /work ───────────────────────────────────────────────────────────────────

export const workCmd: SlashCommand = {
  name:        '/work',
  aliases:     [],
  description: 'Workspace focus (show | set <path> | clear)',
  async execute(args: string, state: AppState): Promise<SlashResult> {
    const [sub, ...rest] = args.trim().split(/\s+/)
    const subCmd = (sub ?? '').toLowerCase()

    if (!subCmd || subCmd === 'show') {
      const ws = state.workspace || chalk.dim('(none)')
      return { action: 'display', lines: [`  ${chalk.dim('workspace:')} ${ws}`] }
    }

    if (subCmd === 'clear') {
      return { action: 'set_workspace', path: null }
    }

    if (subCmd === 'set') {
      const rawPath = rest.join(' ').trim()
      if (!rawPath) {
        return {
          action: 'display',
          lines:  [`  Usage: ${chalk.cyan('/work set <path>')}`],
        }
      }
      const resolved = path.resolve(rawPath)
      return { action: 'set_workspace', path: resolved }
    }

    return {
      action: 'display',
      lines: [
        `  Usage: ${chalk.cyan('/work')}           ${chalk.dim('show current workspace')}`,
        `         ${chalk.cyan('/work set <path>')} ${chalk.dim('set workspace focus')}`,
        `         ${chalk.cyan('/work clear')}      ${chalk.dim('clear workspace focus')}`,
      ],
    }
  },
}

// ─── /inbox ──────────────────────────────────────────────────────────────────

export const inboxCmd: SlashCommand = {
  name:        '/inbox',
  aliases:     [],
  description: 'List operator notifications',
  async execute(_args: string, state: AppState): Promise<SlashResult> {
    const dir = state.layout.state.operatorNotifications
    if (!await fileExists(dir)) {
      return { action: 'display', lines: [chalk.dim('  No notifications.')] }
    }

    let entries: string[]
    try {
      entries = await nodefs.readdir(dir)
    } catch {
      return { action: 'display', lines: [chalk.red('  Error reading notifications.')] }
    }

    const files = entries.filter(e => e.endsWith('.json')).sort().reverse()
    if (files.length === 0) {
      return { action: 'display', lines: [chalk.dim('  No notifications.')] }
    }

    const lines: string[] = [`  ${chalk.bold(`${files.length} notification(s):`)}`]
    for (const f of files.slice(0, 4)) {
      // Filename format: heartbeat-<level>-<ts>.json or similar
      const base = f.replace('.json', '')
      lines.push(`  ${chalk.dim(base)}`)
    }
    if (files.length > 4) {
      lines.push(chalk.dim(`  … and ${files.length - 4} more`))
    }
    return { action: 'display', lines }
  },
}
