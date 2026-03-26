import { join } from 'node:path'
import { existsSync } from 'node:fs'
import { homedir } from 'node:os'
import { createLayout } from '../store/layout.js'
import { createLogger } from '../logger/logger.js'
import { runBoot } from '../boot/boot.js'
import { resolveAdapter, detectAvailableModels } from '../cpe/cpe.js'
import { resolveWorkspaceFocus, createBuiltinTools } from '../exec/exec.js'
import { startTui } from '../tui/tui.js'
import { readJson } from '../store/io.js'

const FCP_ENTITIES_DIR = join(homedir(), '.fcp', 'entities')
const FCP_DEFAULT_FILE = join(homedir(), '.fcp', 'default')

interface BaselineConfig {
  provider?: string
  model?: string
  context_window?: number
  haca_profile?: 'haca-core' | 'haca-evolve'
}

async function resolveEntityRoot(): Promise<string> {
  if (existsSync(FCP_DEFAULT_FILE)) {
    const content = await import('node:fs/promises').then(fs => fs.readFile(FCP_DEFAULT_FILE, 'utf8'))
    const entityId = content.trim()
    if (entityId) {
      const entityRoot = join(FCP_ENTITIES_DIR, entityId)
      if (existsSync(entityRoot)) return entityRoot
    }
  }

  if (existsSync(FCP_ENTITIES_DIR)) {
    const { readdir } = await import('node:fs/promises')
    const entries = await readdir(FCP_ENTITIES_DIR, { withFileTypes: true })
    const dirs = entries.filter(e => e.isDirectory())
    if (dirs.length > 0 && dirs[0]) {
      return join(FCP_ENTITIES_DIR, dirs[0].name)
    }
  }

  throw new Error('No entity found. Run `fcp init` to create one.')
}

async function resolveModel(baseline: BaselineConfig): Promise<{ provider: string; model: string; contextWindow: number }> {
  const provider = baseline.provider
  const model = baseline.model

  if (provider && model) {
    return { provider, model, contextWindow: baseline.context_window ?? 200000 }
  }

  const available = await detectAvailableModels()
  if (available.length === 0) {
    throw new Error('No AI provider available. Set ANTHROPIC_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY, or start Ollama.')
  }

  const first = available[0]!
  return { provider: first.provider, model: first.id, contextWindow: first.contextWindow }
}

export async function runFcp(opts: { verbose?: boolean; debug?: boolean }): Promise<void> {
  const entityRoot = await resolveEntityRoot()
  const layout = createLayout(entityRoot)
  const logger = createLogger(layout.entityLog, join(layout.state, 'counters.json'))

  let baseline: BaselineConfig = {}
  if (existsSync(layout.baseline)) {
    baseline = await readJson<BaselineConfig>(layout.baseline).catch(() => ({}))
  }

  const { provider, model, contextWindow } = await resolveModel(baseline)

  let bootResult
  try {
    bootResult = await runBoot(layout, logger)
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    process.stderr.write(`Boot failed: ${msg}\n`)
    process.exit(1)
  }

  const profile = baseline.haca_profile ?? 'haca-core'
  const adapter = resolveAdapter({ provider, model, profile })
  const workspaceFocus = resolveWorkspaceFocus(process.cwd())
  const sessionGrants = new Set<string>()
  const ctx = { workspaceFocus }

  // Delegating approval — wired to TUI after startTui binds io
  // Tool-level approval (string prompt) maps to a simple deny-safe default;
  // loop-level approval (name + input) is handled by SessionIO.requestToolApproval
  let toolLevelApproval: (prompt: string) => Promise<'once' | 'session' | 'allow' | 'deny'> =
    async () => 'deny'

  const tools = createBuiltinTools(
    layout,
    logger,
    ctx,
    adapter,
    sessionGrants,
    (prompt) => toolLevelApproval(prompt),
  )

  await startTui({
    layout,
    bootResult,
    adapter,
    logger,
    sessionOpts: { contextWindow, tools },
    model,
    provider,
    workspaceFocus,
    ...(opts.verbose !== undefined ? { verbose: opts.verbose } : {}),
    ...(opts.debug !== undefined ? { debug: opts.debug } : {}),
    version: '0.1.0',
    onToolLevelApproval: (fn) => { toolLevelApproval = fn },
  })
}
