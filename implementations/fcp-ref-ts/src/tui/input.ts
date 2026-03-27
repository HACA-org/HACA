// TUI input — keypress-based line editor for raw terminal interaction.
// Manages a mutable line buffer; caller is responsible for rendering the prompt row.
import * as readline from 'node:readline'
import { EventEmitter } from 'node:events'

export interface InputLine {
  readonly text: string
}

export class TUIInput extends EventEmitter {
  private buf  = ''
  private hist: string[] = []
  private histIdx = -1

  constructor() {
    super()
    readline.emitKeypressEvents(process.stdin)
    if (process.stdin.isTTY) process.stdin.setRawMode(true)
    process.stdin.on('keypress', this._onKey.bind(this))
  }

  get current(): string { return this.buf }

  private _onKey(_ch: string | undefined, key: readline.Key | undefined): void {
    if (!key) return

    if (key.ctrl && key.name === 'c') {
      this.close()
      process.exit(0)
    }

    if (key.name === 'return') {
      const line = this.buf
      if (line.trim()) this.hist.unshift(line)
      this.buf     = ''
      this.histIdx = -1
      this.emit('line', line)
      this.emit('change', this.buf)
      return
    }

    if (key.name === 'backspace') {
      this.buf = this.buf.slice(0, -1)
      this.emit('change', this.buf)
      return
    }

    if (key.name === 'up') {
      this.histIdx = Math.min(this.histIdx + 1, this.hist.length - 1)
      if (this.histIdx >= 0) this.buf = this.hist[this.histIdx] ?? ''
      this.emit('change', this.buf)
      return
    }

    if (key.name === 'down') {
      this.histIdx = Math.max(this.histIdx - 1, -1)
      this.buf = this.histIdx >= 0 ? (this.hist[this.histIdx] ?? '') : ''
      this.emit('change', this.buf)
      return
    }

    // Printable character
    if (!key.ctrl && !key.meta && _ch && _ch.length === 1) {
      this.buf += _ch
      this.emit('change', this.buf)
    }
  }

  nextLine(): Promise<string> {
    return new Promise(resolve => {
      this.once('line', resolve)
    })
  }

  close(): void {
    if (process.stdin.isTTY) process.stdin.setRawMode(false)
    process.stdin.removeAllListeners('keypress')
  }
}
