// Integration test: warm boot detects stale session token (crash recovery).
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
  tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'fcp-crash-recovery-'))
})

afterEach(async () => {
  await fs.rm(tmpDir, { recursive: true, force: true })
})

// Helper: run FAP to set up a fully initialized entity, then return layout.
async function initEntity(root: string) {
  const BASELINE = {
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
  }
  await fs.mkdir(path.join(root, 'state'), { recursive: true })
  await fs.mkdir(path.join(root, 'persona'), { recursive: true })
  await fs.writeFile(path.join(root, 'boot.md'), '# Boot\n')
  await fs.writeFile(path.join(root, 'state', 'baseline.json'), JSON.stringify(BASELINE))
  await fs.writeFile(path.join(root, 'persona', 'id.md'), '# Identity\n')

  const layout = createLayout(root)
  const logger = createLogger({ test: true })
  const r = await startEntity({ layout, logger, io: testIO, operatorName: 'Alice', operatorEmail: 'alice@example.com' })
  if (!r.ok) throw new Error(`FAP failed: ${r.reason}`)
  return { layout, logger }
}

describe('boot — crash recovery', () => {
  it('detects stale token, removes it, and issues a new one', async () => {
    const { layout, logger } = await initEntity(tmpDir)

    // Simulate crash: leave a stale session token from the previous session
    const staleToken = JSON.parse(await fs.readFile(layout.state.sentinels.sessionToken, 'utf8')) as { sessionId: string }
    const staleId = staleToken.sessionId

    const result = await startEntity({ layout, logger, io: testIO })
    expect(result.ok).toBe(true)
    if (!result.ok) return

    // New session ID must differ from the stale one
    expect(result.sessionId).not.toBe(staleId)
    expect(result.sessionId).toMatch(/^[0-9a-f-]{36}$/)

    // Token file must now hold the new session
    const newToken = JSON.parse(await fs.readFile(layout.state.sentinels.sessionToken, 'utf8')) as { sessionId: string }
    expect(newToken.sessionId).toBe(result.sessionId)
  })

  it('calls the injected sleep cycle on crash recovery', async () => {
    const { layout, logger } = await initEntity(tmpDir)

    let sleepCycleCalled = false
    const result = await startEntity({
      layout, logger, io: testIO,
      sleepCycle: async () => { sleepCycleCalled = true },
    })

    expect(result.ok).toBe(true)
    expect(sleepCycleCalled).toBe(true)
  })

  it('succeeds without sleep cycle when not injected', async () => {
    const { layout, logger } = await initEntity(tmpDir)

    const result = await startEntity({ layout, logger, io: testIO })
    expect(result.ok).toBe(true)
  })
})
