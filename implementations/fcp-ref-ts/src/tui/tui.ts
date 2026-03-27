// TUI orchestrator — implements SessionIO, renders AppState on each event.
// Consumes SessionEvent[], updates AppState via applyEvent(), re-renders.
import type { SessionIO, SessionEvent } from '../types/session.js'
import type { Profile } from '../types/cli.js'
import { applyEvent, initialAppState } from '../types/tui.js'
import type { AppState } from '../types/tui.js'
import { makeStdoutOutput, eraseScreen, moveTo, hideCursor, showCursor } from './renderer.js'
import { computeLayout } from './layout.js'
import { renderHistory } from './history.js'
import { renderStatus, renderSeparator, renderInputPrompt } from './status.js'
import { TUIInput } from './input.js'

export interface TUIOptions {
  readonly sessionId: string
  readonly profile:   Profile
}

export function createTUI(opts: TUIOptions): SessionIO & { teardown(): void } {
  const out    = makeStdoutOutput()
  let state: AppState = initialAppState(opts.sessionId, opts.profile)
  let input: TUIInput | null = null

  function render(currentInput = ''): void {
    const layout = computeLayout(out)
    const lines  = renderHistory(state.messages, layout)

    // Clear screen (full redraw)
    out.write(hideCursor())
    out.write(eraseScreen())
    out.write(moveTo(1, 1))

    renderStatus(out, state, layout)

    // Chat history
    for (let i = 0; i < lines.length; i++) {
      out.write(moveTo(layout.chatStart + i, 1) + lines[i]!.text)
    }

    renderSeparator(out, layout)
    renderInputPrompt(out, layout, currentInput)
    out.write(showCursor())
  }

  // Initial render
  if (process.stdout.isTTY) {
    render()
    process.stdout.on('resize', () => render(input?.current ?? ''))
  }

  const tui: SessionIO & { teardown(): void } = {
    prompt(): Promise<string> {
      if (!process.stdin.isTTY) {
        // Non-TTY: fall back to simple readline
        return new Promise(resolve => {
          process.stdout.write('> ')
          process.stdin.once('data', (d: Buffer) => resolve(d.toString().trim()))
        })
      }

      input = new TUIInput()
      input.on('change', (line: string) => render(line))

      return input.nextLine().then(line => {
        input?.close()
        input = null
        return line
      })
    },

    write(text: string): void {
      if (!process.stdout.isTTY) {
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
      render(input?.current ?? '')
    },

    emit(event: SessionEvent): void {
      state = applyEvent(state, event)
      if (process.stdout.isTTY) {
        render(input?.current ?? '')
      } else {
        // Non-TTY: emit minimal text output
        if (event.type === 'cpe_response' && event.content) {
          process.stdout.write('Agent: ' + event.content + '\n')
        } else if (event.type === 'tool_dispatch') {
          process.stdout.write(`[tool] ${event.skillName}\n`)
        } else if (event.type === 'session_close') {
          process.stdout.write(`[closed: ${event.reason}]\n`)
        }
      }
    },

    teardown(): void {
      input?.close()
      if (process.stdout.isTTY) {
        const layout = computeLayout(out)
        // Move cursor below the TUI area
        out.write(moveTo(layout.inputRow + 1, 1))
        out.write(showCursor())
      }
    },
  }

  return tui
}
