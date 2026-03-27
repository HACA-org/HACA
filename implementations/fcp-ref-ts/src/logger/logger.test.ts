import { describe, it, expect, vi, afterEach } from 'vitest'
import { createLogger } from './logger.js'

describe('logger', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('writes JSON line to stderr', () => {
    const spy = vi.spyOn(process.stderr, 'write').mockReturnValue(true)
    createLogger().info('hello')
    expect(spy).toHaveBeenCalledOnce()
    const line = JSON.parse((spy.mock.calls[0]![0] as string).trim()) as Record<string, unknown>
    expect(line['level']).toBe('info')
    expect(line['msg']).toBe('hello')
    expect(typeof line['ts']).toBe('string')
  })

  it('includes data field when provided', () => {
    const spy = vi.spyOn(process.stderr, 'write').mockReturnValue(true)
    createLogger().debug('ctx', { x: 1 })
    const line = JSON.parse((spy.mock.calls[0]![0] as string).trim()) as Record<string, unknown>
    expect(line['data']).toEqual({ x: 1 })
  })

  it('omits data key when data is undefined', () => {
    const spy = vi.spyOn(process.stderr, 'write').mockReturnValue(true)
    createLogger().warn('no data')
    const line = JSON.parse((spy.mock.calls[0]![0] as string).trim()) as Record<string, unknown>
    expect('data' in line).toBe(false)
  })

  it('respects log levels', () => {
    const spy = vi.spyOn(process.stderr, 'write').mockReturnValue(true)
    const log = createLogger()
    log.debug('d')
    log.info('i')
    log.warn('w')
    log.error('e')
    const levels = spy.mock.calls
      .map(c => JSON.parse((c[0] as string).trim()) as Record<string, unknown>)
      .map(l => l['level'])
    expect(levels).toEqual(['debug', 'info', 'warn', 'error'])
  })

  it('child() inherits parent context', () => {
    const spy = vi.spyOn(process.stderr, 'write').mockReturnValue(true)
    createLogger({ component: 'boot' }).child({ phase: 3 }).info('running')
    const line = JSON.parse((spy.mock.calls[0]![0] as string).trim()) as Record<string, unknown>
    expect(line['component']).toBe('boot')
    expect(line['phase']).toBe(3)
  })

  it('child() does not mutate parent context', () => {
    const spy = vi.spyOn(process.stderr, 'write').mockReturnValue(true)
    const parent = createLogger({ component: 'boot' })
    parent.child({ phase: 3 })
    parent.info('parent log')
    const line = JSON.parse((spy.mock.calls[0]![0] as string).trim()) as Record<string, unknown>
    expect('phase' in line).toBe(false)
  })
})
