import { useRef } from 'react'
import { Box, useApp, useStdout } from 'ink'
import { Chat } from './components/Chat.js'
import { Sidebar } from './components/Sidebar.js'
import { InputZone } from './components/InputZone.js'
import { Footer } from './components/Footer.js'
import { useTuiStore, makeInitialState } from './store.js'
import type { TuiState } from './types.js'
import type { SlashCommand } from './components/SlashMenu.js'

// Built-in slash commands
const SLASH_COMMANDS: SlashCommand[] = [
  { name: '/new',    description: 'clear history and start fresh' },
  { name: '/reset',  description: 'reset session (no closure payload)' },
  { name: '/stop',   description: 'interrupt current cycle' },
  { name: '/exit',   description: 'close session with closure payload' },
  { name: '/close',  description: 'close session with closure payload' },
  { name: '/focus',  description: 'change workspace focus', hasPopup: false },
  { name: '/inbox',  description: 'view inbox', hasPopup: true },
  { name: '/model',  description: 'change active model', hasPopup: true },
  { name: '/agenda', description: 'view scheduled tasks', hasPopup: true },
  { name: '/memory', description: 'inspect working memory', hasPopup: true },
  { name: '/endure', description: 'manage evolution proposals', hasPopup: true },
  { name: '/cmi',    description: 'cognitive mesh connections', hasPopup: true },
]

export interface AppProps {
  initial: TuiState
  onReady: (dispatch: (e: SessionEvent) => void, setAllowlist: (p: AllowlistPrompt | null) => void) => void
  onUserMessage: (text: string) => void
  onStop: () => void
  onExit: (withPayload: boolean) => Promise<void>
  onReset: () => void
  onSlashCommand?: (cmd: string) => void
}

import type { SessionEvent } from './types.js'
import type { AllowlistPrompt } from './types.js'

export function App({ initial, onReady, onUserMessage, onStop, onExit, onReset, onSlashCommand }: AppProps) {
  const { exit } = useApp()
  const { stdout } = useStdout()

  const terminalWidth  = stdout?.columns  ?? 120
  const terminalHeight = stdout?.rows     ?? 40

  const { state, dispatchEvent, setInputMode, setAllowlistPrompt, setCtrlCPending, setActivePopup } =
    useTuiStore(initial)

  // Expose dispatch and setAllowlistPrompt to parent on first render
  const readyFired = useRef(false)
  if (!readyFired.current) {
    readyFired.current = true
    onReady(dispatchEvent, setAllowlistPrompt)
  }

  // Layout math
  const SIDEBAR_WIDTH = 30
  const FOOTER_HEIGHT = 1
  const INPUT_HEIGHT  = 3   // input line + slash menu padding
  const chatWidth  = terminalWidth - SIDEBAR_WIDTH - 1  // -1 for sidebar border
  const chatHeight = terminalHeight - FOOTER_HEIGHT - INPUT_HEIGHT - 2

  // ── Handlers ────────────────────────────────────────────────────────────────

  function handleSubmit(text: string) {
    if (state.inputMode !== 'normal') return
    onUserMessage(text)
  }

  function handleStop() {
    onStop()
    dispatchEvent({ type: 'stop_requested' })
  }

  async function handleCtrlC() {
    if (state.ctrlCPending) {
      // Second press — force close with sleep cycle, no closure payload
      setCtrlCPending(false)
      dispatchEvent({ type: 'sleep_start' })
      await onExit(false)
      exit()
    } else {
      setCtrlCPending(true)
      // Auto-clear after 3s
      setTimeout(() => setCtrlCPending(false), 3000)
    }
  }

  function handleSlashCommand(cmd: SlashCommand) {
    if (cmd.hasPopup) {
      setActivePopup(cmd.name)
      return
    }
    switch (cmd.name) {
      case '/new':
      case '/reset':
        dispatchEvent({ type: 'session_reset' })
        onReset()
        break
      case '/stop':
        handleStop()
        break
      case '/exit':
      case '/close':
        void handleControlledExit()
        break
      default:
        onSlashCommand?.(cmd.name)
    }
  }

  async function handleControlledExit() {
    setInputMode('locked')
    // System message: generating closure payload
    dispatchEvent({
      type: 'system_message',
      id: 'exit-1',
      text: '⟳ gerando closure payload...',
      ts: new Date().toISOString(),
    })
    dispatchEvent({ type: 'sleep_start' })
    await onExit(true)
    dispatchEvent({
      type: 'system_message',
      id: 'exit-2',
      text: '✓ sleep cycle completo',
      ts: new Date().toISOString(),
    })
    dispatchEvent({ type: 'sleep_done' })
    exit()
  }

  return (
    <Box flexDirection="column" width={terminalWidth} height={terminalHeight}>
      {/* Main area: chat + sidebar */}
      <Box flexDirection="row" flexGrow={1}>
        <Chat
          entries={state.entries}
          height={chatHeight}
          width={chatWidth}
        />
        <Sidebar
          state={state.sidebar}
          height={chatHeight}
        />
      </Box>

      {/* Input zone */}
      <InputZone
        mode={state.inputMode}
        allowlistPrompt={state.allowlistPrompt}
        commands={SLASH_COMMANDS}
        onSubmit={handleSubmit}
        onSlashCommand={handleSlashCommand}
        onStop={handleStop}
        onCtrlC={() => void handleCtrlC()}
        width={terminalWidth}
      />

      {/* Footer */}
      <Footer
        state={state.footer}
        ctrlCPending={state.ctrlCPending}
        terminalWidth={terminalWidth}
      />
    </Box>
  )
}

// Re-export for wiring
export type { TuiState }
export { makeInitialState }
