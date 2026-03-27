// fcp_skill_audit — read and validate a skill's manifest.json and report status.
import * as path from 'node:path'
import { fileExists, readJson } from '../../store/io.js'
import { SkillIndexSchema, SkillManifestSchema } from '../../types/formats/skills.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

function extractSkill(params: unknown): string | null {
  if (typeof params === 'object' && params !== null && 'skill' in params) {
    const s = (params as Record<string, unknown>)['skill']
    return typeof s === 'string' ? s.trim() : null
  }
  return null
}

interface AuditReport {
  name:         string
  class:        string
  version:      string
  description:  string
  permissions:  string[]
  dependencies: string[]
  run_exists:   boolean
  issues:       string[]
}

export const skillAuditHandler: ToolHandler = {
  name: 'fcp_skill_audit',
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    const skillName = extractSkill(params)
    if (!skillName) return { ok: false, error: 'skill name is required' }

    // Verify presence in index
    if (!await fileExists(ctx.layout.skills.index)) {
      return { ok: false, error: 'skills/index.json not found' }
    }
    let index
    try {
      index = SkillIndexSchema.parse(await readJson(ctx.layout.skills.index))
    } catch {
      return { ok: false, error: 'malformed skills/index.json' }
    }

    const entry = index.skills.find(s => s.name === skillName)
    if (!entry) return { ok: false, error: `skill not in index: ${skillName}` }

    const manifestPath = path.join(ctx.layout.skills.dir, entry.manifest)
    const runPath      = path.join(ctx.layout.skills.lib, skillName, 'run.js')
    const issues: string[] = []

    // Validate manifest
    if (!await fileExists(manifestPath)) {
      return { ok: false, error: `manifest not found: ${manifestPath}` }
    }

    let manifest
    try {
      manifest = SkillManifestSchema.parse(await readJson(manifestPath))
    } catch (e: unknown) {
      return { ok: false, error: `invalid manifest: ${String(e)}` }
    }

    if (manifest.name !== skillName) {
      issues.push(`manifest.name "${manifest.name}" does not match index name "${skillName}"`)
    }
    if (manifest.class !== entry.class) {
      issues.push(`manifest.class "${manifest.class}" does not match index class "${entry.class}"`)
    }

    const runExists = await fileExists(runPath)
    if (!runExists) issues.push('run.js not found')

    const report: AuditReport = {
      name:         manifest.name,
      class:        manifest.class,
      version:      manifest.version,
      description:  manifest.description,
      permissions:  manifest.permissions,
      dependencies: manifest.dependencies,
      run_exists:   runExists,
      issues,
    }

    ctx.logger.info('exec:skill_audit', { name: skillName, issues: issues.length })
    return { ok: true, output: JSON.stringify(report, null, 2) }
  },
}
