// /model slash command — display current CPE model and list alternatives.
// Switching models mid-session requires a reboot; this command guides the operator.
import chalk from 'chalk'
import { listOllamaModels } from '../cpe/ollama.js'
import { shortenModel } from './fixed-bar.js'
import type { SlashCommand, SlashResult } from './slash.js'
import type { AppState } from '../types/tui.js'

// Static model catalogs (mirrors init.ts / model.ts)
const ANTHROPIC_MODELS = [
  'claude-opus-4-6',
  'claude-sonnet-4-6',
  'claude-haiku-4-5-20251001',
  'claude-opus-4-5-20251101',
  'claude-sonnet-4-20250514',
]

const OPENAI_MODELS = [
  'gpt-4o',
  'gpt-4o-mini',
  'o1',
  'o3-mini',
]

const GOOGLE_MODELS = [
  'gemini-2.5-flash',
  'gemini-3-flash-preview',
  'gemini-3.1-flash-lite-preview',
  'gemini-3.1-pro-preview',
]

async function getModelsForProvider(provider: string): Promise<string[]> {
  switch (provider) {
    case 'anthropic': return ANTHROPIC_MODELS
    case 'openai':    return OPENAI_MODELS
    case 'google':    return GOOGLE_MODELS
    case 'ollama':    return await listOllamaModels()
    default:          return []
  }
}

async function execute(args: string, state: AppState): Promise<SlashResult> {
  const sub = args.trim().toLowerCase()

  const currentLabel = `${state.provider}:${shortenModel(state.model)}`

  if (!sub || sub === 'list') {
    const models = await getModelsForProvider(state.provider)
    const lines: string[] = [
      `  ${chalk.dim('current:')} ${chalk.cyan(currentLabel)}`,
    ]
    if (models.length > 0) {
      lines.push(`  ${chalk.dim(`available (${state.provider}):`)}`)
      for (const m of models) {
        const marker = m === state.model ? chalk.green(' ←') : ''
        lines.push(`    ${chalk.dim(m)}${marker}`)
      }
    } else if (state.provider === 'ollama') {
      lines.push(`  ${chalk.yellow('  No Ollama models found (is Ollama running?)')}`)
    }
    lines.push(`  ${chalk.dim('To switch: run')} ${chalk.cyan('fcp model')} ${chalk.dim('then')} ${chalk.cyan('/new')}`)
    return { action: 'display', lines }
  }

  // Unknown sub-command
  return {
    action: 'display',
    lines: [
      `  Usage: ${chalk.cyan('/model')}        ${chalk.dim('show current model and list alternatives')}`,
      `         ${chalk.cyan('/model list')}   ${chalk.dim('same as above')}`,
    ],
  }
}

export const modelCmd: SlashCommand = {
  name:        '/model',
  aliases:     [],
  description: 'Show current CPE model and list alternatives',
  execute,
}
