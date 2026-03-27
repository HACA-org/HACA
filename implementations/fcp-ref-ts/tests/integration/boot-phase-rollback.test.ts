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
      version: '1.0', entity_id: 'test',
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
