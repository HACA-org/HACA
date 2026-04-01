// TUI input — keypress-based line editor for raw terminal interaction.
// Manages a mutable line buffer with cursor positioning and history.
// Caller is responsible for rendering the prompt row.
import * as readline from 'node:readline'
import { EventEmitter } from 'node:events'

export class TUIInput extends EventEmitter {
  private buf  = ''
  private pos  = 0          // cursor position within buf
  private hist: string[] = []
  private histIdx = -1
  private label = '> '

  constructor() {
    super()
    readline.emitKeypressEvents(process.stdin)
    if (process.stdin.isTTY) process.stdin.setRawMode(true)
    process.stdin.on('keypress', this._onKey.bind(this))
  }

  get current(): string { return this.buf }
  get cursorPos(): number { return this.pos }
  get promptLabel(): string { return this.label }

  setLabel(label: string): void {
    this.label = label
  }

  private _onKey(_ch: string | undefined, key: readline.Key | undefined): void {
    if (!key) return

    if (key.ctrl && key.name === 'c') {
      this.close()
      process.exit(0)
    }

    // Ctrl-A: home
    if (key.ctrl && key.name === 'a') {
      this.pos = 0
      this.emit('change', this.buf)
      return
    }

    // Ctrl-E: end
    if (key.ctrl && key.name === 'e') {
      this.pos = this.buf.length
      this.emit('change', this.buf)
      return
    }

    // Ctrl-U: clear line
    if (key.ctrl && key.name === 'u') {
      this.buf = ''
      this.pos = 0
      this.emit('change', this.buf)
      return
    }

    // Ctrl-W: delete word backward
    if (key.ctrl && key.name === 'w') {
      const before = this.buf.slice(0, this.pos)
      const after  = this.buf.slice(this.pos)
      const trimmed = before.replace(/\S+\s*$/, '')
      this.buf = trimmed + after
      this.pos = trimmed.length
      this.emit('change', this.buf)
      return
    }

    if (key.name === 'return') {
      const line = this.buf
      if (line.trim()) this.hist.unshift(line)
      this.buf     = ''
      this.pos     = 0
      this.histIdx = -1
      this.emit('line', line)
      this.emit('change', this.buf)
      return
    }

    if (key.name === 'backspace') {
      if (this.pos > 0) {
        this.buf = this.buf.slice(0, this.pos - 1) + this.buf.slice(this.pos)
        this.pos--
      }
      this.emit('change', this.buf)
      return
    }

    // Delete key
    if (key.name === 'delete') {
      if (this.pos < this.buf.length) {
        this.buf = this.buf.slice(0, this.pos) + this.buf.slice(this.pos + 1)
      }
      this.emit('change', this.buf)
      return
    }

    if (key.name === 'left') {
      if (this.pos > 0) this.pos--
      this.emit('change', this.buf)
      return
    }

    if (key.name === 'right') {
      if (this.pos < this.buf.length) this.pos++
      this.emit('change', this.buf)
      return
    }

    if (key.name === 'home') {
      this.pos = 0
      this.emit('change', this.buf)
      return
    }

    if (key.name === 'end') {
      this.pos = this.buf.length
      this.emit('change', this.buf)
      return
    }

    if (key.name === 'up') {
      this.histIdx = Math.min(this.histIdx + 1, this.hist.length - 1)
      if (this.histIdx >= 0) {
        this.buf = this.hist[this.histIdx] ?? ''
        this.pos = this.buf.length
      }
      this.emit('change', this.buf)
      return
    }

    if (key.name === 'down') {
      this.histIdx = Math.max(this.histIdx - 1, -1)
      this.buf = this.histIdx >= 0 ? (this.hist[this.histIdx] ?? '') : ''
      this.pos = this.buf.length
      this.emit('change', this.buf)
      return
    }

    // Tab: emit tab event for slash autocomplete
    if (key.name === 'tab') {
      this.emit('tab', this.buf)
      return
    }

    // Printable character
    if (!key.ctrl && !key.meta && _ch && _ch.length === 1) {
      this.buf = this.buf.slice(0, this.pos) + _ch + this.buf.slice(this.pos)
      this.pos++
      this.emit('change', this.buf)
    }
  }

  nextLine(): Promise<string> {
    return new Promise(resolve => {
      this.once('line', resolve)
    })
  }

  // Replace the current buffer (used by tab-complete).
  fill(text: string): void {
    this.buf = text
    this.pos = text.length
    this.emit('change', this.buf)
  }

  close(): void {
    if (process.stdin.isTTY) process.stdin.setRawMode(false)
    process.stdin.removeAllListeners('keypress')
  }
}
