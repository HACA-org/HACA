// fcp_agent_run — run a named skill as an isolated stateless agent.
//
// Two execution modes (from manifest.execution):
//   script — spawns skills/<name>/run.js via Node; receives FCP_SKILL_INPUT env var
//   text   — reads SKILL.md or EXECUTE.md and invokes the CPE as a stateless subprocess
//            with a canonical skill-execution persona + the .md instructions as task
//
// Gate (script only, main:session): once/session/deny
// In auto:session the GateIO is wired to auto-deny, so gates resolve as denied
// automatically — no special branching needed here.
//
// file-read inside text execution is always within skills/<name>/ (inside workspace).
// fcp_file_read outside workspace is blocked in auto:session by the auto-deny io.
import { spawn } from 'node:child_process'
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { fileExists, readJson } from '../../store/io.js'
import { SkillManifestSchema } from '../../types/formats/skills.js'
import { resolveToolApproval } from '../../session/approval.js'
import { resolveAdapter } from '../../cpe/cpe.js'
import { SkillIndexSchema } from '../../types/formats/skills.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

const DEFAULT_TIMEOUT_MS = 30_000
const MAX_OUT_BYTES      = 256 * 1024

// Canonical persona injected for text-execution skills.
// The agent receives the .md instructions and must execute them exactly.
const TEXT_SKILL_SYSTEM = `You are a stateless skill executor. Your only task is to follow the instructions provided exactly and return the expected result. Do not improvise, explain, or add context beyond what is asked. If you cannot complete the task, report the specific error clearly.`

interface AgentRunParams {
  skill:  string
  input?: unknown
}

function extractParams(params: unknown): AgentRunParams | null {
  if (typeof params !== 'object' || params === null) return null
  const p = params as Record<string, unknown>
  const skill = typeof p['skill'] === 'string' ? p['skill'].trim() : null
  if (!skill) return null
  return { skill, input: p['input'] }
}

async function runScript(
  scriptPath: string,
  input:      unknown,
  ctx:        ExecContext,
  timeoutMs:  number,
): Promise<ToolResult> {
  const inputJson = JSON.stringify(input ?? {})
  return new Promise<ToolResult>((resolve) => {
    let stdout = ''
    let stderr = ''
    const child = spawn('node', [scriptPath], {
      cwd:   ctx.layout.root,
      env:   { ...process.env, FCP_SKILL_INPUT: inputJson },
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    child.stdout.on('data', (chunk: Buffer) => {
      stdout += chunk.toString('utf8')
      if (stdout.length > MAX_OUT_BYTES) child.kill('SIGTERM')
    })
    child.stderr.on('data', (chunk: Buffer) => { stderr += chunk.toString('utf8') })
    const timer = setTimeout(() => child.kill('SIGTERM'), timeoutMs)
    child.on('close', (code) => {
      clearTimeout(timer)
      if (code !== 0) {
        resolve({ ok: false, error: `skill exited ${code}: ${stderr.slice(0, 512)}` })
      } else {
        resolve({ ok: true, output: (stdout + (stderr ? `\nSTDERR:\n${stderr}` : '')).trim() })
      }
    })
    child.on('error', (err: Error) => { clearTimeout(timer); resolve({ ok: false, error: String(err) }) })
  })
}

async function runText(
  skillDir: string,
  input:    unknown,
  ctx:      ExecContext,
): Promise<ToolResult> {
  // Find instruction file — prefer SKILL.md, fall back to EXECUTE.md
  let instructions: string | null = null
  for (const name of ['SKILL.md', 'EXECUTE.md']) {
    const fp = path.join(skillDir, name)
    if (await fileExists(fp)) {
      instructions = await fs.readFile(fp, 'utf8').catch(() => null)
      break
    }
  }
  if (!instructions) {
    return { ok: false, error: 'text-execution skill has no SKILL.md or EXECUTE.md' }
  }

  const userMessage = [
    '## Instructions\n',
    instructions.trim(),
    '\n## Input\n',
    JSON.stringify(input ?? {}, null, 2),
  ].join('\n')

  let adapter
  try {
    adapter = resolveAdapter(ctx.baseline.cpe.backend)
  } catch (e: unknown) {
    return { ok: false, error: `CPE adapter error: ${String(e)}` }
  }

  try {
    const resp = await adapter.invoke({
      system:   TEXT_SKILL_SYSTEM,
      messages: [{ role: 'user', content: userMessage }],
      tools:    [],
    })
    return { ok: true, output: resp.content }
  } catch (e: unknown) {
    return { ok: false, error: `CPE invocation failed: ${String(e)}` }
  }
}

export const agentRunHandler: ToolHandler = {
  name: 'fcp_agent_run',
  description: 'Run a named skill as an isolated stateless agent. Script skills execute run.js; text skills execute instructions from SKILL.md/EXECUTE.md via the CPE. Requires operator approval in main:session. Timeout: 30 s, max output: 256 KB.',
  inputSchema: {
    type: 'object',
    properties: {
      skill: { type: 'string', description: 'Skill name as registered in skills/index.json.' },
      input: { description: 'Input data passed to the skill (any JSON value).' },
    },
    required: ['skill'],
  },
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    const parsed = extractParams(params)
    if (!parsed) return { ok: false, error: 'skill name is required' }
    if (!/^[a-z][a-z0-9_-]*$/.test(parsed.skill)) {
      return { ok: false, error: 'invalid skill name format' }
    }

    // Gate for script skills in main:session — ask before loading the manifest so
    // the operator can deny before any disk access beyond validation above.
    // text skills never gate (execution is read-only inside the skill dir).
    // We cannot know the execution type without the manifest, so we gate first and
    // skip the gate retroactively for text skills after loading.
    let gateGranted = ctx.sessionMode === 'auto'  // auto:session skips interactive gate
    if (!gateGranted) {
      const decision = await resolveToolApproval(
        `Run agent skill: ${parsed.skill}`,
        'once-session-deny',
        ctx.io,
      )
      if (!decision.granted) return { ok: false, error: 'Denied by operator.' }
      gateGranted = true
    }

    // Load and validate skill index
    if (!await fileExists(ctx.layout.skills.index)) {
      return { ok: false, error: 'skills/index.json not found' }
    }
    let index
    try {
      index = SkillIndexSchema.parse(await readJson(ctx.layout.skills.index))
    } catch {
      return { ok: false, error: 'malformed skills/index.json' }
    }

    const entry = index.skills.find(s => s.name === parsed.skill)
    if (!entry) return { ok: false, error: `skill not found: ${parsed.skill}` }

    // Load and validate skill manifest
    const manifestPath = path.join(ctx.layout.skills.dir, parsed.skill, 'manifest.json')
    if (!await fileExists(manifestPath)) {
      return { ok: false, error: `manifest.json not found for skill: ${parsed.skill}` }
    }
    let manifest
    try {
      manifest = SkillManifestSchema.parse(await readJson(manifestPath))
    } catch {
      return { ok: false, error: `malformed manifest.json for skill: ${parsed.skill}` }
    }

    const skillDir = path.join(ctx.layout.skills.dir, parsed.skill)

    if (manifest.execution === 'text') {
      // text skills execute read-only inside the skill dir — gate already granted above is fine
      ctx.logger.info('exec:agent_run:text', { skill: parsed.skill })
      return runText(skillDir, parsed.input, ctx)
    }

    const scriptPath = path.join(skillDir, 'run.js')
    if (!await fileExists(scriptPath)) {
      return { ok: false, error: `run.js not found for skill: ${parsed.skill}` }
    }

    ctx.logger.info('exec:agent_run:script', { skill: parsed.skill, mode: ctx.sessionMode })
    return runScript(scriptPath, parsed.input, ctx, manifest.timeoutSeconds * 1000)
  },
}
