import { createHash } from 'node:crypto'
import { existsSync } from 'node:fs'
import { readdir, unlink } from 'node:fs/promises'
import { join } from 'node:path'
import type { Layout } from '../store/layout.js'
import { readJson, writeJson, appendJsonl } from '../store/io.js'
import { runSleepCycle } from './sleep.js'
import type { Logger } from '../logger/logger.js'
import type { CPEAdapter, Message, ToolUseCall, ToolDefinition } from '../cpe/types.js'
import type { BootResult } from '../boot/types.js'
import type { SessionEvent, ToolEvent, ToolEventType } from '../tui/types.js'
import { buildContext } from './context.js'

const MAX_CYCLES = 50

export interface ToolHandler {
  definition: ToolDefinition
  handle(input: Record<string, unknown>): Promise<string>
}

export interface SessionOptions {
  contextWindow: number
  tools?: ToolHandler[]
}

export interface SessionIO {
  readInput(): Promise<string | null>
  onEvent(event: SessionEvent): void
  requestToolApproval?(name: string, input: Record<string, unknown>): Promise<'once' | 'session' | 'allow' | 'deny'>
  onContextWarning?(usedPct: number): void
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
  const text = messages.map(m =>
    typeof m.content === 'string' ? m.content : JSON.stringify(m.content)
  ).join('')
  return Math.ceil(text.length / 4)
}

function makeId(): string {
  return Math.random().toString(36).slice(2, 10)
}

function toolEventType(name: string): ToolEventType {
  if (name === 'fileRead')    return 'fileRead'
  if (name === 'fileWrite')   return 'fileWrite'
  if (name === 'shellRun')    return 'shellRun'
  if (name === 'webFetch')    return 'webFetch'
  if (name === 'memory')      return 'memory'
  if (name === 'workerSkill') return 'workerSkill'
  if (name === 'skillCreate') return 'skillCreate'
  if (name === 'skillAudit')  return 'skillAudit'
  return 'generic'
}

function buildToolEventPatch(name: string, input: Record<string, unknown>, result: string): Partial<ToolEvent> {
  const patch: Partial<ToolEvent> = { status: 'done' }

  if (name === 'fileRead') {
    patch.filePath = String(input['path'] ?? '')
    patch.summary = `${result.split('\n').length} lines`
  } else if (name === 'fileWrite') {
    patch.filePath = String(input['path'] ?? '')
    // result may contain a unified diff if the tool emits one
    if (result.includes('\n@@') || result.startsWith('---')) {
      patch.diff = result
    } else {
      patch.summary = result.slice(0, 80)
    }
  } else if (name === 'webFetch') {
    patch.url = String(input['url'] ?? '')
    const statusMatch = result.match(/^(\d{3})\s/)
    if (statusMatch) patch.httpStatus = parseInt(statusMatch[1]!, 10)
  } else if (name === 'memory') {
    patch.memorySlug = String(input['slug'] ?? '')
    patch.memoryPreview = String(input['content'] ?? '').slice(0, 120)
  } else {
    patch.summary = result.slice(0, 80)
  }

  return patch
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
  io: SessionIO,
): Promise<void> {
  await logger.info('session', 'start', { sessionId: bootResult.sessionId })

  const { systemPrompt, preSessionStimuli } = await buildContext(layout)
  const { warnPct, compactPct } = bootResult.contextWindowConfig

  const messages: Message[] = [...bootResult.history]
  const sessionGrants = new Set<string>()
  const fingerprints: string[] = []

  let cycleCount = 0
  let totalCycles = 0

  // Inject presession stimuli
  if (preSessionStimuli.length > 0) {
    const stimulusText = preSessionStimuli.map(s => JSON.stringify(s)).join('\n')
    messages.push({ role: 'user', content: stimulusText })
    await appendJsonl(layout.sessionStore, { type: 'message', role: 'user', content: stimulusText, ts: new Date().toISOString() })
  }

  // Boot notifications
  if (bootResult.pendingProposals.length > 0) {
    io.onEvent({ type: 'system_message', id: makeId(), text: `${bootResult.pendingProposals.length} evolution proposal(s) pending review.`, ts: new Date().toISOString() })
  }
  if (bootResult.crashRecovered) {
    io.onEvent({ type: 'system_message', id: makeId(), text: 'Session recovered from crash.', ts: new Date().toISOString() })
  }

  // Restore history to TUI
  for (const msg of bootResult.history) {
    const text = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content)
    const role = msg.role === 'user' ? 'user_message' : 'agent_end'
    const id = makeId()
    if (role === 'agent_end') {
      io.onEvent({ type: 'agent_start', id, ts: new Date().toISOString() })
      io.onEvent({ type: 'agent_end', id, text, ts: new Date().toISOString() })
    } else {
      io.onEvent({ type: 'user_message', id, text, ts: new Date().toISOString() })
    }
  }

  const toolDefs = (opts.tools ?? []).map(t => t.definition)
  const toolMap = new Map((opts.tools ?? []).map(t => [t.definition.name, t]))

  while (true) {
    // Drain inbox
    const inboxItems = await drainInbox(layout)
    if (inboxItems.length > 0) {
      const content = inboxItems.join('\n')
      messages.push({ role: 'user', content })
      await appendJsonl(layout.sessionStore, { type: 'message', role: 'user', content, ts: new Date().toISOString() })
      io.onEvent({ type: 'system_message', id: makeId(), text: `[inbox] ${content}`, ts: new Date().toISOString() })
    }

    // Wait for operator input if nothing pending
    if (messages.length === 0 || messages[messages.length - 1]?.role === 'assistant') {
      const input = await io.readInput()
      if (input === null) break

      const trimmed = input.trim()
      if (trimmed === '') continue

      if (trimmed === '/new' || trimmed === '/reset') {
        messages.length = 0
        await appendJsonl(layout.sessionStore, { type: 'session_reset', ts: new Date().toISOString() })
        io.onEvent({ type: 'session_reset' })
        io.onEvent({ type: 'system_message', id: makeId(), text: 'Histórico limpo.', ts: new Date().toISOString() })
        cycleCount = 0
        fingerprints.length = 0
        continue
      }

      messages.push({ role: 'user', content: trimmed })
      await appendJsonl(layout.sessionStore, { type: 'message', role: 'user', content: trimmed, ts: new Date().toISOString() })
    }

    // Context window check
    const usedTokens = estimateTokens(messages)
    const usedPct = usedTokens / opts.contextWindow
    if (usedPct >= compactPct) {
      await logger.warn('session', 'context_compact_threshold', { usedPct: Math.round(usedPct * 100) })
      io.onEvent({ type: 'system_message', id: makeId(), text: `Context window at ${Math.round(usedPct * 100)}%. Compaction required.`, ts: new Date().toISOString() })
    } else if (usedPct >= warnPct) {
      await logger.info('session', 'context_warn_threshold', { usedPct: Math.round(usedPct * 100) })
      io.onContextWarning?.(usedPct)
    }

    // Token update
    io.onEvent({ type: 'tokens_update', input: usedTokens, output: 0, contextWindow: opts.contextWindow })

    // Invoke CPE — emit agent_start, simulate token stream, agent_end
    const agentId = makeId()
    io.onEvent({ type: 'agent_start', id: agentId, ts: new Date().toISOString() })

    const response = await adapter.invoke({
      system: systemPrompt,
      messages,
      ...(toolDefs.length > 0 ? { tools: toolDefs } : {}),
    })

    await logger.increment('cycles')
    totalCycles++
    io.onEvent({ type: 'cycle_update', cycleCount: totalCycles })

    await appendJsonl(layout.sessionStore, {
      type: 'cpe_response',
      ts: new Date().toISOString(),
      stopReason: response.stopReason,
      usage: response.usage,
    })

    // Emit tokens and update token count
    io.onEvent({
      type: 'tokens_update',
      input: response.usage.inputTokens,
      output: response.usage.outputTokens,
      contextWindow: opts.contextWindow,
    })

    if (response.content) {
      // Simulate token streaming: emit chunks of ~8 chars
      const chunkSize = 8
      for (let i = 0; i < response.content.length; i += chunkSize) {
        io.onEvent({ type: 'agent_token', id: agentId, token: response.content.slice(i, i + chunkSize) })
      }
      io.onEvent({ type: 'agent_end', id: agentId, text: response.content, ts: new Date().toISOString() })
      messages.push({ role: 'assistant', content: response.content })
      await appendJsonl(layout.sessionStore, { type: 'message', role: 'assistant', content: response.content, ts: new Date().toISOString() })
    } else {
      io.onEvent({ type: 'agent_end', id: agentId, text: '', ts: new Date().toISOString() })
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
      io.onEvent({ type: 'system_message', id: makeId(), text: 'Maximum cycle limit reached. Stopping tool execution.', ts: new Date().toISOString() })
      break
    }

    const fp = makeFingerprint(response.toolCalls)
    if (fingerprints.includes(fp)) {
      await logger.warn('session', 'loop_detected', { fingerprint: fp })
      io.onEvent({ type: 'system_message', id: makeId(), text: 'Loop detected. Stopping tool execution.', ts: new Date().toISOString() })
      break
    }
    fingerprints.push(fp)

    // Dispatch tool calls
    const toolResults: Array<{ type: 'tool_result'; tool_use_id: string; content: string }> = []

    for (const toolCall of response.toolCalls) {
      const toolEventId = makeId()
      const toolEv: ToolEvent = {
        id: toolEventId,
        type: toolEventType(toolCall.name),
        name: toolCall.name,
        status: 'pending',
        ...(toolCall.name === 'webFetch' ? { url: String(toolCall.input['url'] ?? '') } : {}),
        ...(toolCall.name === 'fileRead' || toolCall.name === 'fileWrite'
          ? { filePath: String(toolCall.input['path'] ?? '') }
          : {}),
      }
      io.onEvent({ type: 'tool_start', entryId: agentId, event: toolEv })

      const handler = toolMap.get(toolCall.name)
      if (!handler) {
        io.onEvent({ type: 'tool_done', entryId: agentId, eventId: toolEventId, patch: { status: 'error', error: `unknown tool: ${toolCall.name}` } })
        toolResults.push({ type: 'tool_result', tool_use_id: toolCall.id, content: `Error: unknown tool ${toolCall.name}` })
        continue
      }

      // Approval check
      let approved = false
      const allowlistData = existsSync(layout.allowlist)
        ? await readJson<{ tools?: string[] }>(layout.allowlist).catch(() => ({ tools: [] }))
        : { tools: [] }
      const persistentAllowed = (allowlistData.tools ?? []).includes(toolCall.name)

      if (persistentAllowed || sessionGrants.has(toolCall.name)) {
        approved = true
      } else if (io.requestToolApproval) {
        io.onEvent({ type: 'tool_done', entryId: agentId, eventId: toolEventId, patch: { status: 'pending' } })
        const decision = await io.requestToolApproval(toolCall.name, toolCall.input)
        if (decision === 'session') { sessionGrants.add(toolCall.name); approved = true }
        else if (decision === 'once' || decision === 'allow') { approved = true }
        if (decision === 'allow') {
          const updated = { tools: [...(allowlistData.tools ?? []), toolCall.name] }
          await writeJson(layout.allowlist, updated)
        }
      }

      if (!approved) {
        io.onEvent({ type: 'tool_done', entryId: agentId, eventId: toolEventId, patch: { status: 'denied' } })
        toolResults.push({ type: 'tool_result', tool_use_id: toolCall.id, content: 'Tool execution denied by operator.' })
        continue
      }

      // Execute
      io.onEvent({ type: 'tool_done', entryId: agentId, eventId: toolEventId, patch: { status: 'running' } })
      try {
        await logger.increment('tool_executions')
        const result = await handler.handle(toolCall.input)
        const patch = buildToolEventPatch(toolCall.name, toolCall.input, result)
        io.onEvent({ type: 'tool_done', entryId: agentId, eventId: toolEventId, patch })
        toolResults.push({ type: 'tool_result', tool_use_id: toolCall.id, content: result })
        await appendJsonl(layout.sessionStore, {
          type: 'tool_execution',
          ts: new Date().toISOString(),
          tool: toolCall.name,
          approved: true,
        })
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : String(err)
        io.onEvent({ type: 'tool_done', entryId: agentId, eventId: toolEventId, patch: { status: 'error', error: errMsg } })
        toolResults.push({ type: 'tool_result', tool_use_id: toolCall.id, content: `Error: ${errMsg}` })
        await logger.error('session', 'tool_error', { tool: toolCall.name, error: errMsg })
      }
    }

    // Persist tool messages
    const toolUseMsg: Message = {
      role: 'assistant',
      content: response.toolCalls.map(tc => ({ type: 'tool_use' as const, id: tc.id, name: tc.name, input: tc.input })),
    }
    const toolResultMsg: Message = { role: 'user', content: toolResults }
    messages.push(toolUseMsg, toolResultMsg)
    await appendJsonl(layout.sessionStore, { type: 'message', role: 'assistant', content: toolUseMsg.content, ts: new Date().toISOString() })
    await appendJsonl(layout.sessionStore, { type: 'message', role: 'user', content: toolResultMsg.content, ts: new Date().toISOString() })
  }

  io.onEvent({ type: 'sleep_start' })
  await runSleepCycle(layout, bootResult.sessionId, messages, logger)
  io.onEvent({ type: 'sleep_done' })
  await logger.info('session', 'end', { sessionId: bootResult.sessionId })
}
