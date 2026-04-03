// Unit tests for fcp doctor checks.
// We test the check functions directly by scaffolding a minimal entity filesystem.
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import * as os from 'node:os'
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { createLayout } from '../../src/types/store.js'
import { hashTrackedFiles, getTrackedFiles, sha256Digest } from '../../src/boot/integrity.js'
import { verifyIntegrityDoc, refreshIntegrityDoc } from '../../src/sil/integrity.js'

let tmpDir: string

const BASELINE = {
  version: '1.0', entityId: 'test-doctor',
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

async function scaffold(root: string) {
  const layout = createLayout(root)
  await fs.mkdir(path.join(root, 'state', 'sentinels'), { recursive: true })
  await fs.mkdir(path.join(root, 'state', 'operator-notifications'), { recursive: true })
  await fs.mkdir(path.join(root, 'memory'), { recursive: true })
  await fs.mkdir(path.join(root, 'persona'), { recursive: true })
  await fs.mkdir(path.join(root, 'skills'), { recursive: true })
  await fs.mkdir(path.join(root, 'hooks'), { recursive: true })
  await fs.mkdir(path.join(root, 'io', 'inbox', 'presession'), { recursive: true })
  await fs.mkdir(path.join(root, 'io', 'spool'), { recursive: true })

  await fs.writeFile(path.join(root, 'boot.md'), '# Boot\n')
  await fs.writeFile(layout.state.baseline, JSON.stringify(BASELINE))
  await fs.writeFile(path.join(root, 'persona', 'identity.md'), '# Identity\n')
  await fs.writeFile(path.join(root, 'persona', 'values.md'), '# Values\n')
  await fs.writeFile(path.join(root, 'persona', 'constraints.md'), '# Constraints\n')
  await fs.writeFile(path.join(root, 'persona', 'protocol.md'), '# Protocol\n')
  await fs.writeFile(layout.skills.index, JSON.stringify({ version: '1.0', skills: [], aliases: {} }))

  // Generate integrity.json from current tracked files.
  const tracked = await getTrackedFiles(layout)
  const files   = await hashTrackedFiles(layout, tracked)
  await fs.writeFile(layout.state.integrity, JSON.stringify({
    version: '1.0', algorithm: 'sha256', lastCheckpoint: null, files,
  }))

  return layout
}

beforeEach(async () => {
  tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'fcp-doctor-'))
})

afterEach(async () => {
  await fs.rm(tmpDir, { recursive: true, force: true })
})

describe('verifyIntegrityDoc', () => {
  it('returns clean when all hashes match', async () => {
    const layout = await scaffold(tmpDir)
    const result = await verifyIntegrityDoc(layout)
    expect(result.clean).toBe(true)
    expect(result.mismatches).toHaveLength(0)
  })

  it('detects hash_mismatch when a tracked file is modified', async () => {
    const layout = await scaffold(tmpDir)
    await fs.writeFile(layout.bootMd, '# TAMPERED\n')

    const result = await verifyIntegrityDoc(layout)
    expect(result.clean).toBe(false)
    const mm = result.mismatches.find(m => m.file === 'boot.md')
    expect(mm).toBeDefined()
    expect(mm!.reason).toBe('hash_mismatch')
  })

  it('detects missing file', async () => {
    const layout = await scaffold(tmpDir)
    await fs.unlink(path.join(tmpDir, 'persona', 'identity.md'))

    const result = await verifyIntegrityDoc(layout)
    expect(result.clean).toBe(false)
    const mm = result.mismatches.find(m => m.file === 'persona/identity.md')
    expect(mm).toBeDefined()
    expect(mm!.reason).toBe('missing')
  })

  it('detects untracked file (new file on disk not in integrity.json)', async () => {
    const layout = await scaffold(tmpDir)
    // Add a new persona file that wasn't there when integrity.json was written.
    await fs.writeFile(path.join(tmpDir, 'persona', 'extra.md'), '# Extra\n')

    const result = await verifyIntegrityDoc(layout)
    expect(result.clean).toBe(false)
    const mm = result.mismatches.find(m => m.file === 'persona/extra.md')
    expect(mm).toBeDefined()
    expect(mm!.reason).toBe('untracked')
  })
})

describe('refreshIntegrityDoc', () => {
  it('fixes drifted hashes', async () => {
    const layout = await scaffold(tmpDir)
    await fs.writeFile(layout.bootMd, '# Modified\n')

    // Verify drift exists.
    let result = await verifyIntegrityDoc(layout)
    expect(result.clean).toBe(false)

    // Fix.
    await refreshIntegrityDoc(layout)

    // Verify clean after fix.
    result = await verifyIntegrityDoc(layout)
    expect(result.clean).toBe(true)
  })

  it('includes newly tracked files after refresh', async () => {
    const layout = await scaffold(tmpDir)
    await fs.writeFile(path.join(tmpDir, 'persona', 'extra.md'), '# Extra\n')

    await refreshIntegrityDoc(layout)

    const result = await verifyIntegrityDoc(layout)
    expect(result.clean).toBe(true)
  })
})
