// Shared entity resolution helpers for CLI commands.
import * as path from 'node:path'
import * as os from 'node:os'
import * as fs from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { CLIError } from '../types/cli.js'

export const FCP_HOME     = path.join(os.homedir(), '.fcp')
export const ENTITIES_DIR = path.join(FCP_HOME, 'entities')
export const DEFAULT_FILE = path.join(FCP_HOME, 'default')

export async function resolveEntityRoot(entityId?: string): Promise<string> {
  if (entityId) {
    const root = path.join(ENTITIES_DIR, entityId)
    if (!existsSync(root)) throw new CLIError(`Entity not found: ${entityId}`, 1)
    return root
  }

  if (existsSync(DEFAULT_FILE)) {
    const id = (await fs.readFile(DEFAULT_FILE, 'utf8')).trim()
    if (id) {
      const root = path.join(ENTITIES_DIR, id)
      if (existsSync(root)) return root
    }
  }

  // Single entity fallback
  if (existsSync(ENTITIES_DIR)) {
    const entries = await fs.readdir(ENTITIES_DIR, { withFileTypes: true })
    const dirs = entries.filter(e => e.isDirectory())
    if (dirs.length === 1) return path.join(ENTITIES_DIR, dirs[0]!.name)
  }

  throw new CLIError('No entity found. Run `fcp init` to create one.', 1)
}
