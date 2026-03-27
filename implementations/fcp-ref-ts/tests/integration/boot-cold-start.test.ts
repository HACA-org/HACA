// Integration test: FAP cold-start on an empty entity directory.
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import * as os from 'node:os'
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { createLayout } from '../../src/types/store.js'
import { startEntity } from '../../src/boot/boot.js'
import { createLogger } from '../../src/logger/logger.js'
import type { BootIO } from '../../src/types/boot.js'

const MINIMAL_BASELINE = {
  version:  '1.0',
  entityId: 'test-entity',
  cpe: { topology: 'transparent', backend: 'anthropic:claude-sonnet-4-6' },
  heartbeat:        { cycleThreshold: 50, intervalSeconds: 60 },
  watchdog:         { silThresholdSeconds: 300 },
  contextWindow:    { budgetTokens: 100000, criticalPct: 90 },
  drift:            { comparisonMechanism: 'ncd-gzip-v1', threshold: 0.3 },
  sessionStore:     { rotationThresholdBytes: 1048576 },
  workingMemory:    { maxEntries: 10 },
  integrityChain:   { checkpointInterval: 10 },
  preSessionBuffer: { maxEntries: 5 },
  operatorChannel:  { notificationsDir: 'state/operator-notifications' },
  fault:            { nBoot: 3, nChannel: 3, nRetry: 3 },
}

const testIO: BootIO = {
  prompt: async () => '',
  write: () => undefined,
}

let tmpDir: string

beforeEach(async () => {
  tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'fcp-cold-start-'))
})

afterEach(async () => {
  await fs.rm(tmpDir, { recursive: true, force: true })
})

describe('boot — cold start (FAP)', () => {
  async function setupMinimalEntity(root: string): Promise<void> {
    await fs.mkdir(path.join(root, 'state'), { recursive: true })
    await fs.mkdir(path.join(root, 'persona'), { recursive: true })
    await fs.writeFile(path.join(root, 'boot.md'), '# Boot Instructions\n')
    await fs.writeFile(path.join(root, 'state', 'baseline.json'), JSON.stringify(MINIMAL_BASELINE, null, 2))
    await fs.writeFile(path.join(root, 'persona', 'identity.md'), '# Identity\n')
  }

  it('runs FAP and creates all required artifacts', async () => {
    await setupMinimalEntity(tmpDir)
    const layout = createLayout(tmpDir)
    const logger = createLogger({ test: true })

    const result = await startEntity({
      layout, logger, io: testIO,
      operatorName: 'Alice', operatorEmail: 'alice@example.com',
    })

    expect(result.ok).toBe(true)
    if (!result.ok) return

    expect(result.sessionId).toMatch(/^[0-9a-f-]{36}$/)

    // All FAP artifacts must exist
    await expect(fs.access(layout.memory.imprint)).resolves.toBeUndefined()
    await expect(fs.access(layout.state.integrity)).resolves.toBeUndefined()
    await expect(fs.access(layout.skills.index)).resolves.toBeUndefined()
    await expect(fs.access(layout.state.integrityChain)).resolves.toBeUndefined()
    await expect(fs.access(layout.state.sentinels.sessionToken)).resolves.toBeUndefined()
  })

  it('writes valid imprint.json with correct operator hash', async () => {
    await setupMinimalEntity(tmpDir)
    const layout = createLayout(tmpDir)
    const logger = createLogger({ test: true })
    const { createHash } = await import('node:crypto')

    await startEntity({ layout, logger, io: testIO, operatorName: 'Bob', operatorEmail: 'bob@example.com' })

    const raw = JSON.parse(await fs.readFile(layout.memory.imprint, 'utf8')) as {
      operatorBound: { operatorHash: string }
    }
    const expectedHash = 'sha256:' + createHash('sha256').update('Bob\nbob@example.com').digest('hex')
    expect(raw.operatorBound.operatorHash).toBe(expectedHash)
  })

  it('writes a genesis entry in integrity-chain.jsonl', async () => {
    await setupMinimalEntity(tmpDir)
    const layout = createLayout(tmpDir)
    const logger = createLogger({ test: true })

    await startEntity({ layout, logger, io: testIO, operatorName: 'Alice', operatorEmail: 'alice@example.com' })

    const lines = (await fs.readFile(layout.state.integrityChain, 'utf8'))
      .split('\n').filter(l => l.trim())
    expect(lines).toHaveLength(1)
    const entry = JSON.parse(lines[0]!) as { type: string; seq: number; prevHash: unknown }
    expect(entry.type).toBe('genesis')
    expect(entry.seq).toBe(0)
    expect(entry.prevHash).toBeNull()
  })

  it('returns error if operator credentials are absent', async () => {
    await setupMinimalEntity(tmpDir)
    const layout = createLayout(tmpDir)
    const logger = createLogger({ test: true })

    const result = await startEntity({ layout, logger, io: testIO })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.reason).toContain('fcp init')
  })

  it('rolls back on failure (missing boot.md)', async () => {
    // Only create baseline — no boot.md
    await fs.mkdir(path.join(tmpDir, 'state'), { recursive: true })
    await fs.writeFile(path.join(tmpDir, 'state', 'baseline.json'), JSON.stringify(MINIMAL_BASELINE))

    const layout = createLayout(tmpDir)
    const logger = createLogger({ test: true })

    const result = await startEntity({
      layout, logger, io: testIO,
      operatorName: 'Alice', operatorEmail: 'alice@example.com',
    })

    expect(result.ok).toBe(false)
    // No partial artifacts should remain
    await expect(fs.access(layout.memory.imprint)).rejects.toThrow()
    await expect(fs.access(layout.state.integrity)).rejects.toThrow()
    await expect(fs.access(layout.skills.index)).rejects.toThrow()
  })
})
