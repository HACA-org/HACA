// fcp_skill_audit — read and validate a skill's manifest.json and report status.
// Two modes:
//   skill — audits an installed skill by name (must be in skills/index.json)
//   path  — audits a skill directory directly (e.g. workspace:tmp/fcp-stage/<name>)
//           used by CPE to validate a skill before proposing skillInstall
import * as path from 'node:path'
import { fileExists, readJson } from '../../store/io.js'
import { resolveWorkspace } from '../workspace.js'
import { SkillIndexSchema, SkillManifestSchema } from '../../types/formats/skills.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

interface AuditReport {
  name:         string
  class:        string
  execution:    string
  version:      string
  description:  string
  permissions:  string[]
  dependencies: string[]
  run_exists:   boolean
  issues:       string[]
}

// Core audit logic — operates on an absolute skill directory path.
// Does not require the skill to be registered in index.json.
export async function auditSkillDir(
  skillDir:  string,
  skillName: string,
  logger:    import('../../types/logger.js').Logger,
): Promise<{ ok: false; error: string } | { ok: true; report: AuditReport }> {
  const manifestPath = path.join(skillDir, 'manifest.json')

  if (!await fileExists(manifestPath)) {
    return { ok: false, error: `manifest.json not found in: ${skillDir}` }
  }

  let manifest
  try {
    manifest = SkillManifestSchema.parse(await readJson(manifestPath))
  } catch (e: unknown) {
    return { ok: false, error: `invalid manifest.json: ${String(e)}` }
  }

  const issues: string[] = []

  if (manifest.name !== skillName) {
    issues.push(`manifest.name "${manifest.name}" does not match expected "${skillName}"`)
  }

  // execution:script requires run.js; execution:text requires SKILL.md or EXECUTE.md
  let runExists = false
  if (manifest.execution === 'text') {
    const hasSKILL  = await fileExists(path.join(skillDir, 'SKILL.md'))
    const hasEXECUTE = await fileExists(path.join(skillDir, 'EXECUTE.md'))
    runExists = hasSKILL || hasEXECUTE
    if (!runExists) issues.push('text-execution skill requires SKILL.md or EXECUTE.md')
  } else {
    runExists = await fileExists(path.join(skillDir, 'run.js'))
    if (!runExists) issues.push('run.js not found')
  }

  const report: AuditReport = {
    name:         manifest.name,
    class:        manifest.class,
    execution:    manifest.execution,
    version:      manifest.version,
    description:  manifest.description,
    permissions:  manifest.permissions,
    dependencies: manifest.dependencies,
    run_exists:   runExists,
    issues,
  }

  logger.info('exec:skill_audit', { name: skillName, issues: issues.length })
  return { ok: true, report }
}

export const skillAuditHandler: ToolHandler = {
  name: 'fcp_skill_audit',
  description: 'Validate a skill and report its status, permissions, and issues. Use skill to audit an installed skill by name, or path to audit a skill directory directly (e.g. a staged skill before proposing skillInstall).',
  inputSchema: {
    type: 'object',
    properties: {
      skill: { type: 'string', description: 'Skill name as registered in skills/index.json. Mutually exclusive with path.' },
      path:  { type: 'string', description: 'Absolute or workspace-relative path to a skill directory to audit directly. Mutually exclusive with skill.' },
    },
  },
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    if (typeof params !== 'object' || params === null) {
      return { ok: false, error: 'skill or path is required' }
    }
    const p = params as Record<string, unknown>
    const skillParam = typeof p['skill'] === 'string' ? p['skill'].trim() : null
    const pathParam  = typeof p['path']  === 'string' ? p['path'].trim()  : null

    if (!skillParam && !pathParam) return { ok: false, error: 'skill or path is required' }
    if (skillParam && pathParam)   return { ok: false, error: 'skill and path are mutually exclusive' }

    if (pathParam) {
      // path mode — audit arbitrary directory
      const workspace = await resolveWorkspace(ctx)
      if (!workspace) return { ok: false, error: 'workspace_focus is not set' }

      const absDir   = path.isAbsolute(pathParam) ? pathParam : path.join(workspace, pathParam)
      const skillName = path.basename(absDir)
      const result   = await auditSkillDir(absDir, skillName, ctx.logger)
      if (!result.ok) return result
      return { ok: true, output: JSON.stringify(result.report, null, 2) }
    }

    // skill mode — audit installed skill by name
    if (!await fileExists(ctx.layout.skills.index)) {
      return { ok: false, error: 'skills/index.json not found' }
    }
    let index
    try {
      index = SkillIndexSchema.parse(await readJson(ctx.layout.skills.index))
    } catch {
      return { ok: false, error: 'malformed skills/index.json' }
    }

    const entry = index.skills.find(s => s.name === skillParam!)
    if (!entry) return { ok: false, error: `skill not in index: ${skillParam}` }

    const skillDir = path.join(ctx.layout.skills.dir, skillParam!)
    const result   = await auditSkillDir(skillDir, skillParam!, ctx.logger)
    if (!result.ok) return result

    // Cross-check index consistency
    const issues = [...result.report.issues]
    if (result.report.class !== entry.class) {
      issues.push(`manifest.class "${result.report.class}" does not match index class "${entry.class}"`)
    }

    return { ok: true, output: JSON.stringify({ ...result.report, issues }, null, 2) }
  },
}
