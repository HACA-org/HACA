import { createHash } from 'node:crypto'
import { existsSync } from 'node:fs'
import { readdir, unlink } from 'node:fs/promises'
import { join } from 'node:path'
import type { Layout } from '../store/layout.js'
import { readJson, writeJson, appendJsonl } from '../store/io.js'
// writeJson used for allowlist persistence
import { runSleepCycle } from './sleep.js'
import type { Logger } from '../logger/logger.js'
import type { CPEAdapter, Message, ToolUseCall, ToolDefinition } from '../cpe/types.js'
import type { BootResult } from '../boot/types.js'
import { buildContext } from './context.js'

const MAX_CYCLES = 50
const CONTEXT_BUDGET_PCT = 0.80

export interface ToolHandler {
  definition: ToolDefinition
  handle(input: Record<string, unknown>): Promise<string>
}

export interface SessionOptions {
  contextWindow: number
  tools?: ToolHandler[]
}

interface CycleFingerprint {
  toolCalls: Array<{ name: string; inputHash: string }>
}

function hashString(s: string): string {
  return createHash('sha256').update(s).digest('hex').slice(0, 16)
}

function makeFingerprint(toolCalls: ToolUseCall[]): string {
  const fp: CycleFingerprint = {
    toolCalls: toolCalls.map(tc => ({
      name: tc.name,
      inputHash: hashString(JSON.stringify(tc.input)),
    })),
  }
  return hashString(JSON.stringify(fp))
}

function estimateTokens(messages: Message[]): number {
  // Rough estimate: 1 token ≈ 4 chars
  const text = messages.map(m =>
    typeof m.content === 'string' ? m.content : JSON.stringify(m.content)
  ).join('')
  return Math.ceil(text.length / 4)
}

function trimHistory(messages: Message[], contextWindow: number): Message[] {
  const budget = Math.floor(contextWindow * CONTEXT_BUDGET_PCT)
  let trimmed = [...messages]
  while (trimmed.length > 2 && estimateTokens(trimmed) > budget) {
    // Remove oldest non-system turn pair (user + assistant)
    trimmed = trimmed.slice(2)
  }
  return trimmed
}

async function drainInbox(layout: Layout): Promise<string[]> {
  if (!existsSync(layout.inbox)) return []
  const files = await readdir(layout.inbox)
  const stimuli: string[] = []
  for (const file of files) {
    if (!file.endsWith('.json')) continue
    const path = join(layout.inbox, file)
    try {
      const data = await readJson<{ message?: string; content?: string }>(path)
      const text = data.message ?? data.content ?? JSON.stringify(data)
      stimuli.push(text)
      await unlink(path)
    } catch {
      // skip malformed
    }
  }
  return stimuli
}


export async function runSessionLoop(
  layout: Layout,
  bootResult: BootResult,
  adapter: CPEAdapter,
  logger: Logger,
  opts: SessionOptions,
  io: {
    readInput(): Promise<string | null>
    writeOutput(text: string): void
    requestToolApproval?(name: string, input: Record<string, unknown>): Promise<'once' | 'session' | 'allow' | 'deny'>
  },
): Promise<void> {
  await logger.info('session', 'start', { sessionId: bootResult.sessionId })

  const { systemPrompt, preSessionStimuli } = await buildContext(layout)
  const messages: Message[] = []
  const sessionGrants = new Set<string>()
  const fingerprints: string[] = []

  // Inject presession stimuli as first user message
  if (preSessionStimuli.length > 0) {
    const stimulusText = preSessionStimuli.map(s => JSON.stringify(s)).join('\n')
    messages.push({ role: 'user', content: stimulusText })
  }

  // Notify pending proposals
  if (bootResult.pendingProposals.length > 0) {
    io.writeOutput(`[FCP] ${bootResult.pendingProposals.length} evolution proposal(s) pending review.`)
  }
  if (bootResult.crashRecovered) {
    io.writeOutput('[FCP] Session recovered from crash.')
  }

  const toolDefs = (opts.tools ?? []).map(t => t.definition)
  const toolMap = new Map((opts.tools ?? []).map(t => [t.definition.name, t]))

  let cycleCount = 0

  while (true) {
    // Drain inbox for async stimuli
    const inboxItems = await drainInbox(layout)
    if (inboxItems.length > 0) {
      messages.push({ role: 'user', content: inboxItems.join('\n') })
    }

    // Read operator input if no pending messages
    if (messages.length === 0 || messages[messages.length - 1]?.role === 'assistant') {
      const input = await io.readInput()
      if (input === null) break // operator closed session
      if (input.trim() === '') continue
      messages.push({ role: 'user', content: input })
      await appendJsonl(layout.sessionStore, { type: 'user_input', ts: new Date().toISOString(), content: input })
    }

    // Trim history to context budget
    const trimmedMessages = trimHistory(messages, opts.contextWindow)

    // Invoke CPE
    const response = await adapter.invoke({
      system: systemPrompt,
      messages: trimmedMessages,
      tools: toolDefs.length > 0 ? toolDefs : undefined,
    })

    await logger.increment('cycles')
    await appendJsonl(layout.sessionStore, {
      type: 'cpe_response',
      ts: new Date().toISOString(),
      stopReason: response.stopReason,
      usage: response.usage,
    })

    if (response.content) {
      messages.push({ role: 'assistant', content: response.content })
      io.writeOutput(response.content)
    }

    if (response.stopReason === 'end_turn' || response.toolCalls.length === 0) {
      cycleCount = 0
      fingerprints.length = 0
      continue
    }

    // Tool use cycle
    cycleCount++
    if (cycleCount >= MAX_CYCLES) {
      await logger.warn('session', 'max_cycles_reached', { cycleCount })
      io.writeOutput('[FCP] Maximum cycle limit reached. Stopping tool execution.')
      break
    }

    // Loop detection
    const fp = makeFingerprint(response.toolCalls)
    if (fingerprints.includes(fp)) {
      await logger.warn('session', 'loop_detected', { fingerprint: fp })
      io.writeOutput('[FCP] Loop detected. Stopping tool execution.')
      break
    }
    fingerprints.push(fp)

    // Dispatch tool calls
    const toolResults: Array<{ type: 'tool_result'; tool_use_id: string; content: string }> = []

    for (const toolCall of response.toolCalls) {
      const handler = toolMap.get(toolCall.name)
      if (!handler) {
        toolResults.push({ type: 'tool_result', tool_use_id: toolCall.id, content: `Error: unknown tool ${toolCall.name}` })
        continue
      }

      // Check approval
      let approved = false
      const allowlistData = existsSync(layout.allowlist)
        ? await readJson<{ tools?: string[] }>(layout.allowlist).catch(() => ({ tools: [] }))
        : { tools: [] }
      const persistentAllowed = (allowlistData.tools ?? []).includes(toolCall.name)

      if (persistentAllowed || sessionGrants.has(toolCall.name)) {
        approved = true
      } else if (io.requestToolApproval) {
        const decision = await io.requestToolApproval(toolCall.name, toolCall.input)
        if (decision === 'session') { sessionGrants.add(toolCall.name); approved = true }
        else if (decision === 'once' || decision === 'allow') { approved = true }
        if (decision === 'allow') {
          // Persist to allowlist
          const updated = { tools: [...(allowlistData.tools ?? []), toolCall.name] }
          await writeJson(layout.allowlist, updated)
        }
      }

      if (!approved) {
        toolResults.push({ type: 'tool_result', tool_use_id: toolCall.id, content: 'Tool execution denied by operator.' })
        continue
      }

      try {
        await logger.increment('tool_executions')
        const result = await handler.handle(toolCall.input)
        toolResults.push({ type: 'tool_result', tool_use_id: toolCall.id, content: result })
        await appendJsonl(layout.sessionStore, {
          type: 'tool_execution',
          ts: new Date().toISOString(),
          tool: toolCall.name,
          approved: true,
        })
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : String(err)
        toolResults.push({ type: 'tool_result', tool_use_id: toolCall.id, content: `Error: ${errMsg}` })
        await logger.error('session', 'tool_error', { tool: toolCall.name, error: errMsg })
      }
    }

    // Add tool use + results to history
    messages.push({
      role: 'assistant',
      content: response.toolCalls.map(tc => ({ type: 'tool_use' as const, id: tc.id, name: tc.name, input: tc.input })),
    })
    messages.push({
      role: 'user',
      content: toolResults,
    })
  }

  await runSleepCycle(layout, bootResult.sessionId, messages, logger)
  await logger.info('session', 'end', { sessionId: bootResult.sessionId })
}
