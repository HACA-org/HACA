import { render } from 'ink'
import { App, makeInitialState } from './App.js'
import type { SessionEvent, AllowDecision, AllowlistPrompt } from './types.js'
import type { BootResult } from '../boot/types.js'
import type { CPEAdapter } from '../cpe/types.js'
import type { Layout } from '../store/layout.js'
import type { Logger } from '../logger/logger.js'
import { runSessionLoop } from '../session/loop.js'
import type { SessionOptions } from '../session/loop.js'

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
}

export async function startTui(opts: TuiOptions): Promise<void> {
  const {
    layout, bootResult, adapter, logger, sessionOpts,
    model, provider, workspaceFocus,
    verbose = false, debug = false, version = '0.1.0',
  } = opts

  // Read profile from imprint if available
  let profile: 'haca-core' | 'haca-evolve' = 'haca-core'
  try {
    const { readJson } = await import('../store/io.js')
    const { existsSync } = await import('node:fs')
    if (existsSync(layout.imprint)) {
      const imp = await readJson<{ hacaProfile: 'haca-core' | 'haca-evolve' }>(layout.imprint)
      profile = imp.hacaProfile
    }
  } catch { /* use default */ }

  const initial = makeInitialState({
    sessionId: bootResult.sessionId,
    profile,
    version,
    verbose,
    debug,
    model,
    provider,
    contextWindow: sessionOpts.contextWindow,
    workspaceFocus,
  })

  // Channels between TUI and session loop
  let dispatchEvent: ((e: SessionEvent) => void) | null = null
  let setAllowlistPromptFn: ((p: AllowlistPrompt | null) => void) | null = null
  const inputQueue: Array<string | null> = []
  let inputResolve: ((v: string | null) => void) | null = null

  function pushInput(text: string | null) {
    if (inputResolve) {
      const r = inputResolve
      inputResolve = null
      r(text)
    } else {
      inputQueue.push(text)
    }
  }

  // Loop IO interface
  const io = {
    readInput(): Promise<string | null> {
      return new Promise(resolve => {
        if (inputQueue.length > 0) {
          resolve(inputQueue.shift()!)
        } else {
          inputResolve = resolve
        }
      })
    },

    writeOutput(text: string) {
      dispatchEvent?.({
        type: 'agent_end',
        id: Math.random().toString(36).slice(2),
        text,
        ts: new Date().toISOString(),
      })
    },

    requestToolApproval(name: string, input: Record<string, unknown>): Promise<'once' | 'session' | 'allow' | 'deny'> {
      return new Promise(resolve => {
        const prompt: AllowlistPrompt = {
          toolName: name,
          toolInput: input,
          resolve: (decision: AllowDecision) => {
            setAllowlistPromptFn?.(null)
            const mapped = decision === 'persist' ? 'allow' : decision
            resolve(mapped as 'once' | 'session' | 'allow' | 'deny')
          },
        }
        setAllowlistPromptFn?.(prompt)
      })
    },

    onContextWarning(usedPct: number) {
      dispatchEvent?.({
        type: 'system_message',
        id: `ctx-warn-${Date.now()}`,
        text: `⚠ context window at ${Math.round(usedPct * 100)}%`,
        ts: new Date().toISOString(),
      })
    },
  }

  const { unmount, waitUntilExit } = render(
    <App
      initial={initial}
      onReady={(dispatch, setAllowlist) => {
        dispatchEvent = dispatch
        setAllowlistPromptFn = setAllowlist
      }}
      onUserMessage={(text) => {
        pushInput(text)
        dispatchEvent?.({
          type: 'user_message',
          id: Math.random().toString(36).slice(2),
          text,
          ts: new Date().toISOString(),
        })
      }}
      onStop={() => {
        dispatchEvent?.({ type: 'stop_requested' })
      }}
      onExit={async (withPayload) => {
        if (!withPayload) {
          pushInput(null)
        }
      }}
      onReset={() => {
        dispatchEvent?.({ type: 'session_reset' })
        pushInput('/reset')
      }}
    />,
  )

  // Run session loop (blocks until done)
  await runSessionLoop(layout, bootResult, adapter, logger, sessionOpts, io)

  unmount()
  await waitUntilExit()
}
