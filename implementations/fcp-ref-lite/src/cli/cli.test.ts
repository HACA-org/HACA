import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { buildProgram } from './dispatch.js'

function run(...args: string[]) {
  const program = buildProgram()
  program.exitOverride() // prevent process.exit in tests
  return program.parseAsync(['node', 'fcp', ...args])
}

describe('CLI dispatch', () => {
  let consoleSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
  })

  afterEach(() => consoleSpy.mockRestore())

  it('fcp --help does not throw', async () => {
    const program = buildProgram()
    program.exitOverride()
    expect(() => program.parse(['node', 'fcp', '--help'])).toThrow() // exitOverride throws on --help
  })

  it('fcp (no args) triggers default action', async () => {
    await run()
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('boot not yet implemented'))
  })

  it('fcp init', async () => {
    await run('init')
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('init'))
  })

  it('fcp init --reset', async () => {
    await run('init', '--reset')
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('init'))
  })

  it('fcp list', async () => {
    await run('list')
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('list'))
  })

  it('fcp status', async () => {
    await run('status')
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('status'))
  })

  it('fcp model', async () => {
    await run('model')
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('model'))
  })

  it('fcp set <id>', async () => {
    await run('set', 'alice')
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('set'))
  })

  it('fcp unset', async () => {
    await run('unset')
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('unset'))
  })

  it('fcp remove <id>', async () => {
    await run('remove', 'alice')
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('remove'))
  })

  it('fcp doctor', async () => {
    await run('doctor')
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('doctor'))
  })

  it('fcp doctor --fix', async () => {
    await run('doctor', '--fix')
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('doctor'))
  })

  it('fcp endure --sync', async () => {
    await run('endure', '--sync')
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('endure'))
  })

  it('fcp agenda', async () => {
    await run('agenda')
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('agenda'))
  })

  it('fcp update', async () => {
    await run('update')
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('update'))
  })

  it('fcp update --dry-run', async () => {
    await run('update', '--dry-run')
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('update'))
  })

  it('fcp --auto <cron_id>', async () => {
    await run('--auto', 'daily-summary')
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('daily-summary'))
  })

})
