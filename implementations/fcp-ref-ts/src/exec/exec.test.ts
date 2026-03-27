// EXEC unit tests — registry, dispatch, allowlist, and all tool handlers.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
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
import type { ExecContext }    from '../types/exec.js'
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

function makeCtx(): ExecContext {
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
  return { layout, baseline, logger, sessionId: 'test-session-id' }
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
  it('isAllowed returns false for new skill', async () => {
    const ctx    = makeCtx()
    const policy = await loadAllowlistPolicy(ctx.layout)
    expect(policy.isAllowed('my_skill')).toBe(false)
  })

  it('session grant is reflected in isAllowed', async () => {
    const ctx    = makeCtx()
    const policy = await loadAllowlistPolicy(ctx.layout)
    await policy.grant('my_skill', 'session')
    expect(policy.isAllowed('my_skill')).toBe(true)
  })

  it('persistent grant writes allowlist.json', async () => {
    const ctx    = makeCtx()
    await fs.mkdir(ctx.layout.state.dir, { recursive: true })
    const policy = await loadAllowlistPolicy(ctx.layout)
    await policy.grant('my_skill', 'persistent')
    const raw  = JSON.parse(await fs.readFile(ctx.layout.state.allowlist, 'utf8')) as Record<string, unknown>
    expect(raw['my_skill']).toBe(true)
  })

  it('loads existing persistent allowlist on startup', async () => {
    const ctx = makeCtx()
    await fs.mkdir(ctx.layout.state.dir, { recursive: true })
    await fs.writeFile(ctx.layout.state.allowlist, JSON.stringify({ pre_loaded: true }), 'utf8')
    const policy = await loadAllowlistPolicy(ctx.layout)
    expect(policy.isAllowed('pre_loaded')).toBe(true)
  })
})

// ─── fcp_file_read ────────────────────────────────────────────────────────────

describe('EXEC — fcp_file_read', () => {
  it('reads file content', async () => {
    const ctx  = makeCtx()
    const file = path.join(workspace, 'test.txt')
    await fs.writeFile(file, 'test content', 'utf8')
    const r = await fileReadHandler.execute({ path: file }, ctx)
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.output).toBe('test content')
  })

  it('rejects path outside workspace', async () => {
    const ctx = makeCtx()
    const r   = await fileReadHandler.execute({ path: path.join(tmpDir, 'outside.txt') }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/outside workspace/)
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
  it('writes file and returns ok', async () => {
    const ctx  = makeCtx()
    const file = path.join(workspace, 'out.txt')
    const r    = await fileWriteHandler.execute({ path: file, content: 'hello' }, ctx)
    expect(r.ok).toBe(true)
    expect(await fs.readFile(file, 'utf8')).toBe('hello')
  })

  it('creates intermediate directories', async () => {
    const ctx  = makeCtx()
    const file = path.join(workspace, 'deep', 'dir', 'out.txt')
    const r    = await fileWriteHandler.execute({ path: file, content: 'nested' }, ctx)
    expect(r.ok).toBe(true)
  })

  it('rejects path outside workspace', async () => {
    const ctx = makeCtx()
    const r   = await fileWriteHandler.execute({ path: path.join(tmpDir, 'out.txt'), content: 'bad' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/outside workspace/)
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

  it('blocks loopback address', async () => {
    const ctx = makeCtx()
    const r   = await webFetchHandler.execute({ url: 'http://127.0.0.1/secret' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/blocked/)
  })

  it('blocks localhost', async () => {
    const ctx = makeCtx()
    const r   = await webFetchHandler.execute({ url: 'http://localhost/secret' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/blocked/)
  })

  it('blocks private RFC-1918 address', async () => {
    const ctx = makeCtx()
    const r   = await webFetchHandler.execute({ url: 'http://192.168.1.100/internal' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/blocked/)
  })
})

// ─── fcp_shell_run ────────────────────────────────────────────────────────────

describe('EXEC — fcp_shell_run', () => {
  it('requires cmd param', async () => {
    const ctx = makeCtx()
    const r   = await shellRunHandler.execute({}, ctx)
    expect(r.ok).toBe(false)
  })

  it('rejects disallowed command', async () => {
    const ctx = makeCtx()
    const r   = await shellRunHandler.execute({ cmd: 'rm', args: ['-rf', '/'] }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/allowlist/)
  })

  it('runs whitelisted command', async () => {
    const ctx = makeCtx()
    const r   = await shellRunHandler.execute({ cmd: 'echo', args: ['hello', 'world'] }, ctx)
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.output).toContain('hello world')
  })

  it('rejects cwd outside workspace', async () => {
    const ctx = makeCtx()
    const r   = await shellRunHandler.execute({ cmd: 'ls', args: [], cwd: tmpDir }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/outside workspace/)
  })
})

// ─── fcp_agent_run ───────────────────────────────────────────────────────────

describe('EXEC — fcp_agent_run', () => {
  it('returns error when skill index missing', async () => {
    const ctx = makeCtx()
    const r   = await agentRunHandler.execute({ skill: 'my_skill' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/index.json/)
  })

  it('returns error when skill not in index', async () => {
    const ctx = makeCtx()
    await fs.mkdir(ctx.layout.skills.dir, { recursive: true })
    await fs.writeFile(ctx.layout.skills.index,
      JSON.stringify({ version: '1.0', skills: [], aliases: {} }), 'utf8')
    const r = await agentRunHandler.execute({ skill: 'missing_skill' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/not found/)
  })

  it('rejects invalid skill name format', async () => {
    const ctx = makeCtx()
    const r   = await agentRunHandler.execute({ skill: 'INVALID SKILL' }, ctx)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/invalid skill name/)
  })

  it('requires skill param', async () => {
    const ctx = makeCtx()
    const r   = await agentRunHandler.execute({}, ctx)
    expect(r.ok).toBe(false)
  })
})

// ─── fcp_skill_create ────────────────────────────────────────────────────────

describe('EXEC — fcp_skill_create', () => {
  it('creates skill scaffold and registers in index', async () => {
    const ctx = makeCtx()
    await fs.mkdir(ctx.layout.skills.dir, { recursive: true })
    const r = await skillCreateHandler.execute(
      { name: 'my_tool', description: 'A test skill' }, ctx)
    expect(r.ok).toBe(true)

    // Verify directory and files
    const skillDir = path.join(ctx.layout.skills.dir, 'my_tool')
    await expect(fs.access(skillDir)).resolves.toBeUndefined()
    await expect(fs.access(path.join(skillDir, 'manifest.json'))).resolves.toBeUndefined()
    await expect(fs.access(path.join(skillDir, 'run.js'))).resolves.toBeUndefined()

    // Verify index entry
    const index = JSON.parse(await fs.readFile(ctx.layout.skills.index, 'utf8')) as {
      skills: Array<{ name: string }>
    }
    expect(index.skills.some(s => s.name === 'my_tool')).toBe(true)
  })

  it('rejects invalid name format', async () => {
    const ctx = makeCtx()
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

  it('refuses to overwrite existing skill', async () => {
    const ctx = makeCtx()
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
