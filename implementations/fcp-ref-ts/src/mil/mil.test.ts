// MIL unit tests — episodic, semantic, working memory, recall, processClosure.
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
      consolidation:  'Session went well. Finished the implementation.',
      promotion:      ['key-decision'],
      working_memory: [{ priority: 7, path: 'src/main.ts' }],
    }, 10)

    // Check semantic promotion was created
    const semantic = await searchSemantic(layout, 'key-decision')
    expect(semantic.length).toBeGreaterThan(0)

    // Check working memory was updated
    const wm = await getWorkingMemory(layout)
    expect(wm.entries.some(e => e.path === 'src/main.ts')).toBe(true)
  })
})
