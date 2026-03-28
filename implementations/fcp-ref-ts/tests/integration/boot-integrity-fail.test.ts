// Integration test: Phase 3 (integrity check) rejects a tampered file.
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import * as os from 'node:os'
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { createLayout } from '../../src/types/store.js'
import { startEntity } from '../../src/boot/boot.js'
import { createLogger } from '../../src/logger/logger.js'
import type { BootIO } from '../../src/types/boot.js'

function makeFapIO(name = 'Alice', email = 'alice@example.com'): BootIO {
  const answers = [name, email]
  let idx = 0
  return { prompt: async () => answers[idx++] ?? '', write: () => undefined }
}
const warmIO: BootIO = { prompt: async () => '', write: () => undefined }

let tmpDir: string

beforeEach(async () => {
  tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'fcp-integrity-fail-'))
})

afterEach(async () => {
  await fs.rm(tmpDir, { recursive: true, force: true })
})

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
  const r = await startEntity({ layout, logger, io: makeFapIO() })
  if (!r.ok) throw new Error(`FAP failed: ${r.reason}`)

  // Remove the stale session token so the next boot is a clean warm boot (not crash recovery).
  await fs.unlink(layout.state.sentinels.sessionToken)
  return { layout, logger }
}

describe('boot — integrity failure', () => {
  it('fails Phase 3 when boot.md is modified after FAP', async () => {
    const { layout, logger } = await initEntity(tmpDir)

    // Tamper with a tracked file
    await fs.writeFile(layout.bootMd, '# Tampered!\n')

    const result = await startEntity({ layout, logger, io: warmIO })
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.phase).toBe(3)
      expect(result.reason).toMatch(/drift|tamper|modified/i)
    }
  })

  it('fails Phase 3 when a persona file is modified after FAP', async () => {
    const { layout, logger } = await initEntity(tmpDir)

    await fs.writeFile(path.join(layout.persona, 'id.md'), '# Modified identity\n')

    const result = await startEntity({ layout, logger, io: warmIO })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.phase).toBe(3)
  })

  it('passes integrity check when no files are modified', async () => {
    const { layout, logger } = await initEntity(tmpDir)

    const result = await startEntity({ layout, logger, io: warmIO })
    expect(result.ok).toBe(true)
  })

  it('fails Phase 3 when integrity.json is missing', async () => {
    const { layout, logger } = await initEntity(tmpDir)

    await fs.unlink(layout.state.integrity)

    const result = await startEntity({ layout, logger, io: warmIO })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.phase).toBe(3)
  })

  it('fails Phase 3 when a tracked file is deleted after FAP', async () => {
    const { layout, logger } = await initEntity(tmpDir)

    // Delete a tracked file — absence is drift
    await fs.unlink(layout.bootMd)

    const result = await startEntity({ layout, logger, io: warmIO })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.phase).toBe(3)
  })

  it('fails Phase 1 when HACA-Core imprint has opaque topology in baseline', async () => {
    const { layout, logger } = await initEntity(tmpDir)

    // Patch baseline to opaque topology
    const raw = JSON.parse(await fs.readFile(layout.state.baseline, 'utf8')) as Record<string, unknown>
    raw['cpe'] = { topology: 'opaque', backend: 'anthropic:claude-sonnet-4-6' }
    const baselineStr = JSON.stringify(raw)
    await fs.writeFile(layout.state.baseline, baselineStr)

    // Update integrity.json so Phase 3 passes
    const { createHash } = await import('node:crypto')
    const intRaw = JSON.parse(await fs.readFile(layout.state.integrity, 'utf8')) as { files: Record<string, string> }
    intRaw.files['state/baseline.json'] = createHash('sha256').update(baselineStr).digest('hex')
    await fs.writeFile(layout.state.integrity, JSON.stringify(intRaw))

    const result = await startEntity({ layout, logger, io: warmIO })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.phase).toBe(1)
  })
})
