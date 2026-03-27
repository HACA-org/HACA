import { readFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Layout } from '../../store/layout.js'
import type { Logger } from '../../logger/logger.js'
import type { ToolHandler } from '../../session/loop.js'
import type { CPEAdapter, Message } from '../../cpe/types.js'

const MAX_WORKER_CYCLES = 10
const PERSONAS_DIR = join(dirname(fileURLToPath(import.meta.url)), 'worker', 'personas')

const WORKER_CONSTRAINTS = `
## Worker Constraints
- You are a stateless worker agent. You have no memory beyond this conversation.
- Complete the assigned task and return the result. Do not ask clarifying questions.
- You must finish within ${MAX_WORKER_CYCLES} cycles.
- Do not request tools unless explicitly provided.
- When done, respond with your final result and stop.
`.trim()

async function resolvePersona(persona: string): Promise<string> {
  // Try built-in canonical persona first
  const builtinPath = join(PERSONAS_DIR, `${persona}.md`)
  if (existsSync(builtinPath)) {
    const content = await readFile(builtinPath, 'utf8')
    // Strip frontmatter
    return content.replace(/^---[\s\S]*?---\n/, '').trim()
  }
  // Treat as inline persona string
  return persona
}

export function createWorkerSkillTool(
  _layout: Layout,
  logger: Logger,
  adapter: CPEAdapter,
  sessionGrants: Set<string>,
  requestApproval: (prompt: string) => Promise<'once' | 'session' | 'allow' | 'deny'>,
): ToolHandler {
  return {
    definition: {
      name: 'workerSkill',
      description: 'Delegate a task to a stateless worker agent that runs in isolation. Use for heavy analysis, summarization, or text skill execution to avoid polluting the main context.',
      input_schema: {
        type: 'object',
        properties: {
          task: { type: 'string', description: 'The task for the worker to complete' },
          context: { type: 'string', description: 'Relevant content or data the worker needs' },
          persona: { type: 'string', description: 'Worker persona: Summarizer, Analyst, Auditor, Debugger, Reviewer, Coder — or an inline description' },
        },
        required: ['task'],
      },
    },
    async handle(input) {
      const task = String(input['task'] ?? '').trim()
      if (!task) return 'Error: task is required'

      const context = input['context'] ? String(input['context']) : undefined
      const personaArg = input['persona'] ? String(input['persona']) : 'Analyst'

      const grantKey = `workerSkill:${personaArg}`
      if (!sessionGrants.has(grantKey)) {
        const decision = await requestApproval(`workerSkill [${personaArg}]: ${task.slice(0, 80)}`)
        if (decision === 'deny') return 'Worker execution denied by operator.'
        sessionGrants.add(grantKey)
      }

      const personaInstructions = await resolvePersona(personaArg)

      const systemPrompt = [
        personaInstructions,
        WORKER_CONSTRAINTS,
      ].join('\n\n')

      const userContent = context
        ? `## Context\n${context}\n\n## Task\n${task}`
        : `## Task\n${task}`

      const messages: Message[] = [{ role: 'user', content: userContent }]

      await logger.info('exec', 'worker_start', { persona: personaArg, taskLen: task.length })

      let cycles = 0
      let lastContent = ''

      while (cycles < MAX_WORKER_CYCLES) {
        cycles++
        const response = await adapter.invoke({ system: systemPrompt, messages })

        if (response.content) {
          lastContent = response.content
          messages.push({ role: 'assistant', content: response.content })
        }

        if (response.stopReason === 'end_turn' || response.toolCalls.length === 0) break

        // Worker issued tool calls — not supported, treat as end
        await logger.warn('exec', 'worker_unexpected_tool_calls', { cycles })
        break
      }

      await logger.info('exec', 'worker_complete', { cycles, persona: personaArg })

      if (!lastContent) return 'Worker returned no output.'
      if (cycles >= MAX_WORKER_CYCLES) return `[Worker reached cycle limit]\n\n${lastContent}`
      return lastContent
    },
  }
}
