// fcp list / fcp set / fcp unset / fcp remove — entity registry management.
import * as path from 'node:path'
import * as os from 'node:os'
import * as fs from 'node:fs/promises'
import { existsSync } from 'node:fs'
import type { Command } from 'commander'
import { fileExists, readJson, ensureDir, atomicWrite } from '../../store/io.js'
import { createLayout } from '../../types/store.js'
import { CLIError } from '../../types/cli.js'

const FCP_HOME     = path.join(os.homedir(), '.fcp')
const ENTITIES_DIR = path.join(FCP_HOME, 'entities')
const DEFAULT_FILE = path.join(FCP_HOME, 'default')

async function getDefault(): Promise<string | null> {
  if (!existsSync(DEFAULT_FILE)) return null
  const id = (await fs.readFile(DEFAULT_FILE, 'utf8')).trim()
  return id || null
}

async function listEntityIds(): Promise<string[]> {
  if (!existsSync(ENTITIES_DIR)) return []
  const entries = await fs.readdir(ENTITIES_DIR, { withFileTypes: true })
  return entries.filter(e => e.isDirectory()).map(e => e.name).sort()
}

async function readEntityMeta(root: string): Promise<{ profile: string; backend: string; activated: boolean }> {
  const layout = createLayout(root)
  let profile = 'unknown'
  let backend = 'unknown'
  let activated = false
  try {
    if (await fileExists(layout.state.baseline)) {
      const raw = await readJson(layout.state.baseline) as Record<string, unknown>
      const cpe = raw['cpe'] as Record<string, unknown> | undefined
      backend = typeof cpe?.['backend'] === 'string' ? cpe['backend'] : 'unknown'
      profile = typeof cpe?.['topology'] === 'string'
        ? (cpe['topology'] === 'opaque' ? 'HACA-Evolve' : 'HACA-Core')
        : 'unknown'
    }
    activated = await fileExists(layout.memory.imprint)
  } catch { /* ignore */ }
  return { profile, backend, activated }
}

// ─── fcp list ─────────────────────────────────────────────────────────────────

async function runList(): Promise<void> {
  const ids = await listEntityIds()
  if (ids.length === 0) {
    process.stdout.write('\n  No entities found. Run `fcp init` to create one.\n\n')
    return
  }

  const defaultId = await getDefault()
  process.stdout.write('\n')

  for (const id of ids) {
    const root    = path.join(ENTITIES_DIR, id)
    const meta    = await readEntityMeta(root)
    const marker  = id === defaultId ? '* ' : '  '
    const state   = meta.activated ? 'activated' : 'cold'
    process.stdout.write(`${marker}${id}\n`)
    process.stdout.write(`    profile:  ${meta.profile}\n`)
    process.stdout.write(`    backend:  ${meta.backend}\n`)
    process.stdout.write(`    state:    ${state}\n`)
    process.stdout.write(`    path:     ${root}\n`)
    process.stdout.write('\n')
  }

  if (defaultId) {
    process.stdout.write(`  * = default\n\n`)
  }
}

// ─── fcp set <entityId> ───────────────────────────────────────────────────────

async function runSet(entityId: string): Promise<void> {
  const root = path.join(ENTITIES_DIR, entityId)
  if (!existsSync(root)) {
    throw new CLIError(`Entity not found: ${entityId}`, 1)
  }
  await ensureDir(FCP_HOME)
  await atomicWrite(DEFAULT_FILE, entityId + '\n')
  process.stdout.write(`  Default set to: ${entityId}\n`)
}

// ─── fcp unset ────────────────────────────────────────────────────────────────

async function runUnset(): Promise<void> {
  if (!existsSync(DEFAULT_FILE)) {
    process.stdout.write('  No default entity set.\n')
    return
  }
  await fs.unlink(DEFAULT_FILE)
  process.stdout.write('  Default entity cleared.\n')
}

// ─── fcp remove <entityId> ───────────────────────────────────────────────────

async function runRemove(entityId: string, opts: { force?: boolean }): Promise<void> {
  const root = path.join(ENTITIES_DIR, entityId)
  if (!existsSync(root)) {
    throw new CLIError(`Entity not found: ${entityId}`, 1)
  }

  const layout    = createLayout(root)
  const activated = await fileExists(layout.memory.imprint)

  if (activated && !opts.force) {
    throw new CLIError(
      `Entity "${entityId}" is activated (has imprint). Use --force to remove it.`, 1,
    )
  }

  // Check if a session is currently active
  if (await fileExists(layout.state.sentinels.sessionToken)) {
    throw new CLIError(
      `Entity "${entityId}" has an active session. Close the session before removing.`, 1,
    )
  }

  await fs.rm(root, { recursive: true, force: true })

  // Clear default if it pointed to this entity
  const defaultId = await getDefault()
  if (defaultId === entityId) {
    await fs.unlink(DEFAULT_FILE)
    process.stdout.write(`  Removed: ${entityId}  (was default — cleared)\n`)
  } else {
    process.stdout.write(`  Removed: ${entityId}\n`)
  }
}

// ─── Registration ─────────────────────────────────────────────────────────────

export function registerEntities(program: Command): void {
  program
    .command('list')
    .description('List all entities')
    .action(async () => { await runList() })

  program
    .command('set <entityId>')
    .description('Set the default entity')
    .action(async (entityId: string) => { await runSet(entityId) })

  program
    .command('unset')
    .description('Clear the default entity')
    .action(async () => { await runUnset() })

  program
    .command('remove <entityId>')
    .description('Remove an entity')
    .option('--force', 'Remove even if entity is activated (has imprint)')
    .action(async (entityId: string, opts: { force?: boolean }) => {
      await runRemove(entityId, opts)
    })
}
