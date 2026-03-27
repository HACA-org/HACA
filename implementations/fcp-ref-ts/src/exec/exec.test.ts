// EXEC unit tests — registry, dispatch, allowlist, and all tool handlers.
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import * as os from 'node:os'
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { createLayout } from '../types/store.js'
import { createLogger } from '../logger/logger.js'
import { createToolRegistry }  from './registry.js'
import { dispatch }            from './dispatch.js'
import { loadAllowlistPolicy } from './allowlist.js'
import { fileReadHandler }     from './tools/file-read.js'
import { fileWriteHandler }    from './tools/file-write.js'
import { webFetchHandler }     from './tools/web-fetch.js'
import { shellRunHandler }     from './tools/shell-run.js'
import { agentRunHandler }     from './tools/agent-run.js'
import { skillCreateHandler }  from './tools/skill-create.js'
import { skillAuditHandler }   from './tools/skill-audit.js'
import type { ExecContext, AllowlistPolicy, GateIO } from '../types/exec.js'
import type { ToolUseBlock }   from '../types/cpe.js'

let tmpDir:   string
let workspace: string

beforeEach(async () => {
  tmpDir    = await fs.mkdtemp(path.join(os.tmpdir(), 'fcp-exec-'))
  workspace = path.join(tmpDir, 'workspace')
  await fs.mkdir(workspace, { recursive: true })
  // Write workspace-focus.json so file/shell tools can resolve the workspace
  await fs.mkdir(path.join(tmpDir, 'state'), { recursive: true })
  await fs.writeFile(
    path.join(tmpDir, 'state', 'workspace-focus.json'),
    JSON.stringify({ path: workspace }),
    'utf8',
  )
})

afterEach(async () => {
  await fs.rm(tmpDir, { recursive: true, force: true })
})

// Stub policy — pre-populated with safe shell commands, empty domains/skills.
function makePolicy(
  commands: string[] = ['ls', 'echo', 'grep', 'find', 'wc', 'head', 'tail'],
  domains: string[] = [],
  skills: string[] = [],
): AllowlistPolicy {
  const cmds = new Set(commands)
  const doms = new Set(domains)
  const skls = new Set(skills)
  return {
    get commands() { return [...cmds] },
    get domains()  { return [...doms] },
    get skills()   { return [...skls] },
    async addCommand(cmd, _tier) { cmds.add(cmd) },
    async addDomain(d, _tier)   { doms.add(d) },
    async addSkill(s, _tier)    { skls.add(s) },
  }
}

// Stub IO — auto-approves with 'o' (once) by default; override prompt for specific tests.
function makeIO(answer = 'o'): GateIO & { writes: string[] } {
  const writes: string[] = []
  return {
    writes,
    async prompt() { return answer },
    write(text) { writes.push(text) },
  }
}

function makeCtx(opts: {
  policy?: AllowlistPolicy
  io?: GateIO
  firstWriteDone?: { value: boolean }
} = {}): ExecContext {
  const layout  = createLayout(tmpDir)
  const logger  = createLogger({ test: true })
  const baseline = {
    version:  '1.0',
    entityId: 'test-entity',
    cpe:      { topology: 'transparent', backend: 'test' },
    heartbeat:        { cycleThreshold: 10, intervalSeconds: 60 },
    watchdog:         { silThresholdSeconds: 300 },
    contextWindow:    { budgetTokens: 10000, criticalPct: 80 },
    drift:            { comparisonMechanism: 'ncd-gzip-v1', threshold: 0.5 },
    sessionStore:     { rotationThresholdBytes: 1048576 },
    workingMemory:    { maxEntries: 20 },
    integrityChain:   { checkpointInterval: 5 },
    preSessionBuffer: { maxEntries: 10 },
    operatorChannel:  { notificationsDir: 'state/operator-notifications' },
    fault:            { nBoot: 3, nChannel: 3, nRetry: 3 },
  } as import('../types/formats/baseline.js').Baseline
  return {
    layout,
    baseline,
    logger,
    sessionId:      'test-session-id',
    policy:         opts.policy ?? makePolicy(),
    io:             opts.io     ?? makeIO(),
    firstWriteDone: opts.firstWriteDone ?? { value: false },
  }
}

// ─── Registry ───────────────────────────────────────────────────────────────

describe('EXEC — registry', () => {
  it('get returns handler by name', () => {
    const reg = createToolRegistry([fileReadHandler, fileWriteHandler])
    expect(reg.get('fcp_file_read')).toBe(fileReadHandler)
    expect(reg.get('fcp_file_write')).toBe(fileWriteHandler)
  })

  it('get returns undefined for unknown name', () => {
    const reg = createToolRegistry([fileReadHandler])
    expect(reg.get('unknown_tool')).toBeUndefined()
  })

  it('list returns sorted names', () => {
    const reg = createToolRegistry([fileWriteHandler, fileReadHandler])
    expect(reg.list()).toEqual(['fcp_file_read', 'fcp_file_write'])
  })
})

// ─── Dispatch ────────────────────────────────────────────────────────────────

describe('EXEC — dispatch', () => {
  it('returns error for unknown tool', async () => {
    const ctx = makeCtx()
    const reg = createToolRegistry([])
    const tu: ToolUseBlock = { type: 'tool_use', id: 'x', name: 'fcp_unknown', input: {} }
    const result = await dispatch(tu, reg, ctx)
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toMatch(/unknown tool/i)
  })

  it('delegates to the registered handler', async () => {
    const ctx = makeCtx()
    const testFile = path.join(workspace, 'hello.txt')
    await fs.writeFile(testFile, 'hello world', 'utf8')

    const reg = createToolRegistry([fileReadHandler])
    const tu: ToolUseBlock = { type: 'tool_use', id: 'x', name: 'fcp_file_read', input: { path: testFile } }
    const result = await dispatch(tu, reg, ctx)
    expect(result.ok).toBe(true)
    if (result.ok) expect(result.output).toBe('hello world')
  })
})

// ─── Allowlist ───────────────────────────────────────────────────────────────

describe('EXEC — allowlist', () => {
  it('commands not in file return empty list on fresh load', async () => {
    const layout = createLayout(tmpDir)
    const policy = await loadAllowlistPolicy(layout)
    expect(policy.commands).toHaveLength(0)
    expect(policy.domains).toHaveLength(0)
    expect(policy.skills).toHaveLength(0)
  })

  it('addCommand session reflects in commands list', async () => {
    const layout = createLayout(tmpDir)
    const policy = await loadAllowlistPolicy(layout)
    await policy.addCommand('git', 'session')
    expect(policy.commands).toContain('git')
  })

  it('addDomain persistent writes allowlist.json', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.state.dir, { recursive: true })
    const policy = await loadAllowlistPolicy(layout)
    await policy.addDomain('api.example.com', 'persistent')
    const raw = JSON.parse(await fs.readFile(layout.state.allowlist, 'utf8')) as {
      domains: string[]
    }
    expect(raw.domains).toContain('api.example.com')
  })

  it('loads existing allowlist.json on startup', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.state.dir, { recursive: true })
    await fs.writeFile(layout.state.allowlist, JSON.stringify({
      commands: ['git'], domains: ['github.com'], skills: ['my_skill'],
    }), 'utf8')
    const policy = await loadAllowlistPolicy(layout)
    expect(policy.commands).toContain('git')
    expect(policy.domains).toContain('github.com')
    expect(policy.skills).toContain('my_skill')
  })

  it('starts empty when allowlist.json is malformed', async () => {
    const layout = createLayout(tmpDir)
    await fs.mkdir(layout.state.dir, { recursive: true })
    await fs.writeFile(layout.state.allowlist, 'not-valid-json{{{', 'utf8')
    const policy = await loadAllowlistPolicy(layout)
    expect(policy.commands).toHaveLength(0)
  })
})

// ─── fcp_file_read ────────────────────────────────────────────────────────────

describe('EXEC — fcp_file_read', () => {
  it('reads file inside workspace without prompting', async () => {
    const io  = makeIO()
    const ctx = makeCtx({ io })
    const file = path.join(workspace, 'test.txt')
    await fs.writeFile(file, 'test content', 'utf8')
    const r = await fileReadHandler.execute({ path: file }, ctx)
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.output).toBe('test content')
    expect(io.writes).toHaveLength(0)  // no gate prompt
  })

  it('prompts operator when path is outside workspace — approved once', async () => {
    const outside = path.join(tmpDir, 'outside.txt')
    await fs.writeFile(outside, 'secret', 'utf8')
    const ctx = makeCtx({ io: makeIO('o') })
    const r = await fileReadHandler.execute({ path: outside }, ctx)
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.output).toBe('secret')
  })

  it('denies read outside workspace when operator says deny', async () => {
    const ctx = makeCtx({ io: makeIO('d') })
    const r   = await fileReadHandler.execute({ path: path.join(tmpDir, 'outside.txt') }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/[Dd]enied/)
  })

  it('returns error for missing path param', async () => {
    const ctx = makeCtx()
    const r   = await fileReadHandler.execute({}, ctx)
    expect(r.ok).toBe(false)
  })

  it('returns error for non-existent file', async () => {
    const ctx = makeCtx()
    const r   = await fileReadHandler.execute({ path: path.join(workspace, 'nonexistent.txt') }, ctx)
    expect(r.ok).toBe(false)
  })
})

// ─── fcp_file_write ───────────────────────────────────────────────────────────

describe('EXEC — fcp_file_write', () => {
  it('prompts on first write inside workspace — session approval skips subsequent writes', async () => {
    const io  = makeIO('s')  // 'session' → mark firstWriteDone
    const firstWriteDone = { value: false }
    const ctx = makeCtx({ io, firstWriteDone })

    const file = path.join(workspace, 'out.txt')
    const r1 = await fileWriteHandler.execute({ path: file, content: 'first' }, ctx)
    expect(r1.ok).toBe(true)
    expect(io.writes.length).toBeGreaterThan(0)

    // Second write: firstWriteDone is true, no prompt
    const writes1 = io.writes.length
    const r2 = await fileWriteHandler.execute({ path: file, content: 'second' }, ctx)
    expect(r2.ok).toBe(true)
    expect(io.writes.length).toBe(writes1)  // no new prompt
  })

  it('prompts on first write — once approval asks again on next write', async () => {
    const io  = makeIO('o')  // 'once' → don't mark firstWriteDone
    const firstWriteDone = { value: false }
    const ctx = makeCtx({ io, firstWriteDone })

    const file = path.join(workspace, 'out.txt')
    await fileWriteHandler.execute({ path: file, content: 'first' }, ctx)
    const writes1 = io.writes.length
    await fileWriteHandler.execute({ path: file, content: 'second' }, ctx)
    expect(io.writes.length).toBeGreaterThan(writes1)  // prompted again
  })

  it('prompts when writing outside workspace — denied', async () => {
    const ctx = makeCtx({ io: makeIO('d') })
    const r   = await fileWriteHandler.execute({ path: path.join(tmpDir, 'out.txt'), content: 'bad' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/[Dd]enied/)
  })

  it('prompts when writing outside workspace — approved once', async () => {
    const ctx = makeCtx({ io: makeIO('o') })
    const r   = await fileWriteHandler.execute({ path: path.join(tmpDir, 'out.txt'), content: 'ok' }, ctx)
    expect(r.ok).toBe(true)
  })

  it('creates intermediate directories', async () => {
    const ctx  = makeCtx({ io: makeIO('s') })
    const file = path.join(workspace, 'deep', 'dir', 'out.txt')
    const r    = await fileWriteHandler.execute({ path: file, content: 'nested' }, ctx)
    expect(r.ok).toBe(true)
  })

  it('returns error for missing params', async () => {
    const ctx = makeCtx()
    const r   = await fileWriteHandler.execute({ path: 'f.txt' }, ctx)
    expect(r.ok).toBe(false)
  })
})

// ─── fcp_web_fetch ────────────────────────────────────────────────────────────

describe('EXEC — fcp_web_fetch', () => {
  it('requires url param', async () => {
    const ctx = makeCtx()
    const r   = await webFetchHandler.execute({}, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/url/)
  })

  it('rejects non-http scheme', async () => {
    const ctx = makeCtx()
    const r   = await webFetchHandler.execute({ url: 'ftp://example.com/file' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/http/)
  })

  it('blocks loopback address — hard error, no gate', async () => {
    const io  = makeIO('d')  // if gate fires, it would deny — but it shouldn't fire
    const ctx = makeCtx({ io })
    const r   = await webFetchHandler.execute({ url: 'http://127.0.0.1/secret' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/blocked/)
    expect(io.writes).toHaveLength(0)  // no gate prompt
  })

  it('blocks localhost — hard error', async () => {
    const ctx = makeCtx()
    const r   = await webFetchHandler.execute({ url: 'http://localhost/secret' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/blocked/)
  })

  it('blocks private RFC-1918 192.168.x', async () => {
    const ctx = makeCtx()
    const r   = await webFetchHandler.execute({ url: 'http://192.168.1.100/internal' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/blocked/)
  })

  it('blocks 10.x RFC-1918', async () => {
    const ctx = makeCtx()
    const r   = await webFetchHandler.execute({ url: 'http://10.0.0.1/internal' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/blocked/)
  })

  it('blocks 172.16.x RFC-1918', async () => {
    const ctx = makeCtx()
    const r   = await webFetchHandler.execute({ url: 'http://172.16.0.1/internal' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/blocked/)
  })

  it('blocks 172.31.x RFC-1918', async () => {
    const ctx = makeCtx()
    const r   = await webFetchHandler.execute({ url: 'http://172.31.255.254/internal' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/blocked/)
  })

  it('blocks IPv6 loopback — hard error', async () => {
    const ctx = makeCtx()
    const r   = await webFetchHandler.execute({ url: 'http://[::1]/secret' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/blocked/)
  })

  it('prompts operator when domain not in allowlist — denied', async () => {
    const ctx = makeCtx({ io: makeIO('d') })
    const r   = await webFetchHandler.execute({ url: 'https://example.com/data' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/[Dd]enied/)
  })

  it('skips gate when domain is in allowlist', async () => {
    const io     = makeIO('d')  // if gate fires, it would deny
    const policy = makePolicy([], ['example.com'])
    const ctx    = makeCtx({ io, policy })
    // Domain is allowlisted — gate should not fire; fetch proceeds (will fail with network error in test)
    const r = await webFetchHandler.execute({ url: 'https://example.com/data' }, ctx)
    expect(io.writes).toHaveLength(0)  // no gate prompt shown
    // Result may be ok or error depending on network, but it was not denied by gate
    if (!r.ok) expect(r.error).not.toMatch(/[Dd]enied/)
  })
})

// ─── fcp_shell_run ────────────────────────────────────────────────────────────

describe('EXEC — fcp_shell_run', () => {
  it('requires cmd param', async () => {
    const ctx = makeCtx()
    const r   = await shellRunHandler.execute({}, ctx)
    expect(r.ok).toBe(false)
  })

  it('runs command in allowlist without prompting', async () => {
    const io  = makeIO('d')  // if gate fires, it would deny
    const ctx = makeCtx({ io, policy: makePolicy(['echo']) })
    const r   = await shellRunHandler.execute({ cmd: 'echo', args: ['hello'] }, ctx)
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.output).toContain('hello')
    expect(io.writes).toHaveLength(0)  // no gate prompt
  })

  it('prompts when command not in allowlist — approved once', async () => {
    const ctx = makeCtx({ io: makeIO('o'), policy: makePolicy([]) })
    const r   = await shellRunHandler.execute({ cmd: 'echo', args: ['hello'] }, ctx)
    expect(r.ok).toBe(true)
  })

  it('prompts when command not in allowlist — denied', async () => {
    const ctx = makeCtx({ io: makeIO('d'), policy: makePolicy([]) })
    const r   = await shellRunHandler.execute({ cmd: 'rm', args: ['-rf', '/'] }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/[Dd]enied/)
  })

  it('add-to-allowlist persists command in policy', async () => {
    const policy = makePolicy([])
    const ctx    = makeCtx({ io: makeIO('a'), policy })
    await shellRunHandler.execute({ cmd: 'echo', args: ['hi'] }, ctx)
    expect(policy.commands).toContain('echo')
  })

  it('prompts when cwd is outside workspace — denied', async () => {
    const ctx = makeCtx({ io: makeIO('d'), policy: makePolicy(['ls']) })
    const r   = await shellRunHandler.execute({ cmd: 'ls', args: [], cwd: tmpDir }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/[Dd]enied/)
  })

  it('allows cwd outside workspace when operator approves once', async () => {
    const ctx = makeCtx({ io: makeIO('o'), policy: makePolicy(['ls']) })
    const r   = await shellRunHandler.execute({ cmd: 'ls', args: [], cwd: tmpDir }, ctx)
    expect(r.ok).toBe(true)
  })
})

// ─── fcp_agent_run ───────────────────────────────────────────────────────────

describe('EXEC — fcp_agent_run', () => {
  it('requires skill param', async () => {
    const ctx = makeCtx()
    const r   = await agentRunHandler.execute({}, ctx)
    expect(r.ok).toBe(false)
  })

  it('rejects invalid skill name format before gate', async () => {
    const ctx = makeCtx()
    const r   = await agentRunHandler.execute({ skill: 'INVALID SKILL' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/invalid skill name/)
  })

  it('denies when operator says deny', async () => {
    const ctx = makeCtx({ io: makeIO('d') })
    const r   = await agentRunHandler.execute({ skill: 'my_skill' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/[Dd]enied/)
  })

  it('returns error when skill index missing — after gate approval', async () => {
    const ctx = makeCtx({ io: makeIO('o') })
    const r   = await agentRunHandler.execute({ skill: 'my_skill' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/index.json/)
  })

  it('returns error when skill not in index', async () => {
    const ctx = makeCtx({ io: makeIO('o') })
    await fs.mkdir(ctx.layout.skills.dir, { recursive: true })
    await fs.writeFile(ctx.layout.skills.index,
      JSON.stringify({ version: '1.0', skills: [], aliases: {} }), 'utf8')
    const r = await agentRunHandler.execute({ skill: 'missing_skill' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/not found/)
  })
})

// ─── fcp_skill_create ────────────────────────────────────────────────────────

describe('EXEC — fcp_skill_create', () => {
  it('creates skill scaffold and registers in index', async () => {
    const ctx = makeCtx({ io: makeIO('o') })
    await fs.mkdir(ctx.layout.skills.dir, { recursive: true })
    const r = await skillCreateHandler.execute(
      { name: 'my_tool', description: 'A test skill' }, ctx)
    expect(r.ok).toBe(true)

    const skillDir = path.join(ctx.layout.skills.dir, 'my_tool')
    await expect(fs.access(skillDir)).resolves.toBeUndefined()
    await expect(fs.access(path.join(skillDir, 'manifest.json'))).resolves.toBeUndefined()
    await expect(fs.access(path.join(skillDir, 'run.js'))).resolves.toBeUndefined()

    const index = JSON.parse(await fs.readFile(ctx.layout.skills.index, 'utf8')) as {
      skills: Array<{ name: string }>
    }
    expect(index.skills.some(s => s.name === 'my_tool')).toBe(true)
  })

  it('denied by operator', async () => {
    const ctx = makeCtx({ io: makeIO('d') })
    const r   = await skillCreateHandler.execute({ name: 'my_tool', description: 'test' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/[Dd]enied/)
  })

  it('rejects invalid name format before gate', async () => {
    const ctx = makeCtx({ io: makeIO('d') })
    const r   = await skillCreateHandler.execute(
      { name: 'Bad Name!', description: 'test' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/lowercase/)
  })

  it('returns error for missing params', async () => {
    const ctx = makeCtx()
    const r   = await skillCreateHandler.execute({ name: 'my_tool' }, ctx)
    expect(r.ok).toBe(false)
  })

  it('refuses to overwrite existing skill — after gate', async () => {
    const ctx = makeCtx({ io: makeIO('o') })
    await fs.mkdir(path.join(ctx.layout.skills.dir, 'my_tool'), { recursive: true })
    const r = await skillCreateHandler.execute(
      { name: 'my_tool', description: 'dupe' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/already exists/)
  })
})

// ─── fcp_skill_audit ─────────────────────────────────────────────────────────

describe('EXEC — fcp_skill_audit', () => {
  async function setupSkill(ctx: ExecContext): Promise<void> {
    const skillDir = path.join(ctx.layout.skills.dir, 'test_skill')
    await fs.mkdir(skillDir, { recursive: true })
    const manifest = {
      name: 'test_skill', class: 'custom', version: '1.0.0',
      description: 'A test skill', timeoutSeconds: 30,
      background: false, ttlSeconds: null, permissions: [], dependencies: [],
    }
    await fs.writeFile(path.join(skillDir, 'manifest.json'),
      JSON.stringify(manifest), 'utf8')
    await fs.writeFile(path.join(skillDir, 'run.js'), '// stub', 'utf8')
    const index = {
      version: '1.0',
      skills: [{ name: 'test_skill', desc: 'A test skill',
                 manifest: 'test_skill/manifest.json', class: 'custom' }],
      aliases: {},
    }
    await fs.mkdir(ctx.layout.skills.dir, { recursive: true })
    await fs.writeFile(ctx.layout.skills.index, JSON.stringify(index), 'utf8')
  }

  it('returns valid audit report for a well-formed skill', async () => {
    const ctx = makeCtx()
    await setupSkill(ctx)
    const r = await skillAuditHandler.execute({ skill: 'test_skill' }, ctx)
    expect(r.ok).toBe(true)
    if (r.ok) {
      const report = JSON.parse(r.output) as { issues: string[]; run_exists: boolean }
      expect(report.issues).toHaveLength(0)
      expect(report.run_exists).toBe(true)
    }
  })

  it('reports missing run.js in issues', async () => {
    const ctx = makeCtx()
    await setupSkill(ctx)
    await fs.unlink(path.join(ctx.layout.skills.dir, 'test_skill', 'run.js'))
    const r = await skillAuditHandler.execute({ skill: 'test_skill' }, ctx)
    expect(r.ok).toBe(true)
    if (r.ok) {
      const report = JSON.parse(r.output) as { issues: string[] }
      expect(report.issues.some((i: string) => i.includes('run.js'))).toBe(true)
    }
  })

  it('returns error when skill not in index', async () => {
    const ctx = makeCtx()
    await fs.mkdir(ctx.layout.skills.dir, { recursive: true })
    await fs.writeFile(ctx.layout.skills.index,
      JSON.stringify({ version: '1.0', skills: [], aliases: {} }), 'utf8')
    const r = await skillAuditHandler.execute({ skill: 'nonexistent' }, ctx)
    expect(r.ok).toBe(false)
  })

  it('requires skill param', async () => {
    const ctx = makeCtx()
    const r   = await skillAuditHandler.execute({}, ctx)
    expect(r.ok).toBe(false)
  })
})
