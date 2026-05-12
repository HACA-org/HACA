// Integration test: Phase 6 (vital-status) — distress beacon, proposals gate, drift probes.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import * as os   from 'node:os'
import * as fs   from 'node:fs/promises'
import * as path from 'node:path'
import { createLayout } from '../../src/types/store.js'
import { startEntity }  from '../../src/boot/boot.js'
import { createLogger } from '../../src/logger/logger.js'
import type { BootIO }  from '../../src/types/boot.js'

// Mock the proposal gate module — the interactive select requires a real TTY.
// Individual tests configure the mock's behaviour via mockResolvedValue / mockRejectedValue.
vi.mock('../../src/boot/proposal-gate.js', () => ({
  runProposalGate: vi.fn().mockResolvedValue(undefined),
}))

// ─── Helpers ──────────────────────────────────────────────────────────────────

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

function makeFapIO(name = 'Alice', email = 'alice@test.com'): BootIO {
  const answers = [name, email]
  let idx = 0
  return { prompt: async () => answers[idx++] ?? '', write: () => undefined }
}
const warmIO: BootIO = { prompt: async () => '', write: () => undefined }

async function initEntity(root: string) {
  await fs.mkdir(path.join(root, 'state'),   { recursive: true })
  await fs.mkdir(path.join(root, 'persona'), { recursive: true })
  await fs.writeFile(path.join(root, 'boot.md'), '# Boot\n')
  await fs.writeFile(path.join(root, 'state', 'baseline.json'), JSON.stringify(BASELINE))
  await fs.writeFile(path.join(root, 'persona', 'id.md'), '# Identity\n')

  const layout = createLayout(root)
  const logger = createLogger({ test: true })
  const r = await startEntity({ layout, logger, io: makeFapIO() })
  if (!r.ok) throw new Error(`FAP failed: ${r.reason}`)

  // Remove session token so the next boot is a clean warm boot
  await fs.unlink(layout.state.sentinels.sessionToken)
  return { layout, logger }
}

let tmpDir: string

beforeEach(async () => {
  tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'fcp-phase6-'))
  vi.restoreAllMocks()
  // Default: gate resolves (operator reviews proposals without aborting)
  const mod = await import('../../src/boot/proposal-gate.js')
  vi.mocked(mod.runProposalGate).mockResolvedValue(undefined)
})

afterEach(async () => {
  await fs.rm(tmpDir, { recursive: true, force: true })
})

// ─── Distress beacon ──────────────────────────────────────────────────────────

describe('phase6 — distress beacon', () => {
  it('fails boot when distress.beacon is present', async () => {
    const { layout, logger } = await initEntity(tmpDir)
    await fs.writeFile(layout.state.distressBeacon, '')

    const result = await startEntity({ layout, logger, io: warmIO })
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.phase).toBe(6)
      expect(result.reason).toMatch(/distress beacon/i)
    }
  })

  it('boots normally when distress.beacon is absent', async () => {
    const { layout, logger } = await initEntity(tmpDir)
    const result = await startEntity({ layout, logger, io: warmIO })
    expect(result.ok).toBe(true)
  })
})

// ─── Pending proposals ────────────────────────────────────────────────────────

describe('phase6 — pending proposals', () => {
  it('fails boot when unapproved proposals exist and gate throws (operator aborts)', async () => {
    const { layout, logger } = await initEntity(tmpDir)

    await fs.writeFile(layout.state.pendingProposals, JSON.stringify({
      proposals: [{
        id:          'proposal-1',
        description: 'Add logging skill',
        ops:         [{ type: 'fileWrite', path: 'skills/logger/manifest.json', content: '{}' }],
        digest:      'sha256:abc123',
        queuedAt:    new Date().toISOString(),
      }],
    }))

    // Simulate operator aborting mid-gate (Ctrl-C)
    const mod = await import('../../src/boot/proposal-gate.js')
    vi.mocked(mod.runProposalGate).mockRejectedValue(new Error('User cancelled selection'))

    const result = await startEntity({ layout, logger, io: warmIO })
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.phase).toBe(6)
      expect(result.reason).toMatch(/proposals must be reviewed/i)
    }
  })

  it('boots normally when all proposals are already approved', async () => {
    const { layout, logger } = await initEntity(tmpDir)

    await fs.writeFile(layout.state.pendingProposals, JSON.stringify({
      proposals: [{
        id:          'proposal-1',
        description: 'Add logging skill',
        ops:         [{ type: 'fileWrite', path: 'skills/logger/manifest.json', content: '{}' }],
        digest:      'sha256:abc123',
        queuedAt:    new Date().toISOString(),
        approvedAt:  new Date().toISOString(),
      }],
    }))

    const result = await startEntity({ layout, logger, io: warmIO })
    expect(result.ok).toBe(true)
  })

  it('boots normally when pending-proposals.json does not exist', async () => {
    const { layout, logger } = await initEntity(tmpDir)
    const result = await startEntity({ layout, logger, io: warmIO })
    expect(result.ok).toBe(true)
  })

  it('calls runProposalGate when unapproved proposals exist', async () => {
    const { layout, logger } = await initEntity(tmpDir)

    await fs.writeFile(layout.state.pendingProposals, JSON.stringify({
      proposals: [{
        id:          'proposal-2',
        description: 'Update persona',
        ops:         [{ type: 'fileWrite', path: 'persona/values.md', content: '# Values\n' }],
        digest:      'sha256:def456',
        queuedAt:    new Date().toISOString(),
      }],
    }))

    const mod = await import('../../src/boot/proposal-gate.js')
    // Gate resolves (operator approved) — boot should succeed
    vi.mocked(mod.runProposalGate).mockResolvedValue(undefined)

    const result = await startEntity({ layout, logger, io: warmIO })
    expect(result.ok).toBe(true)
    expect(vi.mocked(mod.runProposalGate)).toHaveBeenCalledOnce()
  })
})

// ─── Drift probes ─────────────────────────────────────────────────────────────

describe('phase6 — drift probes', () => {
  it('fails boot when a deterministic probe exceeds threshold', async () => {
    const { layout, logger } = await initEntity(tmpDir)

    // Probe targets memory/imprint.json (must start with 'memory/' per DriftProbeSchema).
    // imprint.json is always created by FAP. The probe checks for a string not present in it.
    const probe = {
      id:            'probe-identity',
      description:   'imprint must contain required marker',
      target:        'memory/imprint.json',
      deterministic: { type: 'string', value: 'REQUIRED_MARKER_NOT_PRESENT' },
      reference:     null,
    }
    await fs.writeFile(layout.state.driftProbes, JSON.stringify(probe) + '\n')

    const result = await startEntity({ layout, logger, io: warmIO })
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.phase).toBe(6)
      expect(result.reason).toMatch(/drift detected/i)
      expect(result.reason).toContain('probe-identity')
    }
  })

  it('boots normally when all probes pass', async () => {
    const { layout, logger } = await initEntity(tmpDir)

    // Probe checks for '"activatedAt"' which IS in imprint.json (FAP always writes it)
    const probe = {
      id:            'probe-imprint-field',
      description:   'imprint.json must contain activatedAt field',
      target:        'memory/imprint.json',
      deterministic: { type: 'string', value: '"activatedAt"' },
      reference:     null,
    }
    await fs.writeFile(layout.state.driftProbes, JSON.stringify(probe) + '\n')

    const result = await startEntity({ layout, logger, io: warmIO })
    expect(result.ok).toBe(true)
  })

  it('boots normally when drift-probes.jsonl does not exist', async () => {
    const { layout, logger } = await initEntity(tmpDir)
    const result = await startEntity({ layout, logger, io: warmIO })
    expect(result.ok).toBe(true)
  })
})
