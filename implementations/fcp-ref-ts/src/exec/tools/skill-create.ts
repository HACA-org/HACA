// fcp_skill_create — scaffold a new custom skill in skills/<name>/.
// Creates: manifest.json + run.js stub + registers in skills/index.json.
import * as path from 'node:path'
import { fileExists, readJson, writeJson, ensureDir, atomicWrite } from '../../store/io.js'
import { SkillIndexSchema, SkillManifestSchema } from '../../types/formats/skills.js'
import { resolveToolApproval } from '../../session/approval.js'
import type { SkillIndex, SkillManifest } from '../../types/formats/skills.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

interface CreateParams {
  name:        string
  description: string
  version?:    string
}

function extractParams(params: unknown): CreateParams | null {
  if (typeof params !== 'object' || params === null) return null
  const p    = params as Record<string, unknown>
  const name = typeof p['name'] === 'string' ? p['name'].trim() : null
  const desc = typeof p['description'] === 'string' ? p['description'].trim() : null
  if (!name || !desc) return null
  const version = typeof p['version'] === 'string' ? p['version'].trim() : '1.0.0'
  return { name, description: desc, version }
}

const RUN_STUB = `#!/usr/bin/env node
// Auto-generated skill stub — implement your skill logic here.
// Input is available via process.env.FCP_SKILL_INPUT (JSON string).
const input = JSON.parse(process.env.FCP_SKILL_INPUT ?? '{}')
console.log(JSON.stringify({ ok: true, input }))
`

export const skillCreateHandler: ToolHandler = {
  name: 'fcp_skill_create',
  description: 'Scaffold a new custom skill: creates skills/<name>/manifest.json and run.js stub, and registers it in skills/index.json. Requires operator approval.',
  inputSchema: {
    type: 'object',
    properties: {
      name:        { type: 'string', description: 'Skill name (lowercase alphanumeric, underscores, hyphens).' },
      description: { type: 'string', description: 'Human-readable description of what the skill does.' },
      version:     { type: 'string', description: 'Semver version string. Defaults to 1.0.0.' },
    },
    required: ['name', 'description'],
  },
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    const parsed = extractParams(params)
    if (!parsed) return { ok: false, error: 'name and description are required' }
    if (!/^[a-z][a-z0-9_-]*$/.test(parsed.name)) {
      return { ok: false, error: 'name must be lowercase alphanumeric with _ or - separators' }
    }

    // Gate: always ask for skill creation
    const decision = await resolveToolApproval(
      `Create new skill: ${parsed.name}`,
      'once-session-allowlist-deny',
      ctx.io,
    )
    if (!decision.granted) return { ok: false, error: 'Denied by operator.' }
    if (decision.tier === 'session')    await ctx.policy.addSkill(parsed.name, 'session')
    if (decision.tier === 'persistent') await ctx.policy.addSkill(parsed.name, 'persistent')

    const skillDir      = path.join(ctx.layout.skills.dir, parsed.name)
    const manifestPath  = path.join(skillDir, 'manifest.json')
    const runPath       = path.join(skillDir, 'run.js')

    if (await fileExists(skillDir)) {
      return { ok: false, error: `skill already exists: ${parsed.name}` }
    }

    // Build and validate manifest
    const manifest: SkillManifest = SkillManifestSchema.parse({
      name:           parsed.name,
      class:          'custom',
      version:        parsed.version ?? '1.0.0',
      description:    parsed.description,
      timeoutSeconds: 30,
      background:     false,
      ttlSeconds:     null,
      permissions:    [],
      dependencies:   [],
    })

    // Load (or initialise) skill index
    let index: SkillIndex = { version: '1.0', skills: [], aliases: {} }
    if (await fileExists(ctx.layout.skills.index)) {
      try {
        index = SkillIndexSchema.parse(await readJson(ctx.layout.skills.index))
      } catch {
        return { ok: false, error: 'malformed skills/index.json — fix before adding skills' }
      }
    }

    if (index.skills.some(s => s.name === parsed.name)) {
      return { ok: false, error: `skill already in index: ${parsed.name}` }
    }

    // Write files
    await ensureDir(skillDir)
    await writeJson(manifestPath, manifest)
    await atomicWrite(runPath, RUN_STUB)

    // Register in index
    index.skills.push({
      name:     parsed.name,
      desc:     parsed.description,
      manifest: `${parsed.name}/manifest.json`,
      class:    'custom',
    })
    await ensureDir(path.dirname(ctx.layout.skills.index))
    await writeJson(ctx.layout.skills.index, index)

    ctx.logger.info('exec:skill_create', { name: parsed.name })
    return { ok: true, output: `Skill created: ${skillDir}` }
  },
}
