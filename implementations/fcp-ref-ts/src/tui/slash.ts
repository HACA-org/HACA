// Slash command router — intercepts '/' commands from the operator prompt
// and dispatches platform commands without passing through the CPE.
import chalk from 'chalk'
import type { AppState } from '../types/tui.js'
import { formatElapsed, fmtK, budgetColor, shortenModel } from './fixed-bar.js'

// ─── Types ────────────────────────────────────────────────────────────────────

export type SlashResult =
  | { action: 'display';     lines: string[] }
  | { action: 'inject';      text: string }    // FCP injects instruction into the session loop
  | { action: 'passthrough'; text: string }
  | { action: 'set_verbose'; value: boolean }
  | { action: 'none' }

export interface SlashCommand {
  readonly name:        string
  readonly aliases:     string[]
  readonly description: string
  execute(args: string, state: AppState): Promise<SlashResult>
}

// ─── Command definitions ──────────────────────────────────────────────────────

function stubCommand(name: string, description: string, aliases: string[] = []): SlashCommand {
  return {
    name,
    aliases,
    description,
    async execute() {
      return { action: 'display', lines: [chalk.dim(`  ${name} — not yet implemented`)] }
    },
  }
}

const helpCmd: SlashCommand = {
  name: '/help',
  aliases: [],
  description: 'Show available commands',
  async execute() {
    const lines = COMMANDS.map(c => {
      const aliases = c.aliases.length > 0 ? chalk.dim(` (${c.aliases.join(', ')})`) : ''
      return `  ${chalk.cyan(c.name)}${aliases}  ${chalk.dim(c.description)}`
    })
    return { action: 'display', lines }
  },
}

const statusCmd: SlashCommand = {
  name: '/status',
  aliases: [],
  description: 'Session status panel',
  async execute(_args, state) {
    const kv = (key: string, value: string) =>
      `  ${chalk.dim(key + ':')} ${value}`
    return {
      action: 'display',
      lines: [
        kv('session',   state.sessionId.slice(0, 8)),
        kv('cycle',     `#${state.cycleCount}  ${chalk.dim('elapsed:')} ${formatElapsed(state.sessionStart)}`),
        kv('tokens',    `↑${fmtK(state.inputTokens)} ↓${fmtK(state.outputTokens)}  ${chalk.dim('budget:')} ${budgetColor(state.budgetPct, `${state.budgetPct}%`)}`),
        kv('model',     `${state.provider}:${shortenModel(state.model)}`),
        kv('profile',   state.profile),
        kv('workspace', state.workspace || '(none)'),
        kv('status',    state.status),
        kv('verbose',   state.verbose ? chalk.green('on') : chalk.dim('off')),
      ],
    }
  },
}

const exitCmd: SlashCommand = {
  name: '/exit',
  aliases: ['/bye'],
  description: 'Close session and run Sleep Cycle (no Closure Payload)',
  async execute() {
    return {
      action: 'inject',
      text: 'SYSTEM: Operator requested session close. Call fcp_session_close immediately.',
    }
  },
}

const newCmd: SlashCommand = {
  name: '/new',
  aliases: ['/clear'],
  description: 'Save state, close session, and start a new one',
  async execute() {
    return {
      action: 'inject',
      text: 'SYSTEM: Operator requested a new session. Call fcp_closure_payload to save state, then call fcp_session_close with reboot: true.',
    }
  },
}

const verboseCmd: SlashCommand = {
  name: '/verbose',
  aliases: [],
  description: 'Toggle verbose debug output (on/off)',
  async execute(args, state) {
    const arg = args.trim().toLowerCase()
    if (arg !== 'on' && arg !== 'off') {
      return {
        action: 'display',
        lines: [
          `  Usage: ${chalk.cyan('/verbose on')} ${chalk.dim('|')} ${chalk.cyan('/verbose off')}`,
          `  Current: ${state.verbose ? chalk.green('on') : chalk.dim('off')}`,
        ],
      }
    }
    const value = arg === 'on'
    return { action: 'set_verbose', value }
  },
}

const COMMANDS: SlashCommand[] = [
  helpCmd,
  statusCmd,
  exitCmd,
  newCmd,
  verboseCmd,
  stubCommand('/model',    'List or switch CPE model'),
  stubCommand('/compact',  'Trigger context compaction'),
  stubCommand('/skill',    'Manage skills (list, add, audit)'),
  stubCommand('/endure',   'Manage evolution proposals (list, approve)'),
  stubCommand('/inbox',    'Operator notifications (list, view)'),
  stubCommand('/work',     'Workspace focus (set, clear, status)'),
  stubCommand('/snapshot', 'Create entity snapshot'),
  stubCommand('/memory',   'Browse memory store'),
]

// ─── Router ───────────────────────────────────────────────────────────────────

// Match a partial prefix against all commands and aliases.
export function matchPrefix(input: string): SlashCommand[] {
  const lower = input.toLowerCase().trim()
  if (!lower.startsWith('/')) return []
  return COMMANDS.filter(c =>
    c.name.startsWith(lower) ||
    c.aliases.some(a => a.startsWith(lower)),
  )
}

// Dispatch a slash command. Returns a SlashResult.
export async function dispatch(input: string, state: AppState): Promise<SlashResult> {
  const trimmed = input.trim()
  const spaceIdx = trimmed.indexOf(' ')
  const cmdName = spaceIdx > 0 ? trimmed.slice(0, spaceIdx) : trimmed
  const args = spaceIdx > 0 ? trimmed.slice(spaceIdx + 1).trim() : ''

  const lower = cmdName.toLowerCase()
  const cmd = COMMANDS.find(c =>
    c.name === lower || c.aliases.includes(lower),
  )

  if (!cmd) {
    return { action: 'display', lines: [chalk.red(`  Unknown command: ${cmdName}`)] }
  }

  return cmd.execute(args, state)
}

// Format autocomplete suggestions for the dynamic area.
export function autocomplete(input: string): string[] {
  const matches = matchPrefix(input)
  if (matches.length === 0) return []
  return matches.map(c => `  ${chalk.cyan(c.name)}  ${chalk.dim(c.description)}`)
}
