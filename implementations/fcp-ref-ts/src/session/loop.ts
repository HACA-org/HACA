// Session loop — main cognitive cycle.
// Iterates: drain inbox → operator prompt → CPE invoke → tool dispatch → repeat.
// EXCEPTION: ~170 lines — tool dispatch and message persistence are tightly coupled
// to the main loop invariant and cannot be split without losing readability.
import { appendJsonl, readJson, fileExists } from '../store/io.js'
import { drainInbox } from './inbox.js'
import { buildContext } from './context.js'
import { estimateTokens, checkBudget } from './budget.js'
import { makeFingerprint } from './fingerprint.js'
import { resolveToolApproval } from './approval.js'
import { SESSION_CLOSE_SIGNAL } from '../sil/sil.js'
import { ClosurePayloadSchema } from '../types/formats/memory.js'
import type { SessionOptions, LoopResult, CycleState } from '../types/session.js'
import type { CPEMessage, ToolResultBlock } from '../types/cpe.js'

const MAX_TOOL_CYCLES = 50

export async function runSessionLoop(opts: SessionOptions): Promise<LoopResult> {
  const { layout, baseline, cpe, policy, tools, logger, io, sessionId, contextMessages } = opts
  const log = logger.child({ module: 'session', sessionId })

  const toolMap = new Map(tools.map(t => [t.name, t]))
  const execCtx = { layout, baseline, logger, sessionId }
  const { system } = await buildContext(layout)

  const messages: CPEMessage[] = [...(contextMessages ?? [])]
  const fingerprints: string[] = []
  let cycle: CycleState = { cycleNum: 0, inputTokens: 0, fingerprint: '' }

  log.info('session:start')

  try {
    while (true) {
      // ── Drain async inbox ────────────────────────────────────────────────
      for (const msg of await drainInbox(layout)) {
        messages.push(msg)
        const text = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content)
        await appendJsonl(layout.memory.sessionJsonl, { type: 'message', role: 'user', content: text, ts: new Date().toISOString() })
        io.emit({ type: 'operator_msg', content: text })
      }

      // ── Operator input (when idle) ───────────────────────────────────────
      const lastRole = messages.at(-1)?.role
      if (messages.length === 0 || lastRole === 'assistant') {
        const text = await io.prompt()
        const trimmed = text.trim()
        if (!trimmed) continue

        messages.push({ role: 'user', content: trimmed })
        await appendJsonl(layout.memory.sessionJsonl, { type: 'message', role: 'user', content: trimmed, ts: new Date().toISOString() })
        io.emit({ type: 'operator_msg', content: trimmed })
      }

      // ── Budget check ─────────────────────────────────────────────────────
      const tokens = cycle.inputTokens > 0 ? cycle.inputTokens : estimateTokens(messages)
      const budget = checkBudget(tokens, baseline.contextWindow.budgetTokens, baseline.contextWindow.criticalPct)
      if (budget.status === 'critical') {
        io.emit({ type: 'session_close', reason: 'budget_critical' })
        return { closed: 'forced', reason: 'budget_critical' }
      }

      // ── CPE invoke ───────────────────────────────────────────────────────
      io.emit({ type: 'cpe_invoke' })
      const resp = await cpe.invoke({
        system,
        messages,
        tools: tools.map(t => ({
          name:         t.name,
          description:  t.name,
          input_schema: {},
        })),
      })
      cycle = {
        cycleNum:    cycle.cycleNum + 1,
        inputTokens: resp.usage.inputTokens,
        fingerprint: makeFingerprint(resp.toolUses),
      }
      io.emit({ type: 'cpe_response', content: resp.content, toolUses: resp.toolUses })

      // ── End turn — push assistant message, wait for operator ─────────────
      if (resp.stopReason === 'end_turn' || resp.toolUses.length === 0) {
        messages.push({ role: 'assistant', content: resp.content })
        await appendJsonl(layout.memory.sessionJsonl, { type: 'message', role: 'assistant', content: resp.content, ts: new Date().toISOString() })
        fingerprints.length = 0
        continue
      }

      // ── Tool cycle ───────────────────────────────────────────────────────
      if (cycle.cycleNum >= MAX_TOOL_CYCLES) {
        log.warn('session:max-cycles', { cycleNum: cycle.cycleNum })
        return { closed: 'forced', reason: 'critical_condition' }
      }
      if (fingerprints.includes(cycle.fingerprint)) {
        log.warn('session:loop-detected', { fingerprint: cycle.fingerprint })
        return { closed: 'forced', reason: 'critical_condition' }
      }
      fingerprints.push(cycle.fingerprint)

      // Push assistant tool-use block
      messages.push({ role: 'assistant', content: resp.toolUses })
      await appendJsonl(layout.memory.sessionJsonl, { type: 'message', role: 'assistant', content: resp.toolUses, ts: new Date().toISOString() })

      // Dispatch each tool use
      const results: ToolResultBlock[] = []
      let sessionCloseTriggered = false
      for (const tu of resp.toolUses) {
        io.emit({ type: 'tool_dispatch', skillName: tu.name, input: tu.input })
        const decision = await resolveToolApproval(tu.name, tu.input, policy, io)
        if (!decision.granted) {
          results.push({ type: 'tool_result', tool_use_id: tu.id, content: 'Denied by operator.' })
          io.emit({ type: 'tool_result', skillName: tu.name, result: { ok: false, error: 'denied' } })
          continue
        }
        const handler = toolMap.get(tu.name)
        if (!handler) {
          results.push({ type: 'tool_result', tool_use_id: tu.id, content: `Unknown tool: ${tu.name}` })
          io.emit({ type: 'tool_result', skillName: tu.name, result: { ok: false, error: 'unknown' } })
          continue
        }
        const result = await handler.execute(tu.input, execCtx)
        results.push({ type: 'tool_result', tool_use_id: tu.id, content: result.ok ? result.output : `Error: ${result.error}` })
        io.emit({ type: 'tool_result', skillName: tu.name, result })
        await appendJsonl(layout.memory.sessionJsonl, { type: 'tool_execution', tool: tu.name, approved: decision.tier, ts: new Date().toISOString() })
        if (result.ok && result.output === SESSION_CLOSE_SIGNAL) {
          sessionCloseTriggered = true
        }
      }

      // Push tool results as user message
      messages.push({ role: 'user', content: results })
      await appendJsonl(layout.memory.sessionJsonl, { type: 'message', role: 'user', content: results, ts: new Date().toISOString() })

      if (sessionCloseTriggered) break
    }
  } catch (e: unknown) {
    io.emit({ type: 'error', error: e })
    log.error('session:error', { err: String(e) })
    return { closed: 'error', error: e }
  }

  // ── Normal close ─────────────────────────────────────────────────────────
  io.emit({ type: 'session_close', reason: 'normal' })
  log.info('session:close', { cycles: cycle.cycleNum })

  const raw = await fileExists(layout.state.pendingClosure)
    ? await readJson(layout.state.pendingClosure)
    : null
  const parsed = ClosurePayloadSchema.safeParse(raw)
  if (!parsed.success) {
    log.warn('session:no-closure-payload')
    return { closed: 'forced', reason: 'critical_condition' }
  }
  return { closed: 'normal', closurePayload: parsed.data }
}
