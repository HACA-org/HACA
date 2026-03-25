import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createLayout } from './layout.js'
import {
  fileExists,
  readJson,
  writeJson,
  appendJsonl,
  readJsonl,
  touchFile,
  removeFile,
} from './io.js'

describe('Layout', () => {
  it('resolves all paths relative to root', () => {
    const layout = createLayout('/home/user/.fcp/entities/alice')
    expect(layout.root).toBe('/home/user/.fcp/entities/alice')
    expect(layout.baseline).toBe('/home/user/.fcp/entities/alice/state/baseline.json')
    expect(layout.sessionToken).toBe('/home/user/.fcp/entities/alice/state/session.token')
    expect(layout.imprint).toBe('/home/user/.fcp/entities/alice/memory/imprint.json')
    expect(layout.inbox).toBe('/home/user/.fcp/entities/alice/io/inbox')
  })

  it('resolves skill paths by name', () => {
    const layout = createLayout('/root')
    expect(layout.skill('my-skill')).toBe('/root/skills/my-skill')
    expect(layout.skillManifest('my-skill')).toBe('/root/skills/my-skill/manifest.json')
  })
})

describe('IO', () => {
  let tmp: string

  beforeEach(async () => {
    tmp = await mkdtemp(join(tmpdir(), 'fcp-test-'))
  })

  afterEach(async () => {
    await rm(tmp, { recursive: true, force: true })
  })

  it('writeJson creates parent dirs and writes atomically', async () => {
    const path = join(tmp, 'nested', 'file.json')
    await writeJson(path, { hello: 'world' })
    const result = await readJson<{ hello: string }>(path)
    expect(result.hello).toBe('world')
  })

  it('writeJson overwrites existing file atomically', async () => {
    const path = join(tmp, 'file.json')
    await writeJson(path, { v: 1 })
    await writeJson(path, { v: 2 })
    const result = await readJson<{ v: number }>(path)
    expect(result.v).toBe(2)
  })

  it('appendJsonl appends entries as newline-delimited JSON', async () => {
    const path = join(tmp, 'log.jsonl')
    await appendJsonl(path, { a: 1 })
    await appendJsonl(path, { a: 2 })
    const entries = await readJsonl<{ a: number }>(path)
    expect(entries).toEqual([{ a: 1 }, { a: 2 }])
  })

  it('readJsonl returns empty array for missing file', async () => {
    const result = await readJsonl(join(tmp, 'missing.jsonl'))
    expect(result).toEqual([])
  })

  it('touchFile creates an empty sentinel file', async () => {
    const path = join(tmp, 'session.token')
    await touchFile(path)
    expect(fileExists(path)).toBe(true)
  })

  it('touchFile does not overwrite existing file', async () => {
    const path = join(tmp, 'file.txt')
    await writeJson(path, { data: 'keep' })
    await touchFile(path)
    const result = await readJson<{ data: string }>(path)
    expect(result.data).toBe('keep')
  })

  it('removeFile deletes a file', async () => {
    const path = join(tmp, 'file.json')
    await writeJson(path, {})
    await removeFile(path)
    expect(fileExists(path)).toBe(false)
  })

  it('removeFile is silent on missing file', async () => {
    await expect(removeFile(join(tmp, 'ghost.json'))).resolves.not.toThrow()
  })
})
