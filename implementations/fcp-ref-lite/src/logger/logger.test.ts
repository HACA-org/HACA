import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mkdtemp, rm, readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createLogger } from './logger.js'

describe('Logger', () => {
  let tmp: string
  let logPath: string
  let countersPath: string

  beforeEach(async () => {
    tmp = await mkdtemp(join(tmpdir(), 'fcp-logger-'))
    logPath = join(tmp, 'entity.log')
    countersPath = join(tmp, 'counters.json')
  })

  afterEach(async () => {
    await rm(tmp, { recursive: true, force: true })
  })

  it('writes structured log entries', async () => {
    const logger = createLogger(logPath, countersPath)
    await logger.info('boot', 'fap_start')
    const raw = await readFile(logPath, 'utf8')
    const entry = JSON.parse(raw.trim())
    expect(entry.level).toBe('info')
    expect(entry.component).toBe('boot')
    expect(entry.event).toBe('fap_start')
    expect(entry.ts).toMatch(/^\d{4}-/)
  })

  it('appends multiple entries', async () => {
    const logger = createLogger(logPath, countersPath)
    await logger.info('boot', 'start')
    await logger.warn('session', 'slow_cycle', { ms: 3000 })
    await logger.error('cpe', 'invoke_failed', { reason: 'timeout' })
    const lines = (await readFile(logPath, 'utf8')).trim().split('\n')
    expect(lines).toHaveLength(3)
    expect(JSON.parse(lines[1]!).data).toEqual({ ms: 3000 })
  })

  it('includes data field only when provided', async () => {
    const logger = createLogger(logPath, countersPath)
    await logger.info('boot', 'done')
    const entry = JSON.parse((await readFile(logPath, 'utf8')).trim())
    expect(entry).not.toHaveProperty('data')
  })

  it('auto-increments error counter on error()', async () => {
    const logger = createLogger(logPath, countersPath)
    await logger.error('cpe', 'failed')
    await logger.error('cpe', 'failed')
    const counters = await logger.getCounters()
    expect(counters.errors).toBe(2)
  })

  it('increments arbitrary counters', async () => {
    const logger = createLogger(logPath, countersPath)
    await logger.increment('sessions')
    await logger.increment('sessions')
    await logger.increment('cycles')
    const counters = await logger.getCounters()
    expect(counters.sessions).toBe(2)
    expect(counters.cycles).toBe(1)
  })

  it('getCounters returns defaults when no file exists', async () => {
    const logger = createLogger(logPath, countersPath)
    const counters = await logger.getCounters()
    expect(counters).toEqual({
      sessions: 0,
      cycles: 0,
      tool_executions: 0,
      errors: 0,
      crashes: 0,
    })
  })

  it('rotates log when file exceeds threshold', async () => {
    const { writeFile, stat } = await import('node:fs/promises')
    // Write a 5MB+ file to trigger rotation
    await writeFile(logPath, 'x'.repeat(5 * 1024 * 1024 + 1), 'utf8')
    const logger = createLogger(logPath, countersPath)
    await logger.info('test', 'after_rotation')
    const { existsSync } = await import('node:fs')
    expect(existsSync(`${logPath}.1`)).toBe(true)
    const newSize = (await stat(logPath)).size
    expect(newSize).toBeLessThan(5 * 1024 * 1024)
  })
})
