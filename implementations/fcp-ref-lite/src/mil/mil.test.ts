import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mkdtemp, rm, mkdir } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createLayout } from '../store/layout.js'
import { writeJson } from '../store/io.js'
import { createLogger } from '../logger/logger.js'
import { createMIL } from './mil.js'
import { runGC } from './gc.js'
import type { Layout } from '../store/layout.js'
import type { ClosurePayload } from './types.js'

async function makeFixture(tmp: string): Promise<Layout> {
  const root = join(tmp, 'entity')
  const layout = createLayout(root)
  await mkdir(join(root, 'memory', 'episodic'), { recursive: true })
  await mkdir(join(root, 'memory', 'semantic'), { recursive: true })
  await mkdir(join(root, 'state'), { recursive: true })
  return layout
}

describe('MIL — remember and recall', () => {
  let tmp: string
  let layout: Layout

  beforeEach(async () => {
    tmp = await mkdtemp(join(tmpdir(), 'fcp-mil-'))
    layout = await makeFixture(tmp)
  })

  afterEach(async () => { await rm(tmp, { recursive: true, force: true }) })

  it('remember writes an episodic entry', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const mil = createMIL(layout, logger)
    const result = await mil.remember('session-1', 'The user prefers short answers')
    expect(result).toContain('Remembered')
    expect(result).toContain('The user prefers short answers')
  })

  it('recall finds content in episodic memory', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const mil = createMIL(layout, logger)
    await mil.remember('session-1', 'The user works in Python')
    const result = await mil.recall('Python')
    expect(result).toContain('Python')
    expect(result).toContain('episodic')
  })

  it('recall finds content in semantic memory', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const mil = createMIL(layout, logger)
    const ep = await mil.writeEpisodic('session-1', 'User is a senior engineer')
    await mil.promoteToSemantic(ep.id, 'User is a senior engineer', ['profile'])
    const result = await mil.recall('senior engineer')
    expect(result).toContain('semantic')
  })

  it('recall finds content in working memory', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const mil = createMIL(layout, logger)
    await mil.updateWorkingMemory([{
      id: 'wm-1',
      ref: 'episodic/abc.json',
      layer: 'episodic',
      summary: 'User is debugging a race condition',
      ts: new Date().toISOString(),
    }])
    const result = await mil.recall('race condition')
    expect(result).toContain('working_memory')
  })

  it('recall returns no-match message when nothing found', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const mil = createMIL(layout, logger)
    const result = await mil.recall('quantum entanglement')
    expect(result).toContain('No memories found')
  })
})

describe('MIL — closure processing', () => {
  let tmp: string
  let layout: Layout

  beforeEach(async () => {
    tmp = await mkdtemp(join(tmpdir(), 'fcp-mil-closure-'))
    layout = await makeFixture(tmp)
  })

  afterEach(async () => { await rm(tmp, { recursive: true, force: true }) })

  it('processes promotions from episodic to semantic', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const mil = createMIL(layout, logger)
    const ep = await mil.writeEpisodic('session-1', 'Important insight about the codebase')

    const closure: ClosurePayload = {
      ts: new Date().toISOString(),
      sessionId: 'session-1',
      messageCount: 10,
      summary: [],
      workingMemoryUpdates: [],
      promotions: [{ episodicId: ep.id, content: ep.content, tags: ['architecture'] }],
    }

    await mil.processClosure(closure)

    const result = await mil.recall('Important insight')
    expect(result).toContain('semantic')
  })

  it('processes working memory updates', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const mil = createMIL(layout, logger)

    const closure: ClosurePayload = {
      ts: new Date().toISOString(),
      sessionId: 'session-1',
      messageCount: 5,
      summary: [],
      workingMemoryUpdates: [{
        id: 'wm-1',
        ref: 'episodic/something.json',
        layer: 'episodic',
        summary: 'Working on auth refactor',
        ts: new Date().toISOString(),
      }],
      promotions: [],
    }

    await mil.processClosure(closure)
    const wm = await mil.getWorkingMemory()
    expect(wm.entries.some(e => e.summary.includes('auth refactor'))).toBe(true)
  })

  it('writes session handoff', async () => {
    const { existsSync } = await import('node:fs')
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const mil = createMIL(layout, logger)

    const closure: ClosurePayload = {
      ts: new Date().toISOString(),
      sessionId: 'session-1',
      messageCount: 8,
      summary: [],
      workingMemoryUpdates: [],
      promotions: [],
      handoff: {
        sessionId: 'session-1',
        ts: new Date().toISOString(),
        message: 'Next session: continue the auth refactor from PR #42',
      },
    }

    await mil.processClosure(closure)
    expect(existsSync(layout.sessionHandoff)).toBe(true)
    const handoff = await import('../store/io.js').then(m =>
      m.readJson<{ message: string }>(layout.sessionHandoff)
    )
    expect(handoff.message).toContain('auth refactor')
  })
})

describe('GC', () => {
  let tmp: string
  let layout: Layout

  beforeEach(async () => {
    tmp = await mkdtemp(join(tmpdir(), 'fcp-gc-'))
    layout = await makeFixture(tmp)
  })

  afterEach(async () => { await rm(tmp, { recursive: true, force: true }) })

  it('prunes episodic entries beyond maxEpisodic', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const mil = createMIL(layout, logger)

    // Write 5 episodic entries
    for (let i = 0; i < 5; i++) {
      await new Promise(r => setTimeout(r, 2)) // ensure unique timestamps
      await mil.writeEpisodic('session-1', `Entry ${i}`)
    }

    await runGC(layout, logger, { maxEpisodic: 3 })

    const { readdir } = await import('node:fs/promises')
    const files = (await readdir(layout.episodic)).filter(f => f.endsWith('.json'))
    expect(files).toHaveLength(3)
  })

  it('prunes working memory beyond maxWorkingMemory', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const mil = createMIL(layout, logger)

    await writeJson(layout.workingMemory, {
      maxEntries: 50,
      entries: Array.from({ length: 10 }, (_, i) => ({
        id: `wm-${i}`,
        ref: `episodic/${i}.json`,
        layer: 'episodic',
        summary: `Entry ${i}`,
        ts: new Date(Date.now() + i).toISOString(),
      })),
    })

    await runGC(layout, logger, { maxWorkingMemory: 5 })

    const wm = await mil.getWorkingMemory()
    expect(wm.entries).toHaveLength(5)
  })

  it('runs without error when episodic and working memory are empty', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    await expect(runGC(layout, logger)).resolves.not.toThrow()
  })
})
