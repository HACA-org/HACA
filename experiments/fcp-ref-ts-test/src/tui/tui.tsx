import { render } from 'ink'
import { App, makeInitialState } from './App.js'
import type { AppState } from './App.js'
import type { SessionEvent, AllowDecision, AllowlistPrompt } from './types.js'
import type { BootResult } from '../boot/types.js'
import type { CPEAdapter } from '../cpe/types.js'
import type { Layout } from '../store/layout.js'
import type { Logger } from '../logger/logger.js'
import { runSessionLoop } from '../session/loop.js'
import type { SessionOptions, SessionIO } from '../session/loop.js'

export interface TuiOptions {
  layout: Layout
  bootResult: BootResult
  adapter: CPEAdapter
  logger: Logger
  sessionOpts: SessionOptions
  model: string
  provider: string
  workspaceFocus: string | null
  verbose?: boolean
  debug?: boolean
  version?: string
  onToolLevelApproval?: (fn: (name: string, input: Record<string, unknown>) => Promise<'once' | 'session' | 'allow' | 'deny'>) => void
}

export async function startTui(opts: TuiOptions): Promise<void> {
  const {
    layout, bootResult, adapter, logger, sessionOpts,
    model, provider, workspaceFocus,
    verbose = false, debug = false, version = '0.1.0',
    onToolLevelApproval,
  } = opts

  // Read profile from imprint (source of truth)
  let profile: 'haca-core' | 'haca-evolve' = 'haca-core'
  try {
    const { readJson } = await import('../store/io.js')
    const { existsSync } = await import('node:fs')
    if (existsSync(layout.imprint)) {
      const imp = await readJson<{ hacaProfile?: 'haca-core' | 'haca-evolve' }>(layout.imprint)
      if (imp.hacaProfile) profile = imp.hacaProfile
    }
  } catch { /* default to haca-core */ }

  const initial: AppState = makeInitialState({
    sessionId: bootResult.sessionId,
    profile, version, verbose, debug,
    model, provider,
    contextWindow: sessionOpts.contextWindow,
    workspaceFocus,
  })

  // ── Event/input bridges ───────────────────────────────────────────────────
  let dispatchEvent: ((e: SessionEvent) => void) | null = null
  let setAllowlistFn: ((p: AllowlistPrompt | null) => void) | null = null
  const inputQueue: Array<string | null> = []
  let inputResolve: ((v: string | null) => void) | null = null

  // Ready gate: resolves when onReady fires (React first render complete)
  let resolveReady!: () => void
  const readyGate = new Promise<void>(r => { resolveReady = r })

  function pushInput(text: string | null) {
    if (inputResolve) {
      const r = inputResolve
      inputResolve = null
      r(text)
    } else {
      inputQueue.push(text)
    }
  }

  function promptApproval(name: string, input: Record<string, unknown>): Promise<'once' | 'session' | 'allow' | 'deny'> {
    return new Promise(resolve => {
      const prompt: AllowlistPrompt = {
        toolName: name,
        toolInput: input,
        resolve: (decision: AllowDecision) => {
          setAllowlistFn?.(null)
          resolve(decision === 'persist' ? 'allow' : decision as 'once' | 'session' | 'deny')
        },
      }
      setAllowlistFn?.(prompt)
    })
  }

  // Wire up tool-level approval from exec handlers
  onToolLevelApproval?.((name, input) => promptApproval(name, input))

  // ── SessionIO: interface consumed by the session loop ─────────────────────
  const io: SessionIO = {
    readInput(): Promise<string | null> {
      return new Promise(resolve => {
        if (inputQueue.length > 0) resolve(inputQueue.shift()!)
        else inputResolve = resolve
      })
    },

    onEvent(event: SessionEvent) {
      dispatchEvent?.(event)
    },

    requestToolApproval(name, input) {
      return promptApproval(name, input)
    },

    onContextWarning(usedPct) {
      dispatchEvent?.({
        type: 'system_message',
        id: `ctx-warn-${Date.now()}`,
        text: `⚠ context window at ${Math.round(usedPct * 100)}%`,
        ts: new Date().toISOString(),
      })
    },
  }

  // ── Render ────────────────────────────────────────────────────────────────
  const { unmount, waitUntilExit } = render(
    <App
      initial={initial}
      onReady={(dispatch, setAllowlist) => {
        dispatchEvent  = dispatch
        setAllowlistFn = setAllowlist
        resolveReady()
      }}
      onUserMessage={(text) => {
        // Dispatch display event first, then unblock the loop
        dispatchEvent?.({
          type: 'user_message',
          id: Math.random().toString(36).slice(2),
          text,
          ts: new Date().toISOString(),
        })
        pushInput(text)
      }}
      onStop={() => {
        dispatchEvent?.({ type: 'stop_requested' })
      }}
      onExit={async (withPayload) => {
        if (!withPayload) pushInput(null)
        // withPayload=true: sleep cycle runs inside loop, loop exits naturally
      }}
    />,
  )

  // Wait for React to mount and expose dispatch before starting the loop
  await readyGate

  try {
    await runSessionLoop(layout, bootResult, adapter, logger, sessionOpts, io)
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    await logger.error('session', 'loop_crash', { error: msg })
    // Emit error to TUI before closing
    io.onEvent({
      type: 'system_message',
      id: `crash-${Date.now()}`,
      text: `⚠ session error: ${msg}`,
      ts: new Date().toISOString(),
    })
    // Give TUI time to render the error before unmounting
    await new Promise(r => setTimeout(r, 2000))
  }
  unmount()
  await waitUntilExit()
}
