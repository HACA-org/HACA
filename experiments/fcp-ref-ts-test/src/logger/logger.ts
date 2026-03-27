import { appendFile, rename, stat } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { ensureDir, readJson, writeJson } from '../store/io.js'

export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

export interface LogEntry {
  ts: string
  level: LogLevel
  component: string
  event: string
  data?: Record<string, unknown>
}

export interface Counters {
  sessions: number
  cycles: number
  tool_executions: number
  errors: number
  crashes: number
}

const DEFAULT_COUNTERS: Counters = {
  sessions: 0,
  cycles: 0,
  tool_executions: 0,
  errors: 0,
  crashes: 0,
}

const ROTATION_THRESHOLD = 5 * 1024 * 1024 // 5MB

export type Logger = ReturnType<typeof createLogger>

export function createLogger(logPath: string, countersPath: string) {
  async function rotate(): Promise<void> {
    if (!existsSync(logPath)) return
    const { size } = await stat(logPath)
    if (size >= ROTATION_THRESHOLD) {
      await rename(logPath, `${logPath}.1`)
    }
  }

  async function write(level: LogLevel, component: string, event: string, data?: Record<string, unknown>): Promise<void> {
    await rotate()
    await ensureDir(dirname(logPath))
    const entry: LogEntry = { ts: new Date().toISOString(), level, component, event, ...(data ? { data } : {}) }
    await appendFile(logPath, JSON.stringify(entry) + '\n', 'utf8')
    if (level === 'error') await increment('errors')
  }

  async function increment(counter: keyof Counters): Promise<void> {
    const counters = existsSync(countersPath)
      ? await readJson<Counters>(countersPath)
      : { ...DEFAULT_COUNTERS }
    counters[counter]++
    await writeJson(countersPath, counters)
  }

  async function getCounters(): Promise<Counters> {
    if (!existsSync(countersPath)) return { ...DEFAULT_COUNTERS }
    return readJson<Counters>(countersPath)
  }

  return {
    debug: (component: string, event: string, data?: Record<string, unknown>) => write('debug', component, event, data),
    info: (component: string, event: string, data?: Record<string, unknown>) => write('info', component, event, data),
    warn: (component: string, event: string, data?: Record<string, unknown>) => write('warn', component, event, data),
    error: (component: string, event: string, data?: Record<string, unknown>) => write('error', component, event, data),
    increment,
    getCounters,
  }
}
