import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mkdtemp, rm, mkdir, writeFile } from 'node:fs/promises'
import { tmpdir, homedir } from 'node:os'
import { join, resolve } from 'node:path'
import { createLayout } from '../store/layout.js'
import { createLogger } from '../logger/logger.js'
import { writeJson } from '../store/io.js'
import { resolveWorkspaceFocus, createBuiltinTools } from './exec.js'
import { readAllowlist, isCommandAllowed, isDomainAllowed } from './allowlist.js'
import type { Layout } from '../store/layout.js'
import type { CPEAdapter } from '../cpe/types.js'
import type { ExecContext } from './types.js'

const mockAdapter: CPEAdapter = {
  provider: 'mock',
  invoke: vi.fn().mockResolvedValue({
    content: 'worker result',
    toolCalls: [],
    usage: { inputTokens: 10, outputTokens: 5 },
    stopReason: 'end_turn',
  }),
}

async function makeFixture(tmp: string): Promise<Layout> {
  const root = join(tmp, 'entity')
  const layout = createLayout(root)
  await mkdir(join(root, 'state'), { recursive: true })
  await mkdir(join(root, 'skills'), { recursive: true })
  return layout
}

describe('resolveWorkspaceFocus', () => {
  it('returns cwd when not inside ~/.fcp', () => {
    const result = resolveWorkspaceFocus('/home/user/projects/myapp')
    expect(result).toBe(resolve('/home/user/projects/myapp'))
  })

  it('returns null when cwd is ~/.fcp', () => {
    const fcpDir = resolve(homedir(), '.fcp')
    expect(resolveWorkspaceFocus(fcpDir)).toBeNull()
  })

  it('returns null when cwd is inside ~/.fcp', () => {
    const fcpDir = resolve(homedir(), '.fcp')
    expect(resolveWorkspaceFocus(join(fcpDir, 'entities', 'foo'))).toBeNull()
  })
})

describe('allowlist helpers', () => {
  it('isCommandAllowed matches base command name', () => {
    expect(isCommandAllowed({ shellRun: ['grep', 'ls'] }, 'grep -r foo .')).toBe(true)
    expect(isCommandAllowed({ shellRun: ['grep', 'ls'] }, 'rm -rf /')).toBe(false)
  })

  it('isDomainAllowed matches exact and subdomains', () => {
    expect(isDomainAllowed({ webFetch: ['github.com'] }, 'https://github.com/repo')).toBe(true)
    expect(isDomainAllowed({ webFetch: ['github.com'] }, 'https://api.github.com/v3')).toBe(true)
    expect(isDomainAllowed({ webFetch: ['github.com'] }, 'https://evil.com')).toBe(false)
  })
})

describe('shellRun tool', () => {
  let tmp: string
  let layout: Layout
  let ctx: ExecContext
  let workspace: string

  beforeEach(async () => {
    tmp = await mkdtemp(join(tmpdir(), 'fcp-exec-'))
    layout = await makeFixture(tmp)
    workspace = join(tmp, 'workspace')
    await mkdir(workspace, { recursive: true })
    ctx = { workspaceFocus: workspace }
  })
  afterEach(async () => { await rm(tmp, { recursive: true, force: true }) })

  it('executes pre-approved command without approval prompt', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    await writeJson(layout.allowlist, { shellRun: ['echo'] })
    const approval = vi.fn().mockResolvedValue('once' as const)
    const sessionGrants = new Set<string>()
    const tools = createBuiltinTools(layout, logger, ctx, mockAdapter, sessionGrants, approval)
    const shellRun = tools.find(t => t.definition.name === 'shellRun')!

    const result = await shellRun.handle({ command: 'echo hello', cwd: workspace })
    expect(result).toContain('hello')
    expect(approval).not.toHaveBeenCalled()
  })

  it('requests approval for unknown command', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const approval = vi.fn().mockResolvedValue('once' as const)
    const sessionGrants = new Set<string>()
    const tools = createBuiltinTools(layout, logger, ctx, mockAdapter, sessionGrants, approval)
    const shellRun = tools.find(t => t.definition.name === 'shellRun')!

    await shellRun.handle({ command: 'echo hello', cwd: workspace })
    expect(approval).toHaveBeenCalledWith(expect.stringContaining('shellRun'))
  })

  it('denies execution when operator denies', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const approval = vi.fn().mockResolvedValue('deny' as const)
    const sessionGrants = new Set<string>()
    const tools = createBuiltinTools(layout, logger, ctx, mockAdapter, sessionGrants, approval)
    const shellRun = tools.find(t => t.definition.name === 'shellRun')!

    const result = await shellRun.handle({ command: 'rm -rf /', cwd: workspace })
    expect(result).toContain('denied')
  })

  it('blocks cwd outside workspace', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const approval = vi.fn().mockResolvedValue('once' as const)
    const sessionGrants = new Set<string>()
    const tools = createBuiltinTools(layout, logger, ctx, mockAdapter, sessionGrants, approval)
    const shellRun = tools.find(t => t.definition.name === 'shellRun')!

    const result = await shellRun.handle({ command: 'ls', cwd: '/tmp' })
    expect(result).toContain('outside workspace')
  })
})

describe('fileRead tool', () => {
  let tmp: string
  let workspace: string
  let ctx: ExecContext

  beforeEach(async () => {
    tmp = await mkdtemp(join(tmpdir(), 'fcp-file-'))
    workspace = join(tmp, 'workspace')
    await mkdir(workspace, { recursive: true })
    ctx = { workspaceFocus: workspace }
  })
  afterEach(async () => { await rm(tmp, { recursive: true, force: true }) })

  it('reads a file inside workspace', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const layout = createLayout(join(tmp, 'entity'))
    await writeFile(join(workspace, 'hello.txt'), 'Hello World', 'utf8')
    const tools = createBuiltinTools(layout, logger, ctx, mockAdapter, new Set(), vi.fn())
    const fileRead = tools.find(t => t.definition.name === 'fileRead')!

    const result = await fileRead.handle({ path: 'hello.txt' })
    expect(result).toBe('Hello World')
  })

  it('blocks path outside workspace', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const layout = createLayout(join(tmp, 'entity'))
    const tools = createBuiltinTools(layout, logger, ctx, mockAdapter, new Set(), vi.fn())
    const fileRead = tools.find(t => t.definition.name === 'fileRead')!

    const result = await fileRead.handle({ path: '/etc/passwd' })
    expect(result).toContain('outside workspace')
  })

  it('returns error when no workspace focus', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const layout = createLayout(join(tmp, 'entity'))
    const noFocusCtx: ExecContext = { workspaceFocus: null }
    const tools = createBuiltinTools(layout, logger, noFocusCtx, mockAdapter, new Set(), vi.fn())
    const fileRead = tools.find(t => t.definition.name === 'fileRead')!

    const result = await fileRead.handle({ path: 'anything.txt' })
    expect(result).toContain('no workspace focus')
  })
})

describe('fileWrite tool', () => {
  let tmp: string
  let workspace: string
  let ctx: ExecContext

  beforeEach(async () => {
    tmp = await mkdtemp(join(tmpdir(), 'fcp-filewrite-'))
    workspace = join(tmp, 'workspace')
    await mkdir(workspace, { recursive: true })
    ctx = { workspaceFocus: workspace }
  })
  afterEach(async () => { await rm(tmp, { recursive: true, force: true }) })

  it('writes a file inside workspace', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const layout = createLayout(join(tmp, 'entity'))
    const tools = createBuiltinTools(layout, logger, ctx, mockAdapter, new Set(), vi.fn())
    const fileWrite = tools.find(t => t.definition.name === 'fileWrite')!

    const result = await fileWrite.handle({ path: 'output.txt', content: 'test content' })
    expect(result).toContain('Written')
    expect(result).toContain('output.txt')
  })

  it('blocks write outside workspace', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const layout = createLayout(join(tmp, 'entity'))
    const tools = createBuiltinTools(layout, logger, ctx, mockAdapter, new Set(), vi.fn())
    const fileWrite = tools.find(t => t.definition.name === 'fileWrite')!

    const result = await fileWrite.handle({ path: '/tmp/evil.txt', content: 'bad' })
    expect(result).toContain('outside workspace')
  })
})

describe('workerSkill tool', () => {
  let tmp: string
  let layout: Layout
  let ctx: ExecContext

  beforeEach(async () => {
    tmp = await mkdtemp(join(tmpdir(), 'fcp-worker-'))
    layout = await makeFixture(tmp)
    ctx = { workspaceFocus: tmp }
  })
  afterEach(async () => { await rm(tmp, { recursive: true, force: true }) })

  it('returns error when task is missing', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const approval = vi.fn().mockResolvedValue('once' as const)
    const tools = createBuiltinTools(layout, logger, ctx, mockAdapter, new Set(), approval)
    const workerSkill = tools.find(t => t.definition.name === 'workerSkill')!

    const result = await workerSkill.handle({})
    expect(result).toContain('task is required')
  })

  it('denies execution when operator denies', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const approval = vi.fn().mockResolvedValue('deny' as const)
    const tools = createBuiltinTools(layout, logger, ctx, mockAdapter, new Set(), approval)
    const workerSkill = tools.find(t => t.definition.name === 'workerSkill')!

    const result = await workerSkill.handle({ task: 'summarize this', persona: 'Summarizer' })
    expect(result).toContain('denied')
  })

  it('invokes adapter and returns result', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const approval = vi.fn().mockResolvedValue('once' as const)
    const tools = createBuiltinTools(layout, logger, ctx, mockAdapter, new Set(), approval)
    const workerSkill = tools.find(t => t.definition.name === 'workerSkill')!

    const result = await workerSkill.handle({ task: 'summarize this', context: 'some content', persona: 'Summarizer' })
    expect(result).toBe('worker result')
  })

  it('uses session grant on second call without re-prompting', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const approval = vi.fn().mockResolvedValue('session' as const)
    const sessionGrants = new Set<string>()
    const tools = createBuiltinTools(layout, logger, ctx, mockAdapter, sessionGrants, approval)
    const workerSkill = tools.find(t => t.definition.name === 'workerSkill')!

    await workerSkill.handle({ task: 'task 1', persona: 'Analyst' })
    await workerSkill.handle({ task: 'task 2', persona: 'Analyst' })
    expect(approval).toHaveBeenCalledTimes(1)
  })

  it('loads canonical persona from built-in personas dir', async () => {
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const approval = vi.fn().mockResolvedValue('once' as const)
    const tools = createBuiltinTools(layout, logger, ctx, mockAdapter, new Set(), approval)
    const workerSkill = tools.find(t => t.definition.name === 'workerSkill')!

    // Should not throw — Summarizer.md exists in built-in personas
    const result = await workerSkill.handle({ task: 'summarize', persona: 'Summarizer' })
    expect(result).toBe('worker result')
  })
})
