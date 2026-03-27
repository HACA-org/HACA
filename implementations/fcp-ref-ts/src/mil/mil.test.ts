// MIL unit tests — episodic, semantic, working memory, recall, processClosure, tool handlers.
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import * as os from 'node:os'
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { createLayout } from '../types/store.js'
import { createLogger } from '../logger/logger.js'
import { writeEpisodic, rotateEpisodic } from './episodic.js'
import { writeSemantic, searchSemantic } from './semantic.js'
import { getWorkingMemory, setWorkingMemory, mergeWorkingMemory } from './working.js'
import { recall, processClosure } from './recall.js'
import { memoryRecallHandler } from './tools/memory-recall.js'
import { memoryWriteHandler }  from './tools/memory-write.js'
import { closurePayloadHandler } from './tools/closure-payload.js'
import type { ExecContext } from '../types/exec.js'

function makeCtx(layout: ReturnType<typeof createLayout>): ExecContext {
  return {
    layout,
    baseline:       {} as import('../types/formats/baseline.js').Baseline,
    logger:         createLogger({ test: true }),
    sessionId:      'test-session',
    policy:         { commands: [], domains: [], skills: [],
      async addCommand() {}, async addDomain() {}, async addSkill() {} },
    io:             { async prompt() { return '' }, write() {} },
    firstWriteDone: { value: false },
  }
}

let tmpDir: string

beforeEach(async () => {
  tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'fcp-mil-'))
})

afterEach(async () => {
  await fs.rm(tmpDir, { recursive: true, force: true })
})

const SESSION_ID = '00000000-0000-0000-0000-000000000001'

describe('MIL — episodic', () => {
  it('writeEpisodic creates a session directory and file', async () => {
    const layout = createLayout(tmpDir)
    const entry = await writeEpisodic(layout, SESSION_ID, 'summary', '# Session summary')
    expect(entry.sessionId).toBe(SESSION_ID)
    expect(entry.sizeBytes).toBeGreaterThan(0)
    await expect(fs.access(path.join(tmpDir, entry.path))).resolves.toBeUndefined()
  })

  it('rotateEpisodic removes old session dirs beyond MAX_SESSIONS=5', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.memory.episodic, { recursive: true })
    // Create 7 fake session dirs
    for (let i = 1; i <= 7; i++) {
      const name = `2026-01-${String(i).padStart(2, '0')}-sessionid`
      await fs.mkdir(path.join(layout.memory.episodic, name))
    }
    await rotateEpisodic(layout)
    const remaining = await fs.readdir(layout.memory.episodic)
    expect(remaining).toHaveLength(5)
  })
})

describe('MIL — semantic', () => {
  it('writeSemantic creates a .md file in memory/semantic/', async () => {
    const layout = createLayout(tmpDir)
    const entry = await writeSemantic(layout, 'my-concept', '# My Concept\nImportant info.')
    expect(entry.slug).toBe('my-concept')
    await expect(fs.access(path.join(tmpDir, entry.path))).resolves.toBeUndefined()
  })

  it('searchSemantic finds files by content', async () => {
    const layout = createLayout(tmpDir)
    await writeSemantic(layout, 'alpha', '# Alpha\nThis is about apples.')
    await writeSemantic(layout, 'beta',  '# Beta\nThis is about bananas.')
    const results = await searchSemantic(layout, 'apples')
    expect(results).toHaveLength(1)
    expect(results[0]!.slug).toBe('alpha')
  })

  it('searchSemantic returns empty when nothing matches', async () => {
    const layout = createLayout(tmpDir)
    await writeSemantic(layout, 'doc', '# Doc\nSome content.')
    const results = await searchSemantic(layout, 'zzz-nomatch')
    expect(results).toHaveLength(0)
  })
})

describe('MIL — working memory', () => {
  it('getWorkingMemory returns empty when file does not exist', async () => {
    const layout = createLayout(tmpDir)
    const wm = await getWorkingMemory(layout)
    expect(wm.entries).toHaveLength(0)
  })

  it('setWorkingMemory and getWorkingMemory round-trip', async () => {
    const layout = createLayout(tmpDir)
    await setWorkingMemory(layout, {
      version: '1.0',
      entries: [{ priority: 5, path: 'docs/important.md' }],
    })
    const wm = await getWorkingMemory(layout)
    expect(wm.entries).toHaveLength(1)
    expect(wm.entries[0]!.path).toBe('docs/important.md')
  })

  it('mergeWorkingMemory deduplicates by path and prunes to maxEntries', async () => {
    const layout = createLayout(tmpDir)
    await setWorkingMemory(layout, {
      version: '1.0',
      entries: [
        { priority: 3, path: 'a.md' },
        { priority: 2, path: 'b.md' },
      ],
    })
    await mergeWorkingMemory(layout, [
      { priority: 10, path: 'a.md' },  // override a.md with higher priority
      { priority: 1,  path: 'c.md' },
    ], 2)  // maxEntries = 2
    const wm = await getWorkingMemory(layout)
    expect(wm.entries).toHaveLength(2)
    expect(wm.entries[0]!.path).toBe('a.md')  // highest priority first
    expect(wm.entries[0]!.priority).toBe(10)
  })
})

describe('MIL — recall', () => {
  it('returns found:false when nothing matches', async () => {
    const layout = createLayout(tmpDir)
    const result = await recall(layout, 'zzz-never-matches')
    expect(result.found).toBe(false)
  })

  it('finds working memory entries by path', async () => {
    const layout = createLayout(tmpDir)
    await setWorkingMemory(layout, { version: '1.0', entries: [{ priority: 5, path: 'notes/todo.md' }] })
    const result = await recall(layout, 'todo')
    expect(result.found).toBe(true)
    if (result.found) {
      expect(result.matches[0]!.source).toBe('working')
    }
  })

  it('finds semantic entries by content', async () => {
    const layout = createLayout(tmpDir)
    await writeSemantic(layout, 'project-goals', '# Project Goals\nComplete the reference implementation.')
    const result = await recall(layout, 'reference implementation')
    expect(result.found).toBe(true)
    if (result.found) {
      expect(result.matches.some(m => m.source === 'semantic')).toBe(true)
    }
  })
})

describe('MIL — processClosure', () => {
  it('writes episodic consolidation and promotes slugs', async () => {
    const layout = createLayout(tmpDir)
    const logger = createLogger({ test: true })
    await processClosure(layout, SESSION_ID, logger, {
      consolidation: 'Session went well. Finished the implementation.',
      promotion:     ['key-decision'],
      workingMemory: [{ priority: 7, path: 'src/main.ts' }],
    }, 10)

    // Check semantic promotion was created
    const semantic = await searchSemantic(layout, 'key-decision')
    expect(semantic.length).toBeGreaterThan(0)

    // Check working memory was updated
    const wm = await getWorkingMemory(layout)
    expect(wm.entries.some(e => e.path === 'src/main.ts')).toBe(true)
  })
})

// ─── MIL tool handlers ────────────────────────────────────────────────────────

describe('MIL — fcp_memory_write', () => {
  it('writes an episodic entry and returns the path', async () => {
    const layout = createLayout(tmpDir)
    const ctx    = makeCtx(layout)
    const r = await memoryWriteHandler.execute({ slug: 'my-note', content: 'Some content.' }, ctx)
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.output).toMatch(/my-note/)
  })

  it('requires slug', async () => {
    const ctx = makeCtx(createLayout(tmpDir))
    const r   = await memoryWriteHandler.execute({ content: 'hello' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/slug/)
  })

  it('requires content', async () => {
    const ctx = makeCtx(createLayout(tmpDir))
    const r   = await memoryWriteHandler.execute({ slug: 'note' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/content/)
  })

  it('rejects whitespace-only content', async () => {
    const ctx = makeCtx(createLayout(tmpDir))
    const r   = await memoryWriteHandler.execute({ slug: 'note', content: '   ' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/empty/)
  })

  it('rejects invalid slug format', async () => {
    const ctx = makeCtx(createLayout(tmpDir))
    const r   = await memoryWriteHandler.execute({ slug: 'My Note!', content: 'hi' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/slug/)
  })
})

describe('MIL — fcp_memory_recall', () => {
  it('returns no-match message when nothing found', async () => {
    const ctx = makeCtx(createLayout(tmpDir))
    const r   = await memoryRecallHandler.execute({ query: 'zzz-never-matches' }, ctx)
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.output).toMatch(/No memory found/)
  })

  it('finds content written via memory-write', async () => {
    const layout = createLayout(tmpDir)
    const ctx    = makeCtx(layout)
    await memoryWriteHandler.execute({ slug: 'test-topic', content: 'unique-keyword-xyz' }, ctx)
    const r = await memoryRecallHandler.execute({ query: 'unique-keyword-xyz' }, ctx)
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.output).toContain('unique-keyword-xyz')
  })

  it('requires query', async () => {
    const ctx = makeCtx(createLayout(tmpDir))
    const r   = await memoryRecallHandler.execute({}, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/query/)
  })

  it('rejects empty query', async () => {
    const ctx = makeCtx(createLayout(tmpDir))
    const r   = await memoryRecallHandler.execute({ query: '' }, ctx)
    expect(r.ok).toBe(false)
  })
})

describe('MIL — fcp_closure_payload', () => {
  const VALID_PAYLOAD = {
    type:          'closure_payload' as const,
    consolidation: 'Session summary.',
    promotion:     ['key-concept'],
    workingMemory: [{ priority: 5, path: 'src/main.ts' }],
    sessionHandoff: { pendingTasks: [], nextSteps: 'Continue tomorrow.' },
  }

  it('stages a valid closure payload to pending-closure.json', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.state.dir, { recursive: true })
    const ctx = makeCtx(layout)
    const r = await closurePayloadHandler.execute(VALID_PAYLOAD, ctx)
    expect(r.ok).toBe(true)
    const raw = JSON.parse(await fs.readFile(layout.state.pendingClosure, 'utf8'))
    expect(raw.consolidation).toBe('Session summary.')
    expect(raw.promotion).toContain('key-concept')
  })

  it('creates state/ dir if missing', async () => {
    const layout = createLayout(tmpDir)
    const ctx    = makeCtx(layout)
    const r = await closurePayloadHandler.execute(VALID_PAYLOAD, ctx)
    expect(r.ok).toBe(true)
    await expect(fs.access(layout.state.pendingClosure)).resolves.toBeUndefined()
  })

  it('rejects invalid payload', async () => {
    const ctx = makeCtx(createLayout(tmpDir))
    const r   = await closurePayloadHandler.execute({ bad: 'data' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/invalid closure payload/)
  })
})
