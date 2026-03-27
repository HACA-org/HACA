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
  version: '1.0',
  entity_id: 'test-entity',
  cpe: { topology: 'transparent', backend: 'anthropic:claude-sonnet-4-6' },
  heartbeat: { cycle_threshold: 50, interval_seconds: 60 },
  watchdog: { sil_threshold_seconds: 300 },
  context_window: { budget_tokens: 100000, critical_pct: 90 },
  drift: { comparison_mechanism: 'ncd-gzip-v1', threshold: 0.3 },
  session_store: { rotation_threshold_bytes: 1048576 },
  working_memory: { max_entries: 10 },
  integrity_chain: { checkpoint_interval: 10 },
  pre_session_buffer: { max_entries: 5 },
  operator_channel: { notifications_dir: 'state/operator_notifications' },
  fault: { n_boot: 3, n_channel: 3, n_retry: 3 },
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
      operator_bound: { operator_hash: string }
    }
    const expectedHash = 'sha256:' + createHash('sha256').update('Bob\nbob@example.com').digest('hex')
    expect(raw.operator_bound.operator_hash).toBe(expectedHash)
  })

  it('writes a genesis entry in integrity_chain.jsonl', async () => {
    await setupMinimalEntity(tmpDir)
    const layout = createLayout(tmpDir)
    const logger = createLogger({ test: true })

    await startEntity({ layout, logger, io: testIO, operatorName: 'Alice', operatorEmail: 'alice@example.com' })

    const lines = (await fs.readFile(layout.state.integrityChain, 'utf8'))
      .split('\n').filter(l => l.trim())
    expect(lines).toHaveLength(1)
    const entry = JSON.parse(lines[0]!) as { type: string; seq: number; prev_hash: unknown }
    expect(entry.type).toBe('genesis')
    expect(entry.seq).toBe(0)
    expect(entry.prev_hash).toBeNull()
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
