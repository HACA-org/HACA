// Interactive prompt UI with standardized styling.
// All prompts use this module for consistent look and behavior.
import { createInterface } from 'node:readline'
import chalk from 'chalk'

export interface PromptOptions {
  default?: string
  hint?: string
}

export interface SelectOption {
  label: string
  description?: string
}

type RL = ReturnType<typeof createInterface>

/**
 * Text input prompt with optional default.
 * Shows hint in parentheses on the right.
 */
export async function prompt(rl: RL, question: string, opts: PromptOptions = {}): Promise<string> {
  const hint = opts.hint || (opts.default ? `[${opts.default}]` : '')
  const line = hint ? `  ${question} ${chalk.dim(hint)}: ` : `  ${question}: `
  return new Promise(resolve => {
    rl.question(line, a => {
      resolve((a.trim() || opts.default || '').trim())
    })
  })
}

/**
 * Yes/No confirmation with optional default.
 * Shows selection in cyan highlight when chosen.
 */
export async function confirm(rl: RL, question: string, defaultYes = true): Promise<boolean> {
  const hint = defaultYes ? 'Y/n' : 'y/N'
  const line = `  ${question} ${chalk.dim(`[${hint}]`)}: `
  return new Promise(resolve => {
    rl.question(line, a => {
      const s = a.trim().toLowerCase()
      const result = s === '' ? defaultYes : s === 'y' || s === 'yes'
      resolve(result)
    })
  })
}

/**
 * Interactive selection from a list of options.
 * Supports arrow keys (↑↓) + Enter, number input (1-9), or 'q'/'Ctrl-C' to cancel.
 * Selected item highlighted in cyan with arrow marker.
 * Throws UserCancelledError if cancelled with Ctrl-C or 'q'.
 */
export class UserCancelledError extends Error {
  constructor() {
    super('User cancelled selection')
    this.name = 'UserCancelledError'
  }
}

export async function select(
  _rl: RL,
  question: string,
  options: SelectOption[],
  defaultIdx = 0,
): Promise<{ index: number; label: string }> {
  if (options.length === 0) throw new Error('select: no options provided')

  // Dynamically import the interactive select to avoid requiring raw mode setup upfront
  const { selectInteractive } = await import('./select.js')
  const result = await selectInteractive(question, options, defaultIdx)

  // Check if user cancelled (via Ctrl-C or 'q')
  if (result.index === -1) {
    throw new UserCancelledError()
  }

  return result
}

/**
 * Section separator with optional label.
 */
export function hr(label = ''): void {
  if (label) {
    const padding = Math.max(0, 60 - label.length - 4)
    process.stdout.write(`\n  ${chalk.dim('──')} ${label} ${chalk.dim('─'.repeat(padding))}\n`)
  } else {
    process.stdout.write(`  ${chalk.dim('─'.repeat(60))}\n`)
  }
}

/**
 * Styled info message (green checkmark).
 */
export function info(msg: string): void {
  process.stdout.write(`  ${chalk.green('✓')} ${msg}\n`)
}

/**
 * Styled warning message (yellow warning icon).
 */
export function warn(msg: string): void {
  process.stdout.write(`  ${chalk.yellow('⚠')} ${msg}\n`)
}

/**
 * Styled error message (red X).
 */
export function error(msg: string): void {
  process.stdout.write(`  ${chalk.red('✗')} ${msg}\n`)
}

/**
 * Styled success header.
 */
export function header(title: string, subtitle = ''): void {
  process.stdout.write('\n')
  hr()
  process.stdout.write(`  ${chalk.bold(title)}\n`)
  if (subtitle) process.stdout.write(`  ${chalk.dim(subtitle)}\n`)
  hr()
  process.stdout.write('\n')
}
