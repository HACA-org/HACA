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
    const staleToken = JSON.parse(await fs.readFile(layout.state.sentinels.sessionToken, 'utf8')) as { session_id: string }
    const staleId = staleToken.session_id

    const result = await startEntity({ layout, logger, io: testIO })
    expect(result.ok).toBe(true)
    if (!result.ok) return

    // New session ID must differ from the stale one
    expect(result.sessionId).not.toBe(staleId)
    expect(result.sessionId).toMatch(/^[0-9a-f-]{36}$/)

    // Token file must now hold the new session
    const newToken = JSON.parse(await fs.readFile(layout.state.sentinels.sessionToken, 'utf8')) as { session_id: string }
    expect(newToken.session_id).toBe(result.sessionId)
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
