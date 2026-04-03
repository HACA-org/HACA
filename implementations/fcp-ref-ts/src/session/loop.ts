// Session loop — main cognitive cycle.
// Iterates: drain inbox → operator prompt → CPE invoke → tool dispatch → heartbeat → repeat.
// EXCEPTION: ~220 lines — tool dispatch and message persistence are tightly coupled
// to the main loop invariant and cannot be split without losing readability.
import * as path from 'node:path'
import * as nodefs from 'node:fs/promises'
import { appendJsonl, readJson, fileExists, ensureDir, writeJson } from '../store/io.js'
import { drainInbox } from './inbox.js'
import { buildContext } from './context.js'
import { estimateTokens, checkBudget } from './budget.js'
import { makeFingerprint } from './fingerprint.js'
import { SESSION_CLOSE_SIGNAL, COMPACT_SESSION_SIGNAL } from '../sil/sil.js'
import { ClosurePayloadSchema } from '../types/formats/memory.js'
import type { SessionOptions, LoopResult, CycleState } from '../types/session.js'
import type { CPEMessage, ToolResultBlock } from '../types/cpe.js'
import type { HeartbeatResult } from '../types/sil.js'

const MAX_TOOL_CYCLES = 50

async function writeOperatorNotification(
  layout: import('../types/store.js').Layout,
  level: 'degraded' | 'critical',
  result: HeartbeatResult,
): Promise<void> {
  await ensureDir(layout.state.operatorNotifications)
  const ts   = new Date().toISOString().replace(/[:.]/g, '-')
  const file = path.join(layout.state.operatorNotifications, `heartbeat-${level}-${ts}.json`)
  const failing = result.vitals.filter(v => !v.ok)
  await writeJson(file, { level, ts: result.ts, cycleCount: result.cycleCount, budgetPct: result.budgetPct, failing })
}

export async function runSessionLoop(opts: SessionOptions): Promise<LoopResult> {
  const { layout, baseline, cpe, policy, tools, logger, io, sessionId, contextMessages, heartbeat } = opts
  const contextWindow = opts.contextWindow > 0 ? opts.contextWindow : baseline.contextWindow.fallbackTokens
  const log = logger.child({ module: 'session', sessionId })

  const toolMap = new Map(tools.map(t => [t.name, t]))
  const firstWriteDone: { value: boolean } = { value: false }
  const execCtx = { layout, baseline, logger, sessionId, sessionMode: 'main' as const, policy, io, firstWriteDone }
  const { system } = await buildContext(layout)

  // MIL/SIL tools bypass the operator gate — they are fundamental to system operation.
  const MIL_SIL_TOOLS = new Set([
    'fcp_memory_recall', 'fcp_memory_write', 'fcp_closure_payload',
    'fcp_evolution_proposal', 'fcp_session_close',
  ])

  const messages: CPEMessage[] = [...(contextMessages ?? [])]
  const fingerprints: string[] = []
  let cycle: CycleState = { cycleNum: 0, inputTokens: 0, fingerprint: '' }
  // Set to true when the SIL compact check fires — prevents re-injection on next cycle.
  let compactRequested = false

  log.info('session:start')

  try {
    while (true) {
      io.emit({ type: 'cycle_start', cycleNum: cycle.cycleNum + 1 })

      // ── Drain async inbox ────────────────────────────────────────────────
      let compactSignalReceived = false
      for (const msg of await drainInbox(layout)) {
        const text = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content)
        if (text === COMPACT_SESSION_SIGNAL) {
          compactSignalReceived = true
          continue
        }
        messages.push(msg)
        await appendJsonl(layout.memory.sessionJsonl, { type: 'message', role: 'user', content: text, ts: new Date().toISOString() })
        io.emit({ type: 'operator_msg', content: text })
      }

      // ── Compact signal: inject CPE instruction ───────────────────────────
      if (compactSignalReceived) {
        const compactInstruction = 'SYSTEM: Context window is critically full. Stop current work and immediately call fcp_closure_payload to save state. The session will be restarted for compaction.'
        messages.push({ role: 'user', content: compactInstruction })
        await appendJsonl(layout.memory.sessionJsonl, { type: 'message', role: 'user', content: compactInstruction, ts: new Date().toISOString() })
        log.warn('session:compact_requested')
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

      // ── Budget check (operator-visible, based on 95% of window) ─────────
      const tokens = cycle.inputTokens > 0 ? cycle.inputTokens : estimateTokens(messages)
      const operatorMax = Math.round(contextWindow * 0.95)
      const budget = checkBudget(tokens, operatorMax, baseline.contextWindow.criticalPct, baseline.contextWindow.warnPct)
      // Emit token update so TUI can display in/out counts and budget %
      io.emit({
        type:         'token_update',
        inputTokens:  tokens,
        outputTokens: 0,   // output tokens only available after CPE response
        budgetPct:    budget.usedPct,
      })
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
          description:  t.description,
          input_schema: t.inputSchema,
        })),
      })
      cycle = {
        cycleNum:    cycle.cycleNum + 1,
        inputTokens: resp.usage.inputTokens,
        fingerprint: makeFingerprint(resp.toolUses),
      }
      io.emit({ type: 'cpe_response', content: resp.content, toolUses: resp.toolUses })
      io.emit({
        type:         'token_update',
        inputTokens:  resp.usage.inputTokens,
        outputTokens: resp.usage.outputTokens,
        budgetPct:    Math.round((resp.usage.inputTokens / operatorMax) * 100),
      })

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
        const handler = toolMap.get(tu.name)
        if (!handler) {
          results.push({ type: 'tool_result', tool_use_id: tu.id, content: `Unknown tool: ${tu.name}` })
          io.emit({ type: 'tool_result', skillName: tu.name, result: { ok: false, error: 'unknown' } })
          continue
        }
        // MIL/SIL tools bypass the operator gate — gate is owned by EXEC tool handlers.
        const approved = MIL_SIL_TOOLS.has(tu.name) ? 'bypass' : 'exec'
        const result = await handler.execute(tu.input, execCtx)
        results.push({ type: 'tool_result', tool_use_id: tu.id, content: result.ok ? result.output : `Error: ${result.error}` })
        io.emit({ type: 'tool_result', skillName: tu.name, result })
        await appendJsonl(layout.memory.sessionJsonl, { type: 'tool_execution', tool: tu.name, approved, ts: new Date().toISOString() })
        if (result.ok && result.output === SESSION_CLOSE_SIGNAL) {
          sessionCloseTriggered = true
        }
      }

      // Push tool results as user message
      messages.push({ role: 'user', content: results })
      await appendJsonl(layout.memory.sessionJsonl, { type: 'message', role: 'user', content: results, ts: new Date().toISOString() })

      if (sessionCloseTriggered) break

      // ── Heartbeat ────────────────────────────────────────────────────────
      if (heartbeat && await heartbeat.shouldRun(cycle.cycleNum)) {
        const hbResult = await heartbeat.run(cycle.cycleNum, cycle.inputTokens, contextWindow)
        const criticals = hbResult.vitals.filter(v => !v.ok && v.severity === 'critical')
        const degraded  = hbResult.vitals.filter(v => !v.ok && v.severity === 'degraded')

        // compact_session check fires at 97% — inject inbox message for next cycle
        const compactVital = criticals.find(v => v.check === 'compact_session')
        if (compactVital && !compactRequested) {
          compactRequested = true
          await ensureDir(layout.io.inbox)
          const ts   = new Date().toISOString().replace(/[:.]/g, '-')
          const file = path.join(layout.io.inbox, `compact-${ts}.json`)
          await writeJson(file, COMPACT_SESSION_SIGNAL)
          const compactMsg = !compactVital.ok ? compactVital.message : ''
          log.warn('session:compact_signal_injected', { pct: compactMsg })
          // Remove compact from criticals list so the other checks still run
          const otherCriticals = criticals.filter(v => v.check !== 'compact_session')
          if (otherCriticals.length > 0) {
            await writeOperatorNotification(layout, 'critical', hbResult)
            io.emit({ type: 'session_close', reason: 'critical_condition' })
            log.warn('session:heartbeat:critical', { vitals: otherCriticals.map(v => v.check) })
            return { closed: 'forced', reason: 'critical_condition' }
          }
        } else if (criticals.length > 0) {
          await writeOperatorNotification(layout, 'critical', hbResult)
          await nodefs.unlink(layout.state.sentinels.sessionToken).catch(() => undefined)
          io.emit({ type: 'session_close', reason: 'critical_condition' })
          log.warn('session:heartbeat:critical', { vitals: criticals.map(v => v.check) })
          return { closed: 'forced', reason: 'critical_condition' }
        }
        if (degraded.length > 0) {
          await writeOperatorNotification(layout, 'degraded', hbResult)
          log.warn('session:heartbeat:degraded', { vitals: degraded.map(v => v.check) })
        }
      }
    }
  } catch (e: unknown) {
    io.emit({ type: 'error', error: e })
    log.error('session:error', { err: String(e) })
    return { closed: 'error', error: e }
  }

  // ── Normal / compact close ───────────────────────────────────────────────
  io.emit({ type: 'session_close', reason: 'normal' })
  log.info('session:close', { cycles: cycle.cycleNum, compact: compactRequested })

  const raw = await fileExists(layout.state.pendingClosure)
    ? await readJson(layout.state.pendingClosure)
    : null
  const parsed = ClosurePayloadSchema.safeParse(raw)
  if (!parsed.success) {
    log.warn('session:no-closure-payload')
    return { closed: 'forced', reason: 'critical_condition' }
  }
  return { closed: 'normal', closurePayload: parsed.data, compact: compactRequested }
}
