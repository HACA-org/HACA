import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mkdtemp, rm, mkdir, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createLayout } from '../store/layout.js'
import { writeJson, touchFile } from '../store/io.js'
import { createLogger } from '../logger/logger.js'
import {
  computeHashes, verifyDrift, writeIntegrityDoc, sha256File, verifyChainFromImprint,
} from './integrity.js'
import {
  logHeartbeat, logEndureCommit, readChain, lastChainSeq,
} from './chain.js'
import {
  createVitalCheckState, tick, shouldRun, runVitalChecks,
} from './heartbeat.js'
import {
  runEndureProtocol, readPendingProposals, writePendingProposals,
} from './endure.js'
import type { Layout } from '../store/layout.js'
import type { PendingProposal } from './types.js'

async function makeFixture(tmp: string): Promise<Layout> {
  const root = join(tmp, 'entity')
  const layout = createLayout(root)
  await mkdir(join(root, 'state'), { recursive: true })
  await mkdir(join(root, 'memory'), { recursive: true })
  await mkdir(join(root, 'persona'), { recursive: true })
  await mkdir(join(root, 'skills'), { recursive: true })
  await mkdir(join(root, 'io', 'inbox', 'presession'), { recursive: true })
  await mkdir(join(root, 'io', 'notifications'), { recursive: true })
  await writeFile(join(root, 'BOOT.md'), '# Boot\nBe helpful.', 'utf8')
  await writeJson(layout.baseline, { cpe: { topology: 'transparent' }, haca_profile: 'haca-core' })
  await writeJson(layout.skillsIndex, { version: '1.0', skills: [] })
  return layout
}

// ---------------------------------------------------------------------------
// Integrity
// ---------------------------------------------------------------------------
describe('integrity', () => {
  let tmp: string
  let layout: Layout

  beforeEach(async () => {
    tmp = await mkdtemp(join(tmpdir(), 'fcp-sil-integrity-'))
    layout = await makeFixture(tmp)
  })
  afterEach(async () => { await rm(tmp, { recursive: true, force: true }) })

  it('computeHashes returns hashes for tracked files', async () => {
    const hashes = await computeHashes(layout)
    expect(Object.keys(hashes)).toContain('BOOT.md')
    expect(Object.keys(hashes)).toContain('state/baseline.json')
  })

  it('writeIntegrityDoc creates integrity.json', async () => {
    await writeIntegrityDoc(layout)
    expect(existsSync(layout.integrity)).toBe(true)
  })

  it('verifyDrift returns empty when no drift', async () => {
    await writeIntegrityDoc(layout)
    const drifts = await verifyDrift(layout)
    expect(drifts).toHaveLength(0)
  })

  it('verifyDrift detects modified file', async () => {
    await writeIntegrityDoc(layout)
    await writeFile(join(layout.root, 'BOOT.md'), '# Modified', 'utf8')
    const drifts = await verifyDrift(layout)
    expect(drifts.some(d => d.includes('BOOT.md'))).toBe(true)
  })

  it('verifyDrift detects missing file', async () => {
    await writeIntegrityDoc(layout)
    await rm(join(layout.root, 'BOOT.md'))
    const drifts = await verifyDrift(layout)
    expect(drifts.some(d => d.includes('missing'))).toBe(true)
  })

  it('sha256File produces deterministic hash', () => {
    const h1 = sha256File('hello world')
    const h2 = sha256File('hello world')
    expect(h1).toBe(h2)
    expect(h1).toMatch(/^sha256:/)
  })
})

// ---------------------------------------------------------------------------
// Chain
// ---------------------------------------------------------------------------
describe('chain', () => {
  let tmp: string
  let layout: Layout

  beforeEach(async () => {
    tmp = await mkdtemp(join(tmpdir(), 'fcp-sil-chain-'))
    layout = await makeFixture(tmp)
  })
  afterEach(async () => { await rm(tmp, { recursive: true, force: true }) })

  it('logHeartbeat appends entry with seq 1', async () => {
    await logHeartbeat(layout, 'session-1')
    const chain = await readChain(layout)
    expect(chain).toHaveLength(1)
    expect(chain[0]!.type).toBe('HEARTBEAT')
    expect(chain[0]!.seq).toBe(1)
  })

  it('chain entries increment seq', async () => {
    await logHeartbeat(layout, 's1')
    await logHeartbeat(layout, 's2')
    const chain = await readChain(layout)
    expect(chain[0]!.seq).toBe(1)
    expect(chain[1]!.seq).toBe(2)
  })

  it('each entry has prevHash of previous entry', async () => {
    await logHeartbeat(layout, 's1')
    await logHeartbeat(layout, 's2')
    const chain = await readChain(layout)
    expect(chain[0]!.prevHash).toBeNull()
    expect(chain[1]!.prevHash).not.toBeNull()
  })

  it('logEndureCommit records operation and evolutionAuthDigest', async () => {
    await logEndureCommit(layout, 'installSkill', 'prop-1', 'sha256:abc123')
    const chain = await readChain(layout)
    expect(chain[0]!.type).toBe('ENDURE_COMMIT')
    expect(chain[0]!.data['operation']).toBe('installSkill')
    expect(chain[0]!.data['evolutionAuthDigest']).toBe('sha256:abc123')
  })

  it('lastChainSeq returns 0 when empty', async () => {
    const seq = await lastChainSeq(layout)
    expect(seq).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// Heartbeat
// ---------------------------------------------------------------------------
describe('heartbeat', () => {
  let tmp: string
  let layout: Layout

  beforeEach(async () => {
    tmp = await mkdtemp(join(tmpdir(), 'fcp-sil-hb-'))
    layout = await makeFixture(tmp)
  })
  afterEach(async () => { await rm(tmp, { recursive: true, force: true }) })

  it('tick increments cyclesSinceCheck', () => {
    const state = createVitalCheckState('s1')
    tick(state)
    tick(state)
    expect(state.cyclesSinceCheck).toBe(2)
  })

  it('shouldRun triggers on cycle threshold', () => {
    const state = createVitalCheckState('s1')
    for (let i = 0; i < 10; i++) tick(state)
    expect(shouldRun(state, { cycleThreshold: 10, intervalSeconds: 300 })).toBe(true)
  })

  it('shouldRun does not trigger before threshold', () => {
    const state = createVitalCheckState('s1')
    for (let i = 0; i < 5; i++) tick(state)
    expect(shouldRun(state, { cycleThreshold: 10, intervalSeconds: 300 })).toBe(false)
  })

  it('runVitalChecks returns no criticals on clean state', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    await writeIntegrityDoc(layout)
    const state = createVitalCheckState('s1')
    const criticals = await runVitalChecks(layout, state, logger, {
      tokensUsed: 1000,
      contextWindow: 100000,
      compactPct: 0.95,
      workspaceFocus: join(tmp, 'workspace'),
      profile: 'haca-core',
    })
    expect(criticals).toHaveLength(0)
  })

  it('runVitalChecks detects identity drift', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    await writeIntegrityDoc(layout)
    // Modify a tracked file after writing integrity doc
    await writeFile(join(layout.root, 'BOOT.md'), '# Tampered', 'utf8')
    const state = createVitalCheckState('s1')
    const criticals = await runVitalChecks(layout, state, logger, {
      tokensUsed: 1000,
      contextWindow: 100000,
      compactPct: 0.95,
      workspaceFocus: join(tmp, 'workspace'),
      profile: 'haca-core',
    })
    expect(criticals.some(c => c === 'identity_drift')).toBe(true)
  })

  it('activates distress beacon on drift in haca-core', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    await writeIntegrityDoc(layout)
    await writeFile(join(layout.root, 'BOOT.md'), '# Tampered', 'utf8')
    const state = createVitalCheckState('s1')
    await runVitalChecks(layout, state, logger, {
      tokensUsed: 1000,
      contextWindow: 100000,
      compactPct: 0.95,
      workspaceFocus: join(tmp, 'workspace'),
      profile: 'haca-core',
    })
    expect(existsSync(layout.distressBeacon)).toBe(true)
  })

  it('does not activate distress beacon on drift in haca-evolve', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    await writeIntegrityDoc(layout)
    await writeFile(join(layout.root, 'BOOT.md'), '# Changed', 'utf8')
    const state = createVitalCheckState('s1')
    await runVitalChecks(layout, state, logger, {
      tokensUsed: 1000,
      contextWindow: 100000,
      compactPct: 0.95,
      workspaceFocus: join(tmp, 'workspace'),
      profile: 'haca-evolve',
    })
    expect(existsSync(layout.distressBeacon)).toBe(false)
  })

  it('resets counters after running', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    await writeIntegrityDoc(layout)
    const state = createVitalCheckState('s1')
    for (let i = 0; i < 5; i++) tick(state)
    await runVitalChecks(layout, state, logger, {
      tokensUsed: 0, contextWindow: 100000, compactPct: 0.95,
      workspaceFocus: null, profile: 'haca-core',
    })
    expect(state.cyclesSinceCheck).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// Endure
// ---------------------------------------------------------------------------
describe('endure', () => {
  let tmp: string
  let layout: Layout

  beforeEach(async () => {
    tmp = await mkdtemp(join(tmpdir(), 'fcp-sil-endure-'))
    layout = await makeFixture(tmp)
    await writeIntegrityDoc(layout)
  })
  afterEach(async () => { await rm(tmp, { recursive: true, force: true }) })

  it('runEndureProtocol does nothing when no proposals', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    await expect(runEndureProtocol(layout, logger, 'haca-core')).resolves.not.toThrow()
  })

  it('installs approved skill proposal', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))

    // Create a valid staged skill
    const stageDir = join(tmp, 'workspace', '.tmp', 'test-skill')
    await mkdir(stageDir, { recursive: true })
    await writeJson(join(stageDir, 'manifest.json'), {
      name: 'test-skill', description: 'A test skill', execute: 'text', entry: 'SKILL.md',
    })
    await writeFile(join(stageDir, 'SKILL.md'), '# Test Skill\nDo things.', 'utf8')

    const proposal: PendingProposal = {
      id: 'prop-1',
      operation: 'installSkill',
      stagePath: stageDir,
      description: 'Install test-skill',
      createdAt: new Date().toISOString(),
      profile: 'haca-core',
      approvedAt: new Date().toISOString(),
    }
    await writePendingProposals(layout, [proposal])

    await runEndureProtocol(layout, logger, 'haca-core')

    expect(existsSync(layout.skill('test-skill'))).toBe(true)
    expect(existsSync(stageDir)).toBe(false) // cleaned up
  })

  it('appends ENDURE_COMMIT to chain after install', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))

    const stageDir = join(tmp, 'workspace', '.tmp', 'chain-skill')
    await mkdir(stageDir, { recursive: true })
    await writeJson(join(stageDir, 'manifest.json'), {
      name: 'chain-skill', description: 'Chain test', execute: 'text', entry: 'SKILL.md',
    })
    await writeFile(join(stageDir, 'SKILL.md'), '# Chain Skill', 'utf8')

    const proposal: PendingProposal = {
      id: 'prop-2',
      operation: 'installSkill',
      stagePath: stageDir,
      description: 'Install chain-skill',
      createdAt: new Date().toISOString(),
      profile: 'haca-core',
      approvedAt: new Date().toISOString(),
    }
    await writePendingProposals(layout, [proposal])
    await runEndureProtocol(layout, logger, 'haca-core')

    const chain = await readChain(layout)
    expect(chain.some(e => e.type === 'ENDURE_COMMIT')).toBe(true)
  })

  it('keeps unapproved proposals pending', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))

    const proposal: PendingProposal = {
      id: 'prop-3',
      operation: 'installSkill',
      stagePath: '/nonexistent',
      description: 'Pending proposal',
      createdAt: new Date().toISOString(),
      profile: 'haca-core',
      // no approvedAt
    }
    await writePendingProposals(layout, [proposal])
    await runEndureProtocol(layout, logger, 'haca-core')

    const remaining = await readPendingProposals(layout)
    expect(remaining.some(p => p.id === 'prop-3')).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// Chain verification from imprint
// ---------------------------------------------------------------------------
describe('verifyChainFromImprint', () => {
  let tmp: string
  let layout: Layout

  beforeEach(async () => {
    tmp = await mkdtemp(join(tmpdir(), 'fcp-sil-chain-verify-'))
    layout = await makeFixture(tmp)
  })
  afterEach(async () => { await rm(tmp, { recursive: true, force: true }) })

  it('valid when no chain exists but imprint is present', async () => {
    await writeJson(layout.imprint, {
      version: '1.0', activatedAt: new Date().toISOString(),
      hacaProfile: 'haca-core',
      operatorBound: { name: 'Test', email: 'test@test.com', hash: 'abc' },
      structuralBaseline: 'sha256:aaa', integrityDocument: 'sha256:bbb', skillsIndex: 'sha256:ccc',
      genesisOmega: 'sha256:genesis',
    })
    const result = await verifyChainFromImprint(layout)
    expect(result.valid).toBe(true)
  })

  it('invalid when imprint missing', async () => {
    const result = await verifyChainFromImprint(layout)
    expect(result.valid).toBe(false)
    expect(result.reason).toContain('imprint.json')
  })

  it('valid chain: GENESIS → HEARTBEAT → ENDURE_COMMIT', async () => {
    const genesisOmega = 'sha256:genesis123'
    await writeJson(layout.imprint, {
      version: '1.0', activatedAt: new Date().toISOString(),
      hacaProfile: 'haca-core',
      operatorBound: { name: 'Test', email: 'test@test.com', hash: 'abc' },
      structuralBaseline: 'sha256:aaa', integrityDocument: 'sha256:bbb', skillsIndex: 'sha256:ccc',
      genesisOmega,
    })

    const { logGenesis, logHeartbeat: lhb, logEndureCommit: lec } = await import('./chain.js')
    await logGenesis(layout, genesisOmega)
    await lhb(layout, 'session-1')
    await lec(layout, 'installSkill', 'prop-1', 'sha256:authdigest')

    const result = await verifyChainFromImprint(layout)
    expect(result.valid).toBe(true)
  })

  it('invalid when GENESIS imprintHash does not match genesisOmega', async () => {
    await writeJson(layout.imprint, {
      version: '1.0', activatedAt: new Date().toISOString(),
      hacaProfile: 'haca-core',
      operatorBound: { name: 'Test', email: 'test@test.com', hash: 'abc' },
      structuralBaseline: 'sha256:aaa', integrityDocument: 'sha256:bbb', skillsIndex: 'sha256:ccc',
      genesisOmega: 'sha256:correct',
    })

    const { logGenesis } = await import('./chain.js')
    await logGenesis(layout, 'sha256:WRONG')

    const result = await verifyChainFromImprint(layout)
    expect(result.valid).toBe(false)
    expect(result.reason).toContain('genesisOmega')
  })

  it('invalid when ENDURE_COMMIT missing evolutionAuthDigest', async () => {
    const genesisOmega = 'sha256:genesis-for-endure'
    await writeJson(layout.imprint, {
      version: '1.0', activatedAt: new Date().toISOString(),
      hacaProfile: 'haca-evolve',
      operatorBound: { name: 'Test', email: 'test@test.com', hash: 'abc' },
      structuralBaseline: 'sha256:aaa', integrityDocument: 'sha256:bbb', skillsIndex: 'sha256:ccc',
      genesisOmega,
    })

    const { appendJsonl } = await import('../store/io.js')
    const { sha256Str } = await import('./integrity.js')

    // Write GENESIS manually
    const genesis = { seq: 1, type: 'GENESIS', ts: new Date().toISOString(), prevHash: null, data: { imprintHash: genesisOmega } }
    await appendJsonl(layout.integrityChain, genesis)

    // Write ENDURE_COMMIT without evolutionAuthDigest
    const endure = { seq: 2, type: 'ENDURE_COMMIT', ts: new Date().toISOString(), prevHash: sha256Str(JSON.stringify(genesis)), data: { operation: 'installSkill', proposalId: 'p1' } }
    await appendJsonl(layout.integrityChain, endure)

    const result = await verifyChainFromImprint(layout)
    expect(result.valid).toBe(false)
    expect(result.reason).toContain('evolutionAuthDigest')
  })
})
