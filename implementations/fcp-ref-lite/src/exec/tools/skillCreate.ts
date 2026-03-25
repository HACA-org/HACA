import { mkdir, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import type { Logger } from '../../logger/logger.js'
import type { ToolHandler } from '../../session/loop.js'
import type { ExecContext } from '../types.js'
import { writeJson } from '../../store/io.js'

const SCRIPT_BOILERPLATE = `#!/usr/bin/env node
// Skill entry point
// Args are passed as JSON string in process.argv[2]
const args = process.argv[2] ? JSON.parse(process.argv[2]) : {}

// TODO: implement skill logic
console.log(JSON.stringify({ result: 'ok', args }))
`

function skillMdTemplate(name: string, description: string, content: string): string {
  return `---
name: ${name}
description: ${description}
---

${content}
`.trimEnd() + '\n'
}

export function createSkillCreateTool(logger: Logger, ctx: ExecContext): ToolHandler {
  return {
    definition: {
      name: 'skillCreate',
      description: 'Scaffold a new skill in the workspace stage (.tmp/<name>/). The entity can then edit the files before proposing installation.',
      input_schema: {
        type: 'object',
        properties: {
          name: { type: 'string', description: 'Skill name (lowercase, hyphens allowed)' },
          execute: { type: 'string', enum: ['text', 'script'], description: 'Execution type: text (SKILL.md via workerSkill) or script (executable entry point)' },
          description: { type: 'string', description: 'Short description of what the skill does' },
          content: { type: 'string', description: 'Initial content for SKILL.md (instructions, guidelines, examples)' },
          entry: { type: 'string', description: 'Entry point filename for script skills (default: run.js)' },
        },
        required: ['name', 'execute', 'description'],
      },
    },
    async handle(input) {
      if (!ctx.workspaceFocus) return 'Error: no workspace focus set. Use /focus <path> to set one.'

      const name = String(input['name'] ?? '').trim().toLowerCase()
      if (!name || !/^[a-z0-9-]+$/.test(name)) {
        return 'Error: skill name must be lowercase letters, numbers, and hyphens only'
      }

      const execute = String(input['execute'] ?? '')
      if (execute !== 'text' && execute !== 'script') {
        return 'Error: execute must be "text" or "script"'
      }

      const description = String(input['description'] ?? '').trim()
      if (!description) return 'Error: description is required'

      const content = input['content'] ? String(input['content']) : `# ${name}\n\nDescribe the skill instructions here.`
      const entry = execute === 'text'
        ? 'SKILL.md'
        : String(input['entry'] ?? 'run.js')

      const stageDir = join(ctx.workspaceFocus, '.tmp', name)

      if (existsSync(stageDir)) {
        return `Error: stage already exists at ${stageDir} — remove it or choose a different name`
      }

      await mkdir(stageDir, { recursive: true })

      // Write manifest.json
      await writeJson(join(stageDir, 'manifest.json'), {
        name,
        description,
        execute,
        entry,
      })

      // Write SKILL.md
      await writeFile(join(stageDir, 'SKILL.md'), skillMdTemplate(name, description, content), 'utf8')

      // Write script boilerplate for script skills
      if (execute === 'script') {
        await writeFile(join(stageDir, entry), SCRIPT_BOILERPLATE, 'utf8')
      }

      await logger.info('exec', 'skill_create', { name, execute, stageDir })

      const files = execute === 'script'
        ? `manifest.json, SKILL.md, ${entry}`
        : 'manifest.json, SKILL.md'

      return `Skill staged at: ${stageDir}\nFiles created: ${files}\nEdit the files, then run skillAudit to validate before proposing installation.`
    },
  }
}
