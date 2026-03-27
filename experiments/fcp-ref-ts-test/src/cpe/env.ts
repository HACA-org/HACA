import { readFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { homedir } from 'node:os'

const FCP_ENV_PATH = join(homedir(), '.fcp', '.env')

let loaded = false

export async function loadEnv(): Promise<void> {
  if (loaded) return
  loaded = true
  if (!existsSync(FCP_ENV_PATH)) return
  const raw = await readFile(FCP_ENV_PATH, 'utf8')
  for (const line of raw.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const eq = trimmed.indexOf('=')
    if (eq === -1) continue
    const key = trimmed.slice(0, eq).trim()
    const value = trimmed.slice(eq + 1).trim().replace(/^["']|["']$/g, '')
    if (key && !(key in process.env)) {
      process.env[key] = value
    }
  }
}

export function getEnv(key: string): string | undefined {
  return process.env[key]
}

export function requireEnv(key: string): string {
  const value = process.env[key]
  if (!value) throw new Error(`Missing required environment variable: ${key}`)
  return value
}
