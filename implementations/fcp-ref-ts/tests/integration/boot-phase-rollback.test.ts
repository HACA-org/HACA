// Integration test: FAP rollback — partial artifacts are cleaned up on failure.
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import * as os from 'node:os'
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { createLayout } from '../../src/types/store.js'
import { startEntity } from '../../src/boot/boot.js'
import { createLogger } from '../../src/logger/logger.js'
import type { BootIO } from '../../src/types/boot.js'

const testIO: BootIO = { prompt: async () => '', write: () => undefined }

let tmpDir: string

beforeEach(async () => {
  tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'fcp-rollback-'))
})

afterEach(async () => {
  await fs.rm(tmpDir, { recursive: true, force: true })
})

describe('boot — FAP rollback', () => {
  it('leaves no artifacts when boot.md is missing', async () => {
    // Set up baseline but omit boot.md — FAP Step 1 fails immediately
    await fs.mkdir(path.join(tmpDir, 'state'), { recursive: true })
    await fs.mkdir(path.join(tmpDir, 'persona'), { recursive: true })
    await fs.writeFile(path.join(tmpDir, 'state', 'baseline.json'), JSON.stringify({
      version: '1.0', entityId: 'test',
      cpe: { topology: 'transparent', backend: 'anthropic:claude-sonnet-4-6' },
      heartbeat:        { cycleThreshold: 50, intervalSeconds: 60 },
      watchdog:         { silThresholdSeconds: 300 },
      contextWindow:    { fallbackTokens: 100000, criticalPct: 90, warnPct: 70 },
      drift:            { comparisonMechanism: 'ncd-gzip-v1', threshold: 0.3 },
      sessionStore:     { rotationThresholdBytes: 1048576 },
      workingMemory:    { maxEntries: 10 },
      integrityChain:   { checkpointInterval: 10 },
      preSessionBuffer: { maxEntries: 5 },
      operatorChannel:  { notificationsDir: 'state/operator-notifications' },
      fault:            { nBoot: 3, nChannel: 3, nRetry: 3 },
    }))

    const layout = createLayout(tmpDir)
    const logger = createLogger({ test: true })

    const result = await startEntity({
      layout, logger, io: testIO,
      operatorName: 'Alice', operatorEmail: 'alice@example.com',
    })

    expect(result.ok).toBe(false)

    // Nothing should have been written
    await expect(fs.access(layout.memory.imprint)).rejects.toThrow()
    await expect(fs.access(layout.state.integrity)).rejects.toThrow()
    await expect(fs.access(layout.skills.index)).rejects.toThrow()
    await expect(fs.access(layout.state.sentinels.sessionToken)).rejects.toThrow()
    await expect(fs.access(layout.state.integrityChain)).rejects.toThrow()
  })

  it('leaves no artifacts when baseline.json is missing', async () => {
    // Only create boot.md, no baseline — FAP Step 1 fails at baseline parse
    await fs.writeFile(path.join(tmpDir, 'boot.md'), '# Boot\n')
    await fs.mkdir(path.join(tmpDir, 'persona'), { recursive: true })

    const layout = createLayout(tmpDir)
    const logger = createLogger({ test: true })

    const result = await startEntity({
      layout, logger, io: testIO,
      operatorName: 'Alice', operatorEmail: 'alice@example.com',
    })

    expect(result.ok).toBe(false)
    await expect(fs.access(layout.memory.imprint)).rejects.toThrow()
    await expect(fs.access(layout.state.integrity)).rejects.toThrow()
  })

  it('leaves no artifacts when baseline.json has invalid schema', async () => {
    await fs.mkdir(path.join(tmpDir, 'state'), { recursive: true })
    await fs.mkdir(path.join(tmpDir, 'persona'), { recursive: true })
    await fs.writeFile(path.join(tmpDir, 'boot.md'), '# Boot\n')
    // Intentionally invalid baseline
    await fs.writeFile(path.join(tmpDir, 'state', 'baseline.json'), '{"version":"2.0"}')

    const layout = createLayout(tmpDir)
    const logger = createLogger({ test: true })

    const result = await startEntity({
      layout, logger, io: testIO,
      operatorName: 'Alice', operatorEmail: 'alice@example.com',
    })

    expect(result.ok).toBe(false)
    await expect(fs.access(layout.memory.imprint)).rejects.toThrow()
    await expect(fs.access(layout.state.integrity)).rejects.toThrow()
  })
})
