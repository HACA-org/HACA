// Integration test: drainInbox reads .msg files and deletes them.
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import * as os from 'node:os'
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { createLayout } from '../../src/types/store.js'
import { drainInbox } from '../../src/session/inbox.js'

let tmpDir: string

beforeEach(async () => {
  tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'fcp-inbox-'))
})

afterEach(async () => {
  await fs.rm(tmpDir, { recursive: true, force: true })
})

describe('session/inbox — drainInbox', () => {
  it('returns empty array when inbox does not exist', async () => {
    const layout = createLayout(tmpDir)
    const msgs = await drainInbox(layout)
    expect(msgs).toHaveLength(0)
  })

  it('returns empty array when inbox is empty', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.io.inbox, { recursive: true })
    const msgs = await drainInbox(layout)
    expect(msgs).toHaveLength(0)
  })

  it('reads .msg files and returns them as user CPEMessages', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.io.inbox, { recursive: true })
    await fs.writeFile(path.join(layout.io.inbox, '001.msg'), JSON.stringify({ message: 'hello from operator' }))
    await fs.writeFile(path.join(layout.io.inbox, '002.msg'), JSON.stringify({ message: 'second message' }))

    const msgs = await drainInbox(layout)
    expect(msgs).toHaveLength(2)
    expect(msgs.every(m => m.role === 'user')).toBe(true)
  })

  it('deletes .msg files after reading', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.io.inbox, { recursive: true })
    const filePath = path.join(layout.io.inbox, 'test.msg')
    await fs.writeFile(filePath, JSON.stringify({ message: 'test' }))

    await drainInbox(layout)
    await expect(fs.access(filePath)).rejects.toThrow()
  })

  it('ignores non-.msg files', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.io.inbox, { recursive: true })
    await fs.writeFile(path.join(layout.io.inbox, 'note.txt'), 'not a message')
    await fs.writeFile(path.join(layout.io.inbox, 'valid.msg'), JSON.stringify({ message: 'valid' }))

    const msgs = await drainInbox(layout)
    expect(msgs).toHaveLength(1)
  })

  it('does not drain presession/ subdirectory (boot territory)', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.io.presession, { recursive: true })
    await fs.writeFile(path.join(layout.io.presession, 'boot.msg'), JSON.stringify({ message: 'presession' }))

    const msgs = await drainInbox(layout)
    expect(msgs).toHaveLength(0)
    // presession file still exists
    await expect(fs.access(path.join(layout.io.presession, 'boot.msg'))).resolves.toBeUndefined()
  })
})
