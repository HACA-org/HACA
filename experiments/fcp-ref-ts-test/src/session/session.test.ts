import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mkdtemp, rm, mkdir, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createLayout } from '../store/layout.js'
import { writeJson, touchFile } from '../store/io.js'
import { createLogger } from '../logger/logger.js'
import { buildContext } from './context.js'
import { runSessionLoop } from './loop.js'
import type { SessionIO } from './loop.js'
import type { CPEAdapter, CPEResponse } from '../cpe/types.js'
import type { BootResult } from '../boot/types.js'
import type { Layout } from '../store/layout.js'
import type { SessionEvent } from '../tui/types.js'

async function makeFixture(tmp: string): Promise<Layout> {
  const root = join(tmp, 'entity')
  const layout = createLayout(root)
  await mkdir(join(root, 'persona'), { recursive: true })
  await mkdir(join(root, 'state'), { recursive: true })
  await mkdir(join(root, 'io', 'inbox', 'presession'), { recursive: true })
  await mkdir(join(root, 'io', 'inbox'), { recursive: true })
  await mkdir(join(root, 'io', 'notifications'), { recursive: true })
  await mkdir(join(root, 'memory'), { recursive: true })
  await mkdir(join(root, 'memory', 'episodic'), { recursive: true })
  await mkdir(join(root, 'memory', 'semantic'), { recursive: true })
  await writeFile(join(root, 'BOOT.md'), '# Custom Instructions\nBe helpful.', 'utf8')
  await writeFile(join(root, 'persona', 'identity.md'), '# Identity\nI am an AI assistant.', 'utf8')
  await writeFile(join(root, 'persona', 'values.md'), '# Values\nHonesty first.', 'utf8')
  await writeJson(layout.baseline, { cpe: { topology: 'transparent' }, haca_profile: 'haca-core' })
  await touchFile(layout.sessionToken)
  return layout
}

const mockBootResult: BootResult = {
  sessionId: 'test-session-id',
  isFirstBoot: false,
  crashRecovered: false,
  pendingProposals: [],
  history: [],
  contextWindowConfig: { warnPct: 0.90, compactPct: 0.95 },
}

/** Collect agent text from onEvent stream */
function collectText(events: SessionEvent[]): string[] {
  return events
    .filter((e): e is Extract<SessionEvent, { type: 'agent_end' }> => e.type === 'agent_end')
    .map(e => e.text)
    .filter(Boolean)
}

/** Collect system messages from onEvent stream */
function collectSystem(events: SessionEvent[]): string[] {
  return events
    .filter((e): e is Extract<SessionEvent, { type: 'system_message' }> => e.type === 'system_message')
    .map(e => e.text)
}

function makeIO(
  inputs: Array<string | null>,
  overrides: Partial<SessionIO> = {},
): SessionIO & { events: SessionEvent[] } {
  let idx = 0
  const events: SessionEvent[] = []
  return {
    readInput: async () => inputs[idx++] ?? null,
    onEvent: (e) => events.push(e),
    ...overrides,
    events,
  }
}

describe('buildContext', () => {
  let tmp: string

  beforeEach(async () => { tmp = await mkdtemp(join(tmpdir(), 'fcp-ctx-')) })
  afterEach(async () => { await rm(tmp, { recursive: true, force: true }) })

  it('builds system prompt from persona files and BOOT.md', async () => {
    const layout = await makeFixture(tmp)
    const ctx = await buildContext(layout)
    expect(ctx.systemPrompt).toContain('Identity')
    expect(ctx.systemPrompt).toContain('Values')
    expect(ctx.systemPrompt).toContain('Custom Instructions')
  })

  it('includes persona files in alphabetical order', async () => {
    const layout = await makeFixture(tmp)
    const ctx = await buildContext(layout)
    const idxIdentity = ctx.systemPrompt.indexOf('identity')
    const idxValues = ctx.systemPrompt.indexOf('values')
    expect(idxIdentity).toBeLessThan(idxValues)
  })

  it('includes working memory entries when present', async () => {
    const layout = await makeFixture(tmp)
    await writeJson(layout.workingMemory, { entries: [{ content: 'Remember: user prefers brevity' }] })
    const ctx = await buildContext(layout)
    expect(ctx.systemPrompt).toContain('Remember: user prefers brevity')
  })

  it('drains presession stimuli', async () => {
    const layout = await makeFixture(tmp)
    await writeJson(join(layout.inboxPresession, 'stim-1.json'), { message: 'Hello from gateway' })
    const ctx = await buildContext(layout)
    expect(ctx.preSessionStimuli).toHaveLength(1)
  })

  it('returns empty systemPrompt sections gracefully when files are missing', async () => {
    const root = join(tmp, 'empty-entity')
    const layout = createLayout(root)
    await mkdir(join(root, 'persona'), { recursive: true })
    await mkdir(join(root, 'io', 'inbox', 'presession'), { recursive: true })
    const ctx = await buildContext(layout)
    expect(ctx.systemPrompt).toBe('')
    expect(ctx.preSessionStimuli).toEqual([])
  })
})

describe('runSessionLoop', () => {
  let tmp: string

  beforeEach(async () => { tmp = await mkdtemp(join(tmpdir(), 'fcp-loop-')) })
  afterEach(async () => { await rm(tmp, { recursive: true, force: true }) })

  function makeAdapter(responses: Partial<CPEResponse>[]): CPEAdapter {
    let i = 0
    return {
      provider: 'mock',
      invoke: vi.fn().mockImplementation(async () => {
        const r = responses[i++] ?? responses[responses.length - 1]!
        return {
          content: r.content ?? null,
          toolCalls: r.toolCalls ?? [],
          usage: r.usage ?? { inputTokens: 10, outputTokens: 5 },
          stopReason: r.stopReason ?? 'end_turn',
        } satisfies CPEResponse
      }),
    }
  }

  it('runs a single exchange and closes on null input', async () => {
    const layout = await makeFixture(tmp)
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const adapter = makeAdapter([{ content: 'Hello there!', stopReason: 'end_turn' }])
    const io = makeIO(['Hello', null])

    await runSessionLoop(layout, mockBootResult, adapter, logger, { contextWindow: 100000 }, io)

    expect(collectText(io.events)).toContain('Hello there!')
  })

  it('removes session token after sleep cycle', async () => {
    const { existsSync } = await import('node:fs')
    const layout = await makeFixture(tmp)
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const adapter = makeAdapter([{ content: 'Bye!', stopReason: 'end_turn' }])
    const io = makeIO(['Hi', null])

    await runSessionLoop(layout, mockBootResult, adapter, logger, { contextWindow: 100000 }, io)

    expect(existsSync(layout.sessionToken)).toBe(false)
  })

  it('executes approved tool calls', async () => {
    const layout = await makeFixture(tmp)
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const toolHandler = vi.fn().mockResolvedValue('tool result')
    const adapter = makeAdapter([
      { toolCalls: [{ id: 't1', name: 'test_tool', input: { x: 1 } }], stopReason: 'tool_use' },
      { content: 'Done!', stopReason: 'end_turn' },
    ])
    const io = makeIO(['Run the tool', null], {
      requestToolApproval: async () => 'once',
    })

    await runSessionLoop(layout, mockBootResult, adapter, logger, {
      contextWindow: 100000,
      tools: [{
        definition: { name: 'test_tool', description: 'test', input_schema: {} },
        handle: toolHandler,
      }],
    }, io)

    expect(toolHandler).toHaveBeenCalledWith({ x: 1 })
    const counters = await logger.getCounters()
    expect(counters['tool_executions']).toBe(1)
  })

  it('denies tool call when operator denies', async () => {
    const layout = await makeFixture(tmp)
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const toolHandler = vi.fn().mockResolvedValue('should not run')
    const adapter = makeAdapter([
      { toolCalls: [{ id: 't1', name: 'test_tool', input: {} }], stopReason: 'tool_use' },
      { content: 'Ok', stopReason: 'end_turn' },
    ])
    const io = makeIO(['go', null], {
      requestToolApproval: async () => 'deny',
    })

    await runSessionLoop(layout, mockBootResult, adapter, logger, {
      contextWindow: 100000,
      tools: [{
        definition: { name: 'test_tool', description: 'test', input_schema: {} },
        handle: toolHandler,
      }],
    }, io)

    expect(toolHandler).not.toHaveBeenCalled()
  })

  it('stops on loop detection', async () => {
    const layout = await makeFixture(tmp)
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const toolHandler = vi.fn().mockResolvedValue('result')
    const repeatedResponse = {
      toolCalls: [{ id: 't1', name: 'test_tool', input: { x: 1 } }],
      stopReason: 'tool_use' as const,
    }
    const adapter = makeAdapter([repeatedResponse, repeatedResponse, repeatedResponse])
    const io = makeIO(['go', null], {
      requestToolApproval: async () => 'once',
    })

    await runSessionLoop(layout, mockBootResult, adapter, logger, {
      contextWindow: 100000,
      tools: [{
        definition: { name: 'test_tool', description: 'test', input_schema: {} },
        handle: toolHandler,
      }],
    }, io)

    expect(collectSystem(io.events).some(t => t.includes('Loop detected'))).toBe(true)
  })

  it('notifies operator of crash recovery', async () => {
    const layout = await makeFixture(tmp)
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const adapter = makeAdapter([{ content: 'ok', stopReason: 'end_turn' }])
    const io = makeIO(['hi', null])

    await runSessionLoop(layout,
      { ...mockBootResult, crashRecovered: true },
      adapter, logger, { contextWindow: 100000 }, io)

    expect(collectSystem(io.events).some(t => t.includes('recovered from crash'))).toBe(true)
  })

  it('processes closure via MIL on normal session end (no pending-closure.json left)', async () => {
    const { existsSync } = await import('node:fs')
    const layout = await makeFixture(tmp)
    const logger = createLogger(join(tmp, 'entity.log'), join(tmp, 'counters.json'))
    const adapter = makeAdapter([{ content: 'Bye', stopReason: 'end_turn' }])
    const io = makeIO(['hi', null])

    await runSessionLoop(layout, mockBootResult, adapter, logger, { contextWindow: 100000 }, io)

    expect(existsSync(layout.pendingClosure)).toBe(false)
  })
})
