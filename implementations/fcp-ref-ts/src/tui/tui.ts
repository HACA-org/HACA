// TUI orchestrator — implements SessionIO with DECSTBM scroll region + fixed bottom bar.
// Scroll region (rows 1..R-9): natural terminal scrolling with scrollback.
// Fixed bar (9 rows): separator, input, separator, footer, dynamic (5 lines).
import type { SessionIO, SessionEvent } from '../types/session.js'
import type { TUIInitOptions } from '../types/tui.js'
import { applyEvent, initialAppState } from '../types/tui.js'
import type { AppState, FooterData } from '../types/tui.js'
import {
  makeStdoutOutput, eraseScreen, moveTo, hideCursor, showCursor,
  setScrollRegion, resetScrollRegion,
} from './renderer.js'
import { computeLayout, MIN_ROWS } from './layout.js'
import type { TUILayout } from './layout.js'
import { appendLines } from './scroll-writer.js'
import {
  renderFixedBar, positionInputCursor, formatElapsed,
} from './fixed-bar.js'
import { formatAssistant, formatOperator, formatToolUse, formatToolResult, formatSystem } from './format.js'
import { DynamicArea } from './dynamic.js'
import { dispatch, autocomplete, matchPrefix } from './slash.js'
import type { SlashResult } from './slash.js'
import { TUIInput } from './input.js'

export type { TUIInitOptions as TUIOptions }

// Signal thrown when a slash command requests session close.
export class SessionCloseSignal {
  constructor(public readonly reason: 'normal' | 'operator_forced') {}
}

export function createTUI(opts: TUIInitOptions): SessionIO & { teardown(): void } {
  const out     = makeStdoutOutput()
  let   state   = initialAppState(opts)
  let   input:  TUIInput | null = null
  const dynamic = new DynamicArea()
  let   layout  = computeLayout(out)
  let   inputLabel = '> '

  const isTTY = process.stdout.isTTY && out.rows >= MIN_ROWS

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

  function refreshBar(currentInput = ''): void {
    renderFixedBar(out, layout, footerData(), currentInput, dynamic.lines(), inputLabel)
    positionInputCursor(out, layout.inputRow, currentInput, inputLabel)
    out.write(showCursor())
  }

  function chatAppend(lines: string[]): void {
    if (!isTTY) return
    out.write(hideCursor())
    appendLines(out, layout.scrollBottom, lines)
    refreshBar(input?.current ?? '')
  }

  // ── Initialization ──────────────────────────────────────────────────────────

  function initScreen(): void {
    out.write(hideCursor())
    out.write(eraseScreen())
    out.write(moveTo(1, 1))
    out.write(setScrollRegion(layout.scrollTop, layout.scrollBottom))
    out.write(moveTo(layout.scrollBottom, 1))
    refreshBar('')
  }

  if (isTTY) {
    initScreen()
    process.stdout.on('resize', () => {
      layout = computeLayout(out)
      out.write(resetScrollRegion())
      out.write(eraseScreen())
      out.write(setScrollRegion(layout.scrollTop, layout.scrollBottom))
      refreshBar(input?.current ?? '')
    })
  }

  // ── SessionIO implementation ────────────────────────────────────────────────

  const tui: SessionIO & { teardown(): void } = {
    async prompt(): Promise<string> {
      if (!isTTY) {
        // Non-TTY fallback: simple line-based I/O
        return new Promise(resolve => {
          process.stdout.write('> ')
          process.stdin.once('data', (d: Buffer) => resolve(d.toString().trim()))
        })
      }

      // Clear dynamic area on new prompt (unless showing persistent content)
      if (dynamic.currentType !== 'approval') {
        dynamic.clear()
        refreshBar('')
      }

      // Prompt loop — slash commands are handled internally, only normal text returns
      while (true) {
        input = new TUIInput()
        let tabIdx = -1  // for cycling through slash autocomplete matches
        let tabMatches: string[] = []

        input.on('change', (line: string) => {
          tabIdx = -1  // reset tab cycling on any change
          // Show slash autocomplete in dynamic area
          if (line.startsWith('/')) {
            const suggestions = autocomplete(line)
            if (suggestions.length > 0) {
              dynamic.set('slash-autocomplete', suggestions)
              tabMatches = matchPrefix(line).map(c => c.name)
            } else {
              dynamic.clear()
              tabMatches = []
            }
          } else if (dynamic.currentType === 'slash-autocomplete') {
            dynamic.clear()
            tabMatches = []
          }
          refreshBar(line)
        })

        input.on('tab', () => {
          if (tabMatches.length > 0) {
            tabIdx = (tabIdx + 1) % tabMatches.length
            input!.fill(tabMatches[tabIdx]! + ' ')
          }
        })

        const line = await input.nextLine()
        input.close()
        input = null

        if (!line.startsWith('/')) {
          dynamic.clear()
          return line
        }

        // Dispatch slash command
        const result: SlashResult = await dispatch(line, state)

        switch (result.action) {
          case 'display':
            dynamic.set('slash-result', result.lines)
            refreshBar('')
            continue  // re-prompt

          case 'exit':
            throw new SessionCloseSignal(result.reason === 'normal' ? 'normal' : 'operator_forced')

          case 'clear':
            dynamic.clear()
            out.write(eraseScreen())
            out.write(setScrollRegion(layout.scrollTop, layout.scrollBottom))
            out.write(moveTo(layout.scrollBottom, 1))
            refreshBar('')
            continue  // re-prompt

          case 'passthrough':
            dynamic.clear()
            return result.text

          case 'none':
            continue  // re-prompt
        }
      }
    },

    write(text: string): void {
      if (!isTTY) {
        process.stdout.write(text + '\n')
        return
      }
      state = {
        ...state,
        messages: [
          ...state.messages,
          { role: 'system', content: text, ts: new Date().toISOString() },
        ],
      }
      chatAppend(formatSystem(text, layout.columns))
    },

    emit(event: SessionEvent): void {
      state = applyEvent(state, event)

      if (!isTTY) {
        // Non-TTY: minimal text output
        if (event.type === 'cpe_response' && event.content) {
          process.stdout.write('Agent: ' + event.content + '\n')
        } else if (event.type === 'tool_dispatch') {
          process.stdout.write(`[tool] ${event.skillName}\n`)
        } else if (event.type === 'session_close') {
          process.stdout.write(`[closed: ${event.reason}]\n`)
        }
        return
      }

      // TTY: format event and render
      switch (event.type) {
        case 'cpe_response':
          if (event.content) {
            chatAppend(formatAssistant(event.content, layout.columns))
          }
          if (event.toolUses.length > 0) {
            for (const tu of event.toolUses) {
              chatAppend(formatToolUse(tu.name, tu.input, layout.columns))
            }
          }
          break

        case 'operator_msg':
          chatAppend(formatOperator(event.content, layout.columns))
          break

        case 'tool_dispatch':
          chatAppend(formatToolUse(event.skillName, event.input, layout.columns))
          break

        case 'tool_result': {
          const ok = event.result.ok
          const output = ok ? event.result.output : event.result.error
          chatAppend(formatToolResult(event.skillName, ok, output, layout.columns))
          break
        }

        case 'session_close':
          chatAppend(formatSystem(`Session closed: ${event.reason}`, layout.columns))
          break

        case 'error': {
          const msg = event.error instanceof Error ? event.error.message : String(event.error)
          chatAppend(formatSystem(`Error: ${msg}`, layout.columns))
          break
        }

        default:
          // token_update, cycle_start, workspace_update, cpe_invoke — footer-only updates
          break
      }

      // Always refresh the footer bar for status/token updates
      refreshBar(input?.current ?? '')
    },

    teardown(): void {
      input?.close()
      if (isTTY) {
        out.write(resetScrollRegion())
        out.write(moveTo(layout.rows, 1))
        out.write(showCursor())
        out.write('\n')
      }
    },
  }

  return tui
}
