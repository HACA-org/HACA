import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import * as fs from 'node:fs/promises'
import * as os from 'node:os'
import * as path from 'node:path'
import {
  readJson, writeJson, appendJsonl, readJsonl,
  atomicWrite, ensureDir, fileExists, drainMsgDir, deleteFile,
  IOError,
} from './io.js'

describe('store/io', () => {
  let tmp: string

  beforeEach(async () => {
    tmp = await fs.mkdtemp(path.join(os.tmpdir(), 'fcp-io-test-'))
  })

  afterEach(async () => {
    await fs.rm(tmp, { recursive: true, force: true })
  })

  // --- writeJson / readJson ---

  describe('writeJson / readJson', () => {
    it('round-trips a JSON object', async () => {
      const file = path.join(tmp, 'data.json')
      await writeJson(file, { foo: 'bar', n: 42 })
      expect(await readJson(file)).toEqual({ foo: 'bar', n: 42 })
    })

    it('second writeJson overwrites the first', async () => {
      const file = path.join(tmp, 'state.json')
      await writeJson(file, { v: 1 })
      await writeJson(file, { v: 2 })
      expect(await readJson(file)).toEqual({ v: 2 })
    })

    it('leaves original untouched if .tmp exists but rename never ran', async () => {
      const file = path.join(tmp, 'state.json')
      await writeJson(file, { original: true })
      // Simulate a crash between writeFile(.tmp) and rename: write orphan .tmp
      await fs.writeFile(file + '.tmp', '{"crashed":true}', 'utf8')
      // Original is unaffected — rename never ran
      expect(await readJson(file)).toEqual({ original: true })
    })

    it('throws IOError on missing file', async () => {
      await expect(readJson(path.join(tmp, 'nope.json'))).rejects.toBeInstanceOf(IOError)
    })

    it('throws IOError on malformed JSON', async () => {
      const file = path.join(tmp, 'bad.json')
      await fs.writeFile(file, 'not json', 'utf8')
      await expect(readJson(file)).rejects.toBeInstanceOf(IOError)
    })
  })

  // --- appendJsonl / readJsonl ---

  describe('appendJsonl / readJsonl', () => {
    it('appends multiple lines and reads them back in order', async () => {
      const file = path.join(tmp, 'log.jsonl')
      await appendJsonl(file, { a: 1 })
      await appendJsonl(file, { b: 2 })
      await appendJsonl(file, { c: 3 })
      expect(await readJsonl(file)).toEqual([{ a: 1 }, { b: 2 }, { c: 3 }])
    })

    it('readJsonl handles empty file', async () => {
      const file = path.join(tmp, 'empty.jsonl')
      await fs.writeFile(file, '', 'utf8')
      expect(await readJsonl(file)).toEqual([])
    })

    it('readJsonl ignores trailing blank lines', async () => {
      const file = path.join(tmp, 'trail.jsonl')
      await fs.writeFile(file, '{"x":1}\n\n\n', 'utf8')
      expect(await readJsonl(file)).toEqual([{ x: 1 }])
    })

    it('readJsonl throws IOError on malformed line', async () => {
      const file = path.join(tmp, 'bad.jsonl')
      await fs.writeFile(file, '{"ok":1}\nnot json\n', 'utf8')
      await expect(readJsonl(file)).rejects.toBeInstanceOf(IOError)
    })

    it('appendJsonl creates the file on first write', async () => {
      const file = path.join(tmp, 'new.jsonl')
      await appendJsonl(file, { first: true })
      expect(await fileExists(file)).toBe(true)
    })
  })

  // --- invariant: writeJson and appendJsonl are not interchangeable ---

  it('writeJson replaces content; appendJsonl accumulates', async () => {
    const jfile  = path.join(tmp, 'test.json')
    const jlfile = path.join(tmp, 'test.jsonl')

    await writeJson(jfile, { v: 1 })
    await writeJson(jfile, { v: 2 })
    expect(await readJson(jfile)).toEqual({ v: 2 })     // overwritten

    await appendJsonl(jlfile, { v: 1 })
    await appendJsonl(jlfile, { v: 2 })
    expect(await readJsonl(jlfile)).toHaveLength(2)      // accumulated
  })

  // --- ensureDir / fileExists ---

  it('ensureDir creates nested directories', async () => {
    const dir = path.join(tmp, 'a', 'b', 'c')
    await ensureDir(dir)
    expect(await fileExists(dir)).toBe(true)
  })

  it('ensureDir is idempotent', async () => {
    const dir = path.join(tmp, 'idempotent')
    await ensureDir(dir)
    await expect(ensureDir(dir)).resolves.toBeUndefined()
  })

  it('fileExists returns false for absent path', async () => {
    expect(await fileExists(path.join(tmp, 'missing'))).toBe(false)
  })

  // --- drainMsgDir ---

  it('drainMsgDir reads .msg files in sorted filename order', async () => {
    const inbox = path.join(tmp, 'inbox')
    await ensureDir(inbox)
    await fs.writeFile(path.join(inbox, 'b.msg'), '{"seq":2}', 'utf8')
    await fs.writeFile(path.join(inbox, 'a.msg'), '{"seq":1}', 'utf8')
    const results = await drainMsgDir(inbox)
    expect(results.map(r => (r.raw as { seq: number }).seq)).toEqual([1, 2])
  })

  it('drainMsgDir ignores non-.msg files', async () => {
    const inbox = path.join(tmp, 'inbox2')
    await ensureDir(inbox)
    await fs.writeFile(path.join(inbox, 'a.msg'), '{"ok":true}', 'utf8')
    await fs.writeFile(path.join(inbox, 'ignore.json'), '{}', 'utf8')
    const results = await drainMsgDir(inbox)
    expect(results).toHaveLength(1)
  })

  // --- deleteFile ---

  it('deleteFile removes an existing file', async () => {
    const file = path.join(tmp, 'del.json')
    await fs.writeFile(file, '{}', 'utf8')
    await deleteFile(file)
    expect(await fileExists(file)).toBe(false)
  })

  it('deleteFile throws IOError on missing file', async () => {
    await expect(deleteFile(path.join(tmp, 'nope'))).rejects.toBeInstanceOf(IOError)
  })
})
