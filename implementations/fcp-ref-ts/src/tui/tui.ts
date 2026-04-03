// TUI orchestrator — blessed-based fullscreen terminal UI.
//
// Layout:
//   ┌─────────────────────────────┐
//   │ chatLog (blessed.log)       │  scrollable, mouse scroll, auto-scroll
//   │ ...messages...              │
//   ├─────────────────────────────┤
//   │ ─ separator ─               │  1 row
//   ├─────────────────────────────┤
//   │ > input (blessed.textbox)   │  1 row
//   ├─────────────────────────────┤
//   │ footer (blessed.box)        │  1 row, key:value
//   ├─────────────────────────────┤
//   │ dynamic (blessed.box)       │  5 rows — slash, scope, notifications
//   └─────────────────────────────┘
//
// Resize is handled automatically by blessed's screen.render().
import blessed from 'neo-blessed'
import type { Widgets } from 'blessed'
import type { SessionIO, SessionEvent } from '../types/session.js'
import type { TUIInitOptions } from '../types/tui.js'
import { applyEvent, initialAppState } from '../types/tui.js'
import type { AppState, FooterData } from '../types/tui.js'
import { formatFooter, formatElapsed } from './fixed-bar.js'
import { formatAssistant, formatOperator, formatToolUse, formatToolResult, formatSystem } from './format.js'
import { dispatch, autocomplete, matchPrefix } from './slash.js'
import type { SlashResult } from './slash.js'
import { DynamicArea } from './dynamic.js'

export type { TUIInitOptions as TUIOptions }

export class SessionCloseSignal {
  constructor(public readonly reason: 'normal' | 'operator_forced') {}
}

export function createTUI(opts: TUIInitOptions): SessionIO & { teardown(): void } {
  let state = initialAppState(opts)
  const dynamicArea = new DynamicArea()

  const isTTY = process.stdout.isTTY === true

  // ── Non-TTY fallback ────────────────────────────────────────────────────────

  if (!isTTY) {
    return {
      async prompt(): Promise<string> {
        return new Promise(resolve => {
          process.stdout.write('> ')
          process.stdin.once('data', (d: Buffer) => resolve(d.toString().trim()))
        })
      },
      write(text: string): void {
        process.stdout.write(text + '\n')
      },
      emit(event: SessionEvent): void {
        state = applyEvent(state, event)
        switch (event.type) {
          case 'cpe_response':
            if (event.content) process.stdout.write('Agent: ' + event.content + '\n')
            break
          case 'operator_msg':
            // Already echoed by the prompt — no duplication needed
            break
          case 'tool_dispatch':
            process.stdout.write(`[tool] ${event.skillName}\n`)
            break
          case 'tool_result': {
            const ok = event.result.ok
            const out = ok ? event.result.output : event.result.error
            const short = out.length > 120 ? out.slice(0, 117) + '...' : out
            process.stdout.write(`  ${event.skillName}: ${ok ? 'ok' : 'error'}${short ? ' — ' + short : ''}\n`)
            break
          }
          case 'error': {
            const msg = event.error instanceof Error ? event.error.message : String(event.error)
            process.stdout.write(`[error] ${msg}\n`)
            break
          }
          case 'session_close':
            process.stdout.write(`[closed: ${event.reason}]\n`)
            break
          default:
            // token_update, cycle_start, cpe_invoke, workspace_update — silent in non-TTY
            break
        }
      },
      teardown(): void { /* noop */ },
    }
  }

  // ── Blessed screen ──────────────────────────────────────────────────────────

  const DYNAMIC_LINES = 5
  const FIXED_BOTTOM = 1 + 1 + 1 + DYNAMIC_LINES  // separator + input + footer + dynamic = 8

  const screen = blessed.screen({
    smartCSR: true,
    fullUnicode: true,
    title: 'FCP',
  })

  // Chat log — scrollable area filling most of the screen
  const chatLog = blessed.log({
    parent: screen,
    top: 0,
    left: 0,
    right: 0,
    bottom: FIXED_BOTTOM,
    tags: false,
    scrollable: true,
    alwaysScroll: true,
    mouse: true,
    scrollbar: {
      style: { bg: 'grey' },
    },
    style: {
      fg: 'white',
    },
  }) as Widgets.Log

  // Separator line
  const separatorBox = blessed.box({
    parent: screen,
    bottom: FIXED_BOTTOM - 1,  // 7
    left: 0,
    right: 0,
    height: 1,
    tags: false,
    style: {
      fg: 'grey',
    },
  })

  // Input row — we manage text manually via key events for reliability
  const inputRow = blessed.box({
    parent: screen,
    bottom: 1 + DYNAMIC_LINES,  // 6
    left: 0,
    right: 0,
    height: 1,
    tags: false,
    style: {
      fg: 'white',
      bold: true,
    },
  })

  // Footer — 1 row
  const footerBox = blessed.box({
    parent: screen,
    bottom: DYNAMIC_LINES,  // 5
    left: 0,
    right: 0,
    height: 1,
    tags: false,
    style: {
      fg: 'white',
    },
  })

  // Dynamic area — 5 rows at very bottom
  const dynamicBox = blessed.box({
    parent: screen,
    bottom: 0,
    left: 0,
    right: 0,
    height: DYNAMIC_LINES,
    tags: false,
    style: {
      fg: 'white',
    },
  })

  // ── Manual input state ───────────────────────────────────────────────────
  let inputBuffer = ''
  let inputActive = false
  let inputResolve: ((value: string) => void) | null = null
  let inputReject: ((err: unknown) => void) | null = null

  function refreshInput(): void {
    inputRow.setContent(`> ${inputBuffer}█`)
    screen.render()
  }

  // ── Helpers ─────────────────────────────────────────────────────────────────

  function footerData(): FooterData {
    return {
      workspace:    state.workspace,
      provider:     state.provider,
      model:        state.model,
      cycleNum:     state.cycleCount,
      inputTokens:  state.inputTokens,
      outputTokens: state.outputTokens,
      contextPct:   state.budgetPct,
      sessionTime:  formatElapsed(state.sessionStart),
      sessionId:    state.sessionId,
      profile:      state.profile,
      fcpVersion:   state.fcpVersion,
      status:       state.status,
    }
  }

  function refreshFooter(): void {
    const cols = (screen as { width?: number }).width as number || 80
    footerBox.setContent(formatFooter(footerData(), cols))
    screen.render()
  }

  function refreshSeparator(): void {
    const cols = (screen as { width?: number }).width as number || 80
    separatorBox.setContent('─'.repeat(cols))
  }

  function refreshDynamic(): void {
    const lines = dynamicArea.lines()
    dynamicBox.setContent(lines.join('\n'))
    screen.render()
  }

  function chatAppend(lines: string[]): void {
    for (const line of lines) {
      chatLog.log(line)
    }
    refreshFooter()
  }

  // ── Initialization ──────────────────────────────────────────────────────────

  // Render header lines
  if (opts.headerLines && opts.headerLines.length > 0) {
    for (const line of opts.headerLines) {
      chatLog.log(line)
    }
    chatLog.log('')  // spacing after header
  }

  // Ctrl-C to exit
  screen.key(['C-c'], () => {
    screen.destroy()
    process.exit(0)
  })

  refreshSeparator()
  refreshFooter()
  refreshDynamic()

  // Refresh separator on resize
  screen.on('resize', () => {
    refreshSeparator()
    refreshFooter()
    refreshDynamic()
    if (inputActive) refreshInput()
  })

  // ── Input handling via raw key events ────────────────────────────────────

  function handleSlashAutocomplete(): void {
    if (inputBuffer.startsWith('/')) {
      const suggestions = autocomplete(inputBuffer)
      if (suggestions.length > 0) {
        dynamicArea.set('slash-autocomplete', suggestions)
      } else {
        dynamicArea.clear()
      }
      refreshDynamic()
    } else if (dynamicArea.currentType === 'slash-autocomplete') {
      dynamicArea.clear()
      refreshDynamic()
    }
  }

  async function handleSubmit(): Promise<void> {
    const raw = inputBuffer.trim()
    inputBuffer = ''
    inputActive = false  // prevent double-submit race

    if (!raw) {
      inputActive = true  // re-enable for next keystroke
      refreshInput()
      return
    }

    // Slash command?
    if (raw.startsWith('/')) {
      dynamicArea.clear()
      refreshDynamic()

      const result = await dispatch(raw, state)
      switch (result.action) {
        case 'display':
          for (const line of result.lines) chatLog.log(line)
          screen.render()
          inputActive = true
          refreshInput()
          return
        case 'exit':
          if (inputReject) {
            const rej = inputReject
            inputResolve = null
            inputReject = null
            rej(new SessionCloseSignal(result.reason === 'normal' ? 'normal' : 'operator_forced'))
          }
          return
        case 'clear':
          chatLog.setContent('')
          screen.render()
          inputActive = true
          refreshInput()
          return
        case 'passthrough':
          if (inputResolve) {
            const r = inputResolve
            inputResolve = null
            inputReject = null
            r(result.text)
          }
          return
        case 'none':
          inputActive = true
          refreshInput()
          return
      }
      return
    }

    // Normal text — resolve prompt
    dynamicArea.clear()
    refreshDynamic()
    if (inputResolve) {
      const r = inputResolve
      inputResolve = null
      inputReject = null
      inputActive = false
      r(raw)
    }
  }

  // Key listener — only processes keys when input is active
  function onKeypress(_ch: string, key: { full: string; name: string; ctrl?: boolean; shift?: boolean; sequence?: string }): void {
    if (!inputActive) return

    if (key.name === 'return') {
      handleSubmit().catch((e) => {
        if (inputReject) inputReject(e)
      })
      return
    }

    if (key.name === 'backspace') {
      if (inputBuffer.length > 0) {
        inputBuffer = inputBuffer.slice(0, -1)
        refreshInput()
        handleSlashAutocomplete()
      }
      return
    }

    // Ignore control keys, arrows, etc.
    if (key.ctrl || key.name === 'escape' || key.name === 'up' || key.name === 'down' ||
        key.name === 'left' || key.name === 'right' || key.name === 'tab' ||
        key.name === 'home' || key.name === 'end' || key.name === 'insert' ||
        key.name === 'delete' || key.name === 'pageup' || key.name === 'pagedown') {
      return
    }

    // Printable character — reject control chars (0x00-0x1f, 0x7f)
    if (_ch && _ch.length > 0 && !/[\x00-\x1f\x7f]/.test(_ch)) {
      inputBuffer += _ch
      refreshInput()
      handleSlashAutocomplete()
    }
  }

  screen.on('keypress', onKeypress)

  function promptUser(): Promise<string> {
    return new Promise((resolve, reject) => {
      inputActive = true
      inputBuffer = ''
      inputResolve = resolve
      inputReject = reject
      refreshInput()
    })
  }

  // ── SessionIO implementation ────────────────────────────────────────────────

  const tui: SessionIO & { teardown(): void } = {
    prompt(): Promise<string> {
      return promptUser()
    },

    write(text: string): void {
      state = {
        ...state,
        messages: [
          ...state.messages,
          { role: 'system', content: text, ts: new Date().toISOString() },
        ],
      }
      const cols = (screen as { width?: number }).width as number || 80
      chatAppend(formatSystem(text, cols))
    },

    emit(event: SessionEvent): void {
      state = applyEvent(state, event)

      const cols = (screen as { width?: number }).width as number || 80

      switch (event.type) {
        case 'cpe_response':
          if (event.content) {
            chatAppend(formatAssistant(event.content, cols))
          }
          // tool_uses are rendered via separate tool_dispatch events — no duplication
          break

        case 'operator_msg':
          chatAppend(formatOperator(event.content, cols))
          break

        case 'tool_dispatch':
          chatAppend(formatToolUse(event.skillName, event.input, cols))
          break

        case 'tool_result': {
          const ok = event.result.ok
          const output = ok ? event.result.output : event.result.error
          chatAppend(formatToolResult(event.skillName, ok, output, cols))
          break
        }

        case 'session_close':
          chatAppend(formatSystem(`Session closed: ${event.reason}`, cols))
          break

        case 'error': {
          const msg = event.error instanceof Error ? event.error.message : String(event.error)
          chatAppend(formatSystem(`Error: ${msg}`, cols))
          break
        }

        default:
          // token_update, cycle_start, workspace_update, cpe_invoke — footer-only
          refreshFooter()
          break
      }
    },

    teardown(): void {
      inputActive = false
      screen.removeListener('keypress', onKeypress)
      screen.destroy()
    },
  }

  return tui
}
