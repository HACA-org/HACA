import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mkdtemp, rm, mkdir, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createLayout } from '../store/layout.js'
import { writeJson, touchFile } from '../store/io.js'
import { createLogger } from '../logger/logger.js'
import { runBoot } from './boot.js'
import { BootError } from './types.js'
import type { Layout } from '../store/layout.js'

async function makeEntityFixture(tmp: string, opts: {
  withImprint?: boolean
  withBeacon?: boolean
  withStalToken?: boolean
  profile?: 'haca-core' | 'haca-evolve'
  topology?: string
} = {}): Promise<Layout> {
  const root = join(tmp, 'entity')
  const layout = createLayout(root)

  // Create minimal structure
  await mkdir(join(root, 'persona'), { recursive: true })
  await mkdir(join(root, 'state'), { recursive: true })
  await mkdir(join(root, 'skills'), { recursive: true })
  await mkdir(join(root, 'io', 'inbox', 'presession'), { recursive: true })
  await mkdir(join(root, 'io', 'notifications'), { recursive: true })
  await mkdir(join(root, 'memory'), { recursive: true })

  await writeFile(join(root, 'persona', 'identity.md'), '# Identity', 'utf8')
  await writeFile(join(root, 'BOOT.md'), '# Boot', 'utf8')

  const profile = opts.profile ?? 'haca-core'
  const topology = opts.topology ?? 'transparent'
  await writeJson(layout.baseline, { cpe: { topology }, haca_profile: profile })
  await writeJson(layout.skillsIndex, { skills: [] })

  // Integrity doc with correct hashes
  const { createHash } = await import('node:crypto')
  const { readFile } = await import('node:fs/promises')
  const hash = (data: string) => 'sha256:' + createHash('sha256').update(data, 'utf8').digest('hex')

  // Canonical schema: { version, algorithm, files: { 'relative/path' -> hash } }
  const toRel = (abs: string) => abs.startsWith(root + '/') ? abs.slice(root.length + 1) : abs
  const files: Record<string, string> = {
    [toRel(layout.baseline)]:    hash(await readFile(layout.baseline, 'utf8')),
    [toRel(layout.bootMd)]:      hash(await readFile(layout.bootMd, 'utf8')),
    [toRel(layout.skillsIndex)]: hash(await readFile(layout.skillsIndex, 'utf8')),
  }
  await writeJson(layout.integrity, { version: '1.0', algorithm: 'sha256', files })

  if (opts.withImprint) {
    await writeJson(layout.imprint, {
      version: '1.0',
      activatedAt: new Date().toISOString(),
      hacaProfile: profile,
      operatorBound: { name: 'Test User', email: 'test@example.com', hash: 'sha256:abc' },
      structuralBaseline: 'sha256:x',
      integrityDocument: 'sha256:y',
      skillsIndex: 'sha256:z',
      genesisOmega: 'sha256:omega',
    })
  }

  if (opts.withBeacon) {
    await writeFile(layout.distressBeacon, '', 'utf8')
  }

  if (opts.withStalToken) {
    await touchFile(layout.sessionToken)
  }

  return layout
}

describe('Boot — warm boot', () => {
  let tmp: string

  beforeEach(async () => {
    tmp = await mkdtemp(join(tmpdir(), 'fcp-boot-'))
  })

  afterEach(async () => {
    await rm(tmp, { recursive: true, force: true })
  })

  it('boots successfully with valid entity', async () => {
    const layout = await makeEntityFixture(tmp, { withImprint: true })
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const result = await runBoot(layout, logger)
    expect(result.isFirstBoot).toBe(false)
    expect(result.crashRecovered).toBe(false)
    expect(result.sessionId).toMatch(/^[0-9a-f-]{36}$/)
    expect(result.pendingProposals).toEqual([])
  })

  it('emits session token on successful boot', async () => {
    const { existsSync } = await import('node:fs')
    const layout = await makeEntityFixture(tmp, { withImprint: true })
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    await runBoot(layout, logger)
    expect(existsSync(layout.sessionToken)).toBe(true)
  })

  it('throws BootError if distress beacon is active', async () => {
    const layout = await makeEntityFixture(tmp, { withImprint: true, withBeacon: true })
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    await expect(runBoot(layout, logger)).rejects.toThrow(BootError)
    await expect(runBoot(layout, logger)).rejects.toThrow('beacon')
  })

  it('throws BootError if imprint is missing', async () => {
    const layout = await makeEntityFixture(tmp)
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    // No imprint → FAP triggered, but FAP will fail on operator enrollment (no tty)
    // We test phase0 directly via warm boot path by adding a fake imprint then removing it
    await writeJson(layout.imprint, {}) // invalid imprint
    await expect(runBoot(layout, logger)).rejects.toThrow(BootError)
  })

  it('detects crash and recovers when stale session token exists', async () => {
    const layout = await makeEntityFixture(tmp, { withImprint: true, withStalToken: true })
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const result = await runBoot(layout, logger)
    expect(result.crashRecovered).toBe(true)
    const counters = await logger.getCounters()
    expect(counters.crashes).toBe(1)
  })

  it('throws BootError on identity drift', async () => {
    const layout = await makeEntityFixture(tmp, { withImprint: true })
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    // Tamper with baseline after integrity doc was created
    await writeJson(layout.baseline, { cpe: { topology: 'transparent' }, tampered: true })
    await expect(runBoot(layout, logger)).rejects.toThrow('Identity drift')
  })

  it('throws BootError if baseline is missing', async () => {
    const layout = await makeEntityFixture(tmp, { withImprint: true })
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const { rm } = await import('node:fs/promises')
    await rm(layout.baseline)
    await expect(runBoot(layout, logger)).rejects.toThrow(BootError)
  })

  it('increments sessions counter on successful boot', async () => {
    const layout = await makeEntityFixture(tmp, { withImprint: true })
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    await runBoot(layout, logger)
    const counters = await logger.getCounters()
    expect(counters.sessions).toBe(1)
  })
})

describe('Boot — FAP cold-start', () => {
  let tmp: string

  beforeEach(async () => {
    tmp = await mkdtemp(join(tmpdir(), 'fcp-fap-'))
  })

  afterEach(async () => {
    vi.restoreAllMocks()
    await rm(tmp, { recursive: true, force: true })
  })

  it('runs FAP when imprint is absent', async () => {
    const layout = await makeEntityFixture(tmp, { withImprint: false })
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))

    // Mock FAP operator enrollment
    vi.mock('./prompt.js', () => ({
      createPrompt: () => ({
        ask: vi.fn()
          .mockResolvedValueOnce('Test User')  // name
          .mockResolvedValueOnce('test@test.com') // email
          .mockResolvedValueOnce('y'),          // confirm
        close: vi.fn(),
      }),
    }))

    const result = await runBoot(layout, logger)
    expect(result.isFirstBoot).toBe(true)
    expect(result.sessionId).toMatch(/^[0-9a-f-]{36}$/)
  })
})
