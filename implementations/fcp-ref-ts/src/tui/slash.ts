// Slash command router — intercepts '/' commands from the operator prompt
// and dispatches platform commands without passing through the CPE.
import chalk from 'chalk'
import type { AppState, FooterData } from '../types/tui.js'
import type { CloseReason } from '../types/session.js'
import { formatElapsed, fmtK, budgetColor } from './fixed-bar.js'

// ─── Types ────────────────────────────────────────────────────────────────────

export type SlashResult =
  | { action: 'display';     lines: string[] }
  | { action: 'exit';        reason: CloseReason }
  | { action: 'clear' }
  | { action: 'passthrough'; text: string }
  | { action: 'none' }

export interface SlashCommand {
  readonly name:        string
  readonly aliases:     string[]
  readonly description: string
  execute(args: string, state: AppState): Promise<SlashResult>
}

// ─── Command definitions ──────────────────────────────────────────────────────

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
    const elapsed = formatElapsed(state.sessionStart)
    return {
      action: 'display',
      lines: [
        `  ${chalk.dim('session')}  ${state.sessionId.slice(0, 8)}  ${chalk.dim('cycle')} #${state.cycleCount}  ${chalk.dim('elapsed')} ${elapsed}`,
        `  ${chalk.dim('tokens')}   ↑${fmtK(state.inputTokens)} ↓${fmtK(state.outputTokens)}  ${chalk.dim('budget')} ${budgetColor(state.budgetPct, state.budgetPct + '%')}`,
        `  ${chalk.dim('model')}    ${state.provider}:${state.model}`,
        `  ${chalk.dim('profile')}  ${state.profile}`,
        state.workspace ? `  ${chalk.dim('workspace')} ${state.workspace}` : `  ${chalk.dim('workspace')} (none)`,
      ],
    }
  },
}

const exitCmd: SlashCommand = {
  name: '/exit',
  aliases: ['/bye', '/close'],
  description: 'Close session normally',
  async execute() {
    return { action: 'exit', reason: 'normal' }
  },
}

const clearCmd: SlashCommand = {
  name: '/clear',
  aliases: ['/new', '/reset'],
  description: 'Clear chat history',
  async execute() {
    return { action: 'clear' }
  },
}

const verboseCmd: SlashCommand = {
  name: '/verbose',
  aliases: [],
  description: 'Toggle verbose output',
  async execute() {
    return { action: 'display', lines: [chalk.dim('  verbose toggle — not yet implemented')] }
  },
}

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

const COMMANDS: SlashCommand[] = [
  helpCmd,
  statusCmd,
  exitCmd,
  clearCmd,
  verboseCmd,
  stubCommand('/model',    'List or switch CPE model'),
  stubCommand('/compact',  'Trigger context compaction'),
  stubCommand('/skill',    'Manage skills', ['/skill list', '/skill add', '/skill audit']),
  stubCommand('/endure',   'Manage evolution proposals', ['/endure list', '/endure approve']),
  stubCommand('/inbox',    'Operator notifications', ['/inbox list', '/inbox view']),
  stubCommand('/work',     'Workspace focus', ['/work set', '/work clear', '/work status']),
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
