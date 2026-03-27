// SIL unit tests — chain, integrity, heartbeat checks, endure, drift.
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import * as os from 'node:os'
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { createLayout } from '../types/store.js'
import { createLogger }  from '../logger/logger.js'
import type { Baseline } from '../types/formats/baseline.js'
import { readChain, appendEndureCommit, appendModelChange } from './chain.js'
import { verifyIntegrityDoc, verifyChainFromImprint, refreshIntegrityDoc } from './integrity.js'
import { budgetCheck }   from './checks/budget.js'
import { focusCheck }    from './checks/focus.js'
import { inboxCheck }    from './checks/inbox.js'
import { identityCheck } from './checks/identity.js'
import { createHeartbeat } from './heartbeat.js'
import { approveProposal, runEndureProtocol } from './endure.js'
import { evolutionProposalHandler } from './tools/evolution-proposal.js'
import { sessionCloseHandler, SESSION_CLOSE_SIGNAL } from './tools/session-close.js'
import { runDriftEvaluation } from './drift.js'
import type { HeartbeatContext } from '../types/sil.js'
import type { ExecContext } from '../types/exec.js'

// Minimal ExecContext stub for SIL tool tests — policy/io/firstWriteDone unused by SIL tools.
function makeSilExecCtx(layout: ReturnType<typeof createLayout>, logger: ReturnType<typeof createLogger>): ExecContext {
  return {
    layout,
    baseline: {} as Baseline,
    logger,
    sessionId: 'test',
    policy: { commands: [], domains: [], skills: [],
      async addCommand() {}, async addDomain() {}, async addSkill() {} },
    io: { async prompt() { return '' }, write() {} },
    firstWriteDone: { value: false },
  }
}

let tmpDir: string

beforeEach(async () => {
  tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'fcp-sil-'))
})

afterEach(async () => {
  await fs.rm(tmpDir, { recursive: true, force: true })
})

function makeBaseline(): Baseline {
  return {
    version:  '1.0',
    entityId: 'test',
    cpe:      { topology: 'transparent', backend: 'test' },
    heartbeat:        { cycleThreshold: 5, intervalSeconds: 60 },
    watchdog:         { silThresholdSeconds: 300 },
    contextWindow:    { budgetTokens: 10000, criticalPct: 80 },
    drift:            { comparisonMechanism: 'ncd-gzip-v1', threshold: 0.5 },
    sessionStore:     { rotationThresholdBytes: 1048576 },
    workingMemory:    { maxEntries: 20 },
    integrityChain:   { checkpointInterval: 5 },
    preSessionBuffer: { maxEntries: 3 },
    operatorChannel:  { notificationsDir: 'state/op' },
    fault:            { nBoot: 3, nChannel: 3, nRetry: 3 },
  }
}

function makeCtx(layout = createLayout(tmpDir)): HeartbeatContext {
  return {
    layout,
    baseline:        makeBaseline(),
    logger:          createLogger({ test: true }),
    cycleCount:      0,
    lastHeartbeatTs: new Date().toISOString(),
    inputTokens:     0,
  }
}

// ─── Chain ───────────────────────────────────────────────────────────────────

describe('SIL — chain', () => {
  it('readChain returns empty when file does not exist', async () => {
    const layout = createLayout(tmpDir)
    expect(await readChain(layout)).toHaveLength(0)
  })

  it('appendEndureCommit creates a linked entry after genesis', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(path.dirname(layout.state.integrityChain), { recursive: true })
    // Write a genesis entry manually (as FAP would)
    const genesis = { seq: 0, ts: new Date().toISOString(), type: 'genesis', imprintHash: 'sha256:abc', prevHash: null }
    await fs.appendFile(layout.state.integrityChain, JSON.stringify(genesis) + '\n', 'utf8')

    await appendEndureCommit(layout, {
      evolutionAuthDigest: 'sha256:' + 'a'.repeat(64),
      files:               { 'boot.md': 'sha256:' + 'b'.repeat(64) },
      integrityDocHash:    'sha256:' + 'c'.repeat(64),
    })

    const chain = await readChain(layout)
    expect(chain).toHaveLength(2)
    expect(chain[1]!.type).toBe('ENDURE_COMMIT')
    expect(chain[1]!.seq).toBe(1)
  })

  it('appendModelChange creates a linked MODEL_CHANGE entry', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(path.dirname(layout.state.integrityChain), { recursive: true })
    const genesis = { seq: 0, ts: new Date().toISOString(), type: 'genesis', imprintHash: 'sha256:abc', prevHash: null }
    await fs.appendFile(layout.state.integrityChain, JSON.stringify(genesis) + '\n', 'utf8')

    await appendModelChange(layout, {
      from: 'claude-3', to: 'claude-4',
      files: {}, integrityDocHash: 'sha256:' + 'd'.repeat(64),
    })

    const chain = await readChain(layout)
    expect(chain[1]!.type).toBe('MODEL_CHANGE')
  })
})

// ─── Integrity verification ───────────────────────────────────────────────────

describe('SIL — integrity verification', () => {
  it('verifyIntegrityDoc returns missing when integrity.json absent', async () => {
    const layout = createLayout(tmpDir)
    const result = await verifyIntegrityDoc(layout)
    expect(result.clean).toBe(false)
    expect(result.mismatches[0]!.reason).toBe('missing')
  })

  it('verifyIntegrityDoc reports clean when all hashes match', async () => {
    const layout = createLayout(tmpDir)
    // Create all required tracked files
    await fs.mkdir(layout.state.dir, { recursive: true })
    await fs.writeFile(layout.bootMd, '# boot', 'utf8')
    await fs.writeFile(layout.state.baseline, JSON.stringify({ version: '1.0' }), 'utf8')
    await refreshIntegrityDoc(layout)

    const result = await verifyIntegrityDoc(layout)
    expect(result.clean).toBe(true)
  })

  it('verifyIntegrityDoc reports hash_mismatch when file changes', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.state.dir, { recursive: true })
    await fs.writeFile(layout.bootMd, '# original', 'utf8')
    await fs.writeFile(layout.state.baseline, JSON.stringify({ version: '1.0' }), 'utf8')
    await refreshIntegrityDoc(layout)

    // Mutate the file
    await fs.writeFile(layout.bootMd, '# tampered', 'utf8')
    const result = await verifyIntegrityDoc(layout)
    expect(result.clean).toBe(false)
    expect(result.mismatches[0]!.reason).toBe('hash_mismatch')
  })

  it('verifyChainFromImprint returns invalid when imprint.json is absent', async () => {
    const layout = createLayout(tmpDir)
    const result = await verifyChainFromImprint(layout)
    expect(result.valid).toBe(false)
  })
})

// ─── Vital checks ─────────────────────────────────────────────────────────────

describe('SIL — budgetCheck', () => {
  it('returns ok when usage is low', async () => {
    const ctx = makeCtx()
    const r = await budgetCheck.run({ ...ctx, inputTokens: 1000 })
    expect(r.ok).toBe(true)
  })

  it('returns degraded when usage is in warn band', async () => {
    const ctx = makeCtx()
    // critical=80, warn=70; 75% usage
    const r = await budgetCheck.run({ ...ctx, inputTokens: 7500 })
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.severity).toBe('degraded')
  })

  it('returns critical when usage exceeds threshold', async () => {
    const ctx = makeCtx()
    const r = await budgetCheck.run({ ...ctx, inputTokens: 9000 })
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.severity).toBe('critical')
  })
})

describe('SIL — focusCheck', () => {
  it('returns ok when workspace_focus.json is absent', async () => {
    const ctx = makeCtx()
    expect((await focusCheck.run(ctx)).ok).toBe(true)
  })

  it('returns critical when focus is inside entity root', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.state.dir, { recursive: true })
    const focusPath = path.join(tmpDir, 'workspace')
    await fs.mkdir(focusPath, { recursive: true })
    // Set focus INSIDE entity root
    await fs.writeFile(layout.state.workspaceFocus, JSON.stringify({ path: path.join(tmpDir, 'src') }), 'utf8')
    const r = await focusCheck.run(makeCtx(layout))
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.severity).toBe('critical')
  })
})

describe('SIL — inboxCheck', () => {
  it('returns ok when presession dir is absent', async () => {
    const r = await inboxCheck.run(makeCtx())
    expect(r.ok).toBe(true)
  })

  it('returns degraded when presession dir exceeds max_entries', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.io.presession, { recursive: true })
    for (let i = 0; i < 5; i++) {
      await fs.writeFile(path.join(layout.io.presession, `${i}.msg`), '{}', 'utf8')
    }
    const r = await inboxCheck.run(makeCtx(layout))
    // baseline.pre_session_buffer.max_entries = 3
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.severity).toBe('degraded')
  })
})

describe('SIL — identityCheck', () => {
  it('returns ok when integrity.json is clean', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.state.dir, { recursive: true })
    await fs.writeFile(layout.bootMd, '# boot', 'utf8')
    await fs.writeFile(layout.state.baseline, JSON.stringify({ version: '1.0' }), 'utf8')
    await refreshIntegrityDoc(layout)
    const r = await identityCheck.run(makeCtx(layout))
    expect(r.ok).toBe(true)
  })

  it('returns critical when a tracked file is modified', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.state.dir, { recursive: true })
    await fs.writeFile(layout.bootMd, '# original', 'utf8')
    await fs.writeFile(layout.state.baseline, JSON.stringify({ version: '1.0' }), 'utf8')
    await refreshIntegrityDoc(layout)
    await fs.writeFile(layout.bootMd, '# tampered', 'utf8')
    const r = await identityCheck.run(makeCtx(layout))
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.severity).toBe('critical')
  })
})

// ─── Heartbeat ────────────────────────────────────────────────────────────────

describe('SIL — createHeartbeat', () => {
  it('shouldRun is true when cycleCount exceeds threshold', () => {
    const layout   = createLayout(tmpDir)
    const baseline = makeBaseline()
    const logger   = createLogger({ test: true })
    const hb = createHeartbeat(layout, baseline, logger, [])
    const old = new Date(Date.now() - 1000).toISOString()
    expect(hb.shouldRun(5, old)).toBe(true)
  })

  it('shouldRun is false when cycle and time thresholds are not met', () => {
    const layout   = createLayout(tmpDir)
    const baseline = makeBaseline()
    const logger   = createLogger({ test: true })
    const hb = createHeartbeat(layout, baseline, logger, [])
    const now = new Date().toISOString()
    expect(hb.shouldRun(0, now)).toBe(false)
  })

  it('run returns all vital results', async () => {
    const layout   = createLayout(tmpDir)
    const baseline = makeBaseline()
    const logger   = createLogger({ test: true })
    const hb = createHeartbeat(layout, baseline, logger, [budgetCheck])
    const result = await hb.run(3, 100, new Date().toISOString())
    expect(result.vitals).toHaveLength(1)
    expect(result.vitals[0]!.check).toBe('context_budget')
  })
})

// ─── Endure ───────────────────────────────────────────────────────────────────

describe('SIL — endure', () => {
  it('fcp_evolution_proposal queues a pending proposal entry', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.state.dir, { recursive: true })
    const logger = createLogger({ test: true })
    const execCtx = makeSilExecCtx(layout, logger)
    const result = await evolutionProposalHandler.execute({ content: 'install skill foo' }, execCtx)
    expect(result.ok).toBe(true)
    if (result.ok) expect(result.output).toMatch(/id:/)
    const data = JSON.parse(await fs.readFile(layout.state.pendingProposals, 'utf8'))
    expect(data.proposals).toHaveLength(1)
    expect(data.proposals[0].digest).toMatch(/^sha256:/)
  })

  it('approveProposal sets approvedAt', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.state.dir, { recursive: true })
    const logger = createLogger({ test: true })
    const execCtx = makeSilExecCtx(layout, logger)
    const result = await evolutionProposalHandler.execute({ content: 'some change' }, execCtx)
    if (!result.ok) throw new Error(result.error)
    const id = result.output.match(/id: (.+)/)![1]!
    const ok = await approveProposal(layout, id)
    expect(ok).toBe(true)
  })

  it('runEndureProtocol writes ENDURE_COMMIT and removes approved proposals', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.state.dir, { recursive: true })
    await fs.mkdir(layout.memory.dir, { recursive: true })
    // Set up a genesis entry in the chain
    await fs.mkdir(path.dirname(layout.state.integrityChain), { recursive: true })
    const genesis = { seq: 0, ts: new Date().toISOString(), type: 'genesis', imprintHash: 'sha256:abc', prevHash: null }
    await fs.appendFile(layout.state.integrityChain, JSON.stringify(genesis) + '\n', 'utf8')

    // Create required tracked files
    await fs.writeFile(layout.bootMd, '# boot', 'utf8')
    await fs.writeFile(layout.state.baseline, JSON.stringify({ version: '1.0' }), 'utf8')
    const logger = createLogger({ test: true })
    const execCtx = makeSilExecCtx(layout, logger)
    const result = await evolutionProposalHandler.execute({ content: 'evolve something' }, execCtx)
    if (!result.ok) throw new Error(result.error)
    const id = result.output.match(/id: (.+)/)![1]!
    await approveProposal(layout, id)
    await runEndureProtocol(layout, logger)

    const chain = await readChain(layout)
    expect(chain.some(e => e.type === 'ENDURE_COMMIT')).toBe(true)
    // Pending proposals should be removed
    const exists = await fs.access(layout.state.pendingProposals).then(() => true).catch(() => false)
    expect(exists).toBe(false)
  })
})

// ─── Drift ────────────────────────────────────────────────────────────────────

describe('SIL — drift', () => {
  it('runDriftEvaluation returns empty when no probes', async () => {
    const layout  = createLayout(tmpDir)
    const logger  = createLogger({ test: true })
    const reports = await runDriftEvaluation(layout, logger)
    expect(reports).toHaveLength(0)
  })

  it('evaluates hash probe: mismatch when content changes', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.state.dir, { recursive: true })
    await fs.mkdir(layout.memory.dir, { recursive: true })
    const logger  = createLogger({ test: true })
    // Create a target memory file
    await fs.mkdir(layout.memory.dir, { recursive: true })
    const target = path.join(layout.memory.dir, 'concept.md')
    await fs.writeFile(target, 'original content', 'utf8')

    // Write a probe with a hash that does NOT match current content
    const probe = {
      id:            'probe-1',
      description:   'test probe',
      target:        'memory/concept.md',
      deterministic: { type: 'hash', value: 'wronghash' },
      reference:     null,
    }
    await fs.appendFile(layout.state.driftProbes, JSON.stringify(probe) + '\n', 'utf8')

    const reports = await runDriftEvaluation(layout, logger)
    expect(reports).toHaveLength(1)
    expect(reports[0]!.exceeds).toBe(true)
  })
})

// ─── SIL tool handlers ───────────────────────────────────────────────────────

describe('SIL — fcp_session_close', () => {
  it('returns the SESSION_CLOSE_SIGNAL sentinel', async () => {
    const layout = createLayout(tmpDir)
    const logger = createLogger({ test: true })
    const ctx    = makeSilExecCtx(layout, logger)
    const r = await sessionCloseHandler.execute({}, ctx)
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.output).toBe(SESSION_CLOSE_SIGNAL)
  })
})

describe('SIL — fcp_evolution_proposal', () => {
  it('creates state/ dir if missing', async () => {
    const layout = createLayout(tmpDir)
    const logger = createLogger({ test: true })
    const ctx    = makeSilExecCtx(layout, logger)
    const r = await evolutionProposalHandler.execute({ content: 'add new skill' }, ctx)
    expect(r.ok).toBe(true)
    await expect(fs.access(layout.state.pendingProposals)).resolves.toBeUndefined()
  })

  it('requires content', async () => {
    const layout = createLayout(tmpDir)
    const logger = createLogger({ test: true })
    const ctx    = makeSilExecCtx(layout, logger)
    const r = await evolutionProposalHandler.execute({}, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/content/)
  })

  it('rejects empty content', async () => {
    const layout = createLayout(tmpDir)
    const logger = createLogger({ test: true })
    const ctx    = makeSilExecCtx(layout, logger)
    const r = await evolutionProposalHandler.execute({ content: '   ' }, ctx)
    expect(r.ok).toBe(false)
  })

  it('accumulates multiple proposals', async () => {
    const layout = createLayout(tmpDir)
    const logger = createLogger({ test: true })
    const ctx    = makeSilExecCtx(layout, logger)
    await evolutionProposalHandler.execute({ content: 'proposal one' }, ctx)
    await evolutionProposalHandler.execute({ content: 'proposal two' }, ctx)
    const data = JSON.parse(await fs.readFile(layout.state.pendingProposals, 'utf8')) as { proposals: unknown[] }
    expect(data.proposals).toHaveLength(2)
  })
})
