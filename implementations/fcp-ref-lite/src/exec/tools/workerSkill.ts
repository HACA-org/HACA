import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import type { Layout } from '../../store/layout.js'
import type { Logger } from '../../logger/logger.js'
import type { ToolHandler } from '../../session/loop.js'
import { readJson } from '../../store/io.js'

const TIMEOUT_MS = 60_000

interface SkillManifest {
  name: string
  entry: string
  description?: string
}

export function createWorkerSkillTool(
  layout: Layout,
  logger: Logger,
  sessionGrants: Set<string>,
  requestApproval: (prompt: string) => Promise<'once' | 'session' | 'allow' | 'deny'>,
): ToolHandler {
  return {
    definition: {
      name: 'workerSkill',
      description: 'Execute a custom skill as a subprocess. Requires operator approval (session-scoped only).',
      input_schema: {
        type: 'object',
        properties: {
          skill: { type: 'string', description: 'Skill name (must exist in skills/)' },
          args: { type: 'object', description: 'Arguments to pass to the skill as JSON' },
        },
        required: ['skill'],
      },
    },
    async handle(input) {
      const skillName = String(input['skill'] ?? '').trim()
      if (!skillName) return 'Error: skill name is required'

      const manifestPath = layout.skillManifest(skillName)
      if (!existsSync(manifestPath)) return `Error: skill not found: ${skillName}`

      let manifest: SkillManifest
      try {
        manifest = await readJson<SkillManifest>(manifestPath)
      } catch {
        return `Error: invalid manifest for skill: ${skillName}`
      }

      const grantKey = `workerSkill:${skillName}`
      if (!sessionGrants.has(grantKey)) {
        const decision = await requestApproval(`workerSkill: ${skillName}`)
        if (decision === 'deny') return 'Execution denied by operator.'
        // session-scoped only — never persists to allowlist
        sessionGrants.add(grantKey)
      }

      const entryPath = layout.skill(skillName) + '/' + manifest.entry
      if (!existsSync(entryPath)) return `Error: skill entry not found: ${entryPath}`

      const args = input['args'] ? JSON.stringify(input['args']) : '{}'

      return new Promise(resolve => {
        const child = spawn('node', [entryPath, args], {
          cwd: layout.skill(skillName),
          timeout: TIMEOUT_MS,
          stdio: ['ignore', 'pipe', 'pipe'],
        })

        const out: string[] = []
        const err: string[] = []
        child.stdout?.on('data', (d: Buffer) => out.push(d.toString()))
        child.stderr?.on('data', (d: Buffer) => err.push(d.toString()))

        child.on('close', async (code) => {
          await logger.info('exec', 'worker_skill', { skill: skillName, code })
          const stdout = out.join('').trim()
          const stderr = err.join('').trim()
          const result = [stdout, stderr ? `stderr: ${stderr}` : ''].filter(Boolean).join('\n')
          resolve(result || `(exited with code ${code})`)
        })

        child.on('error', async (e) => {
          await logger.error('exec', 'worker_skill_error', { skill: skillName, error: e.message })
          resolve(`Error: ${e.message}`)
        })
      })
    },
  }
}
