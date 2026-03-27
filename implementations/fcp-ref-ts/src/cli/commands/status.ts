// fcp status — display entity state overview without starting a session.
import * as path from 'node:path'
import * as os from 'node:os'
import * as fs from 'node:fs/promises'
import { existsSync } from 'node:fs'
import type { Command } from 'commander'
import { createLayout } from '../../types/store.js'
import { fileExists, readJson } from '../../store/io.js'
import { CLIError } from '../../types/cli.js'

const ENTITIES_DIR = path.join(os.homedir(), '.fcp', 'entities')
const DEFAULT_FILE = path.join(os.homedir(), '.fcp', 'default')

async function listEntities(): Promise<string[]> {
  if (!existsSync(ENTITIES_DIR)) return []
  const entries = await fs.readdir(ENTITIES_DIR, { withFileTypes: true })
  return entries.filter(e => e.isDirectory()).map(e => e.name)
}

export async function runStatus(entityId?: string): Promise<void> {
  const entities = await listEntities()
  if (entities.length === 0) {
    throw new CLIError('No entities found. Run `fcp init`.', 1)
  }

  const defaultId = existsSync(DEFAULT_FILE)
    ? (await fs.readFile(DEFAULT_FILE, 'utf8')).trim()
    : null

  const targets = entityId ? [entityId] : entities

  for (const id of targets) {
    if (!entities.includes(id)) {
      process.stdout.write(`  ${id}: not found\n`)
      continue
    }
    const root   = path.join(ENTITIES_DIR, id)
    const layout = createLayout(root)

    const isDefault = id === defaultId
    const imprintExists = await fileExists(layout.memory.imprint)
    const tokenExists   = await fileExists(layout.state.sentinels.sessionToken)

    let profile = 'unknown'
    let backend = 'unknown'
    if (await fileExists(layout.state.baseline)) {
      try {
        const raw = await readJson(layout.state.baseline) as Record<string, unknown>
        const cpe = raw['cpe'] as Record<string, unknown> | undefined
        backend = typeof cpe?.['backend'] === 'string' ? cpe['backend'] : 'unknown'
        profile = typeof cpe?.['topology'] === 'string'
          ? (cpe['topology'] === 'opaque' ? 'HACA-Evolve' : 'HACA-Core')
          : 'unknown'
      } catch { /* ignore */ }
    }

    process.stdout.write(`\n  Entity: ${id}${isDefault ? '  (default)' : ''}\n`)
    process.stdout.write(`    path:     ${root}\n`)
    process.stdout.write(`    profile:  ${profile}\n`)
    process.stdout.write(`    backend:  ${backend}\n`)
    process.stdout.write(`    imprint:  ${imprintExists ? 'present' : 'absent (cold start pending)'}\n`)
    process.stdout.write(`    session:  ${tokenExists ? 'ACTIVE' : 'closed'}\n`)
  }
  process.stdout.write('\n')
}

export function registerStatus(program: Command): void {
  program
    .command('status [entity]')
    .description('Show entity status')
    .action(async (entity?: string) => {
      await runStatus(entity)
    })
}
