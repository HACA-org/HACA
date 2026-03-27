import { existsSync } from 'node:fs'
import { access, constants } from 'node:fs/promises'
import { join } from 'node:path'
import type { Logger } from '../../logger/logger.js'
import type { ToolHandler } from '../../session/loop.js'
import { readJson } from '../../store/io.js'

interface SkillManifest {
  name?: unknown
  description?: unknown
  execute?: unknown
  entry?: unknown
}

interface AuditFinding {
  severity: 'CRITICAL' | 'WARNING' | 'INFO'
  location: string
  message: string
}

export interface SkillAuditResult {
  path: string
  verdict: 'PASS' | 'FAIL'
  findings: AuditFinding[]
}

async function isExecutable(path: string): Promise<boolean> {
  try {
    await access(path, constants.X_OK)
    return true
  } catch {
    return false
  }
}

export async function auditSkillPath(skillPath: string): Promise<SkillAuditResult> {
  const findings: AuditFinding[] = []

  // Check manifest exists
  const manifestPath = join(skillPath, 'manifest.json')
  if (!existsSync(manifestPath)) {
    findings.push({ severity: 'CRITICAL', location: 'manifest.json', message: 'manifest.json not found' })
    return { path: skillPath, verdict: 'FAIL', findings }
  }

  // Parse manifest
  let manifest: SkillManifest
  try {
    manifest = await readJson<SkillManifest>(manifestPath)
  } catch {
    findings.push({ severity: 'CRITICAL', location: 'manifest.json', message: 'manifest.json is invalid JSON' })
    return { path: skillPath, verdict: 'FAIL', findings }
  }

  // Validate required fields
  if (!manifest.name || typeof manifest.name !== 'string') {
    findings.push({ severity: 'CRITICAL', location: 'manifest.json', message: 'missing or invalid "name" field' })
  }
  if (!manifest.description || typeof manifest.description !== 'string') {
    findings.push({ severity: 'WARNING', location: 'manifest.json', message: 'missing or invalid "description" field' })
  }
  if (manifest.execute !== 'text' && manifest.execute !== 'script') {
    findings.push({ severity: 'CRITICAL', location: 'manifest.json', message: `"execute" must be "text" or "script", got: ${JSON.stringify(manifest.execute)}` })
  }
  if (!manifest.entry || typeof manifest.entry !== 'string') {
    findings.push({ severity: 'CRITICAL', location: 'manifest.json', message: 'missing or invalid "entry" field' })
  }

  // Check SKILL.md exists
  if (!existsSync(join(skillPath, 'SKILL.md'))) {
    findings.push({ severity: 'CRITICAL', location: 'SKILL.md', message: 'SKILL.md not found' })
  }

  // Check entry file exists
  if (manifest.entry && typeof manifest.entry === 'string') {
    const entryPath = join(skillPath, manifest.entry)
    if (!existsSync(entryPath)) {
      findings.push({ severity: 'CRITICAL', location: manifest.entry, message: `entry file not found: ${manifest.entry}` })
    } else if (manifest.execute === 'script') {
      const executable = await isExecutable(entryPath)
      if (!executable) {
        findings.push({ severity: 'WARNING', location: manifest.entry, message: 'entry file is not executable (chmod +x may be needed)' })
      }
    }
  }

  const critical = findings.filter(f => f.severity === 'CRITICAL').length
  const verdict: 'PASS' | 'FAIL' = critical > 0 ? 'FAIL' : 'PASS'

  return { path: skillPath, verdict, findings }
}

function formatAuditResult(result: SkillAuditResult): string {
  const critical = result.findings.filter(f => f.severity === 'CRITICAL').length
  const warnings = result.findings.filter(f => f.severity === 'WARNING').length
  const info = result.findings.filter(f => f.severity === 'INFO').length

  const lines: string[] = [
    `SKILL AUDIT: ${result.path}`,
    '='.repeat(40),
    `CRITICAL: ${critical}  WARNING: ${warnings}  INFO: ${info}`,
    '',
  ]

  for (const f of result.findings) {
    lines.push(`[${f.severity}] ${f.location} — ${f.message}`)
  }

  if (result.findings.length === 0) {
    lines.push('No issues found.')
  }

  lines.push('')
  lines.push(`VERDICT: ${result.verdict}`)

  return lines.join('\n')
}

export function createSkillAuditTool(logger: Logger): ToolHandler {
  return {
    definition: {
      name: 'skillAudit',
      description: 'Audit a skill directory for structural integrity. Use on staged skills before proposing installation, or on installed skills for health checks.',
      input_schema: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'Absolute path to the skill directory (stage or installed)' },
        },
        required: ['path'],
      },
    },
    async handle(input) {
      const skillPath = String(input['path'] ?? '').trim()
      if (!skillPath) return 'Error: path is required'

      if (!existsSync(skillPath)) return `Error: path not found: ${skillPath}`

      await logger.info('exec', 'skill_audit', { path: skillPath })
      const result = await auditSkillPath(skillPath)
      return formatAuditResult(result)
    },
  }
}
