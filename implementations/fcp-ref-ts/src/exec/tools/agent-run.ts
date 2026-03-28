// fcp_agent_run — instantiate a named skill as an isolated agent subprocess.
// Looks up the skill in skills/index.json, then executes skills/<name>/run.js
// with a 30-second timeout in a child process.
import { spawn } from 'node:child_process'
import * as path from 'node:path'
import { fileExists, readJson } from '../../store/io.js'
import { SkillIndexSchema } from '../../types/formats/skills.js'
import { resolveToolApproval } from '../../session/approval.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

const DEFAULT_TIMEOUT_MS = 30_000
const MAX_OUT_BYTES      = 256 * 1024

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

export const agentRunHandler: ToolHandler = {
  name: 'fcp_agent_run',
  description: 'Run a named skill as an isolated agent subprocess. The skill must be registered in skills/index.json. Always requires operator approval. Timeout: 30 s, max output: 256 KB.',
  inputSchema: {
    type: 'object',
    properties: {
      skill: { type: 'string', description: 'Skill name as registered in skills/index.json.' },
      input: { description: 'Input data passed to the skill as FCP_SKILL_INPUT (any JSON value).' },
    },
    required: ['skill'],
  },
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    const parsed = extractParams(params)
    if (!parsed) return { ok: false, error: 'skill name is required' }
    if (!/^[a-z][a-z0-9_-]*$/.test(parsed.skill)) {
      return { ok: false, error: 'invalid skill name format' }
    }

    // Gate: always ask for agent execution (once/session/deny — no allowlist option)
    const decision = await resolveToolApproval(
      `Run agent skill: ${parsed.skill}`,
      'once-session-deny',
      ctx.io,
    )
    if (!decision.granted) return { ok: false, error: 'Denied by operator.' }

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

    const scriptPath = path.join(ctx.layout.skills.dir, parsed.skill, 'run.js')
    if (!await fileExists(scriptPath)) {
      return { ok: false, error: `skill script not found: ${scriptPath}` }
    }

    const inputJson = JSON.stringify(parsed.input ?? {})
    ctx.logger.info('exec:agent_run', { skill: parsed.skill })

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
      child.stderr.on('data', (chunk: Buffer) => {
        stderr += chunk.toString('utf8')
      })

      const timer = setTimeout(() => {
        child.kill('SIGTERM')
      }, DEFAULT_TIMEOUT_MS)

      child.on('close', (code) => {
        clearTimeout(timer)
        if (code !== 0) {
          resolve({ ok: false, error: `skill exited ${code}: ${stderr.slice(0, 512)}` })
        } else {
          const out = stdout + (stderr ? `\nSTDERR:\n${stderr}` : '')
          resolve({ ok: true, output: out.trim() })
        }
      })

      child.on('error', (err: Error) => {
        clearTimeout(timer)
        resolve({ ok: false, error: String(err) })
      })
    })
  },
}
