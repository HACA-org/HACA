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
import chalk from 'chalk'
import type { SessionIO, SessionEvent } from '../types/session.js'
import type { TUIInitOptions } from '../types/tui.js'
import { applyEvent, initialAppState } from '../types/tui.js'
import type { FooterData } from '../types/tui.js'
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
            // Non-TTY: readline already echoes input, no additional output needed.
            // TTY path renders via emit() case below.
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
  })

  // Layout offsets from bottom — all derived from FIXED_BOTTOM and DYNAMIC_LINES
  // so changing either constant keeps everything in sync.
  const BOTTOM_SEPARATOR = FIXED_BOTTOM - 1  // separator sits just above input
  const BOTTOM_INPUT     = FIXED_BOTTOM - 2  // input above footer
  const BOTTOM_FOOTER    = FIXED_BOTTOM - 3  // footer above dynamic area

  // Separator line
  const separatorBox = blessed.box({
    parent: screen,
    bottom: BOTTOM_SEPARATOR,
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
    bottom: BOTTOM_INPUT,
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
    bottom: BOTTOM_FOOTER,
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

  // ── Screen helpers ───────────────────────────────────────────────────────

  function getCols(): number {
    return (screen as unknown as { width?: number }).width ?? 80
  }

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
      status:       state.status,
    }
  }

  function refreshFooter(): void {
    footerBox.setContent(formatFooter(footerData(), getCols()))
    screen.render()
  }

  function refreshSeparator(): void {
    separatorBox.setContent('─'.repeat(getCols()))
    screen.render()
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
        case 'set_verbose':
          state = { ...state, verbose: result.value }
          chatAppend([chalk.dim(`  verbose: ${result.value ? chalk.green('on') : 'off'}`)])
          inputActive = true
          refreshInput()
          return

        case 'exit': {
          const rej = inputReject
          inputResolve = null
          inputReject = null
          inputRow.setContent('')
          screen.render()
          if (rej) {
            rej(new SessionCloseSignal(result.reason === 'normal' ? 'normal' : 'operator_forced'))
          } else {
            // No active prompt — signal is delivered via teardown path
            screen.destroy()
            process.exit(0)
          }
          return
        }
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
            inputRow.setContent('')
            screen.render()
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

    // Normal text — clear input visually then resolve prompt
    dynamicArea.clear()
    inputRow.setContent('')
    screen.render()
    if (inputResolve) {
      const r = inputResolve
      inputResolve = null
      inputReject = null
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
      // write() is for out-of-band system messages (not tracked in AppState).
      // State is only mutated via emit() + applyEvent() to keep a single update path.
      chatAppend(formatSystem(text, getCols()))
    },

    emit(event: SessionEvent): void {
      state = applyEvent(state, event)
      switch (event.type) {
        case 'cpe_response':
          if (event.content) {
            chatAppend(formatAssistant(event.content, getCols()))
          }
          // tool_uses are rendered via separate tool_dispatch events — no duplication
          break

        case 'operator_msg':
          chatAppend(formatOperator(event.content, getCols()))
          break

        case 'tool_dispatch':
          chatAppend(formatToolUse(event.skillName, event.input, getCols(), state.verbose))
          break

        case 'tool_result': {
          const ok = event.result.ok
          const output = ok ? event.result.output : event.result.error
          chatAppend(formatToolResult(event.skillName, ok, output, getCols(), state.verbose))
          break
        }

        case 'session_close':
          chatAppend(formatSystem(`Session closed: ${event.reason}`, getCols()))
          break

        case 'error': {
          const msg = event.error instanceof Error ? event.error.message : String(event.error)
          chatAppend(formatSystem(`Error: ${msg}`, getCols()))
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
