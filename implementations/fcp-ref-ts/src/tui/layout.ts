// Terminal layout — computes the four fixed regions of the TUI.
// Status bar (row 1) + chat history (rows 2..N-2) + separator (N-1) + input (N).
import type { Output } from './renderer.js'

export interface TUILayout {
  readonly statusRow:   number  // row 1
  readonly chatStart:   number  // row 2
  readonly chatEnd:     number  // row rows-2
  readonly inputRow:    number  // row rows
  readonly columns:     number
}

export function computeLayout(out: Output): TUILayout {
  const rows    = Math.max(out.rows, 6)
  const columns = Math.max(out.columns, 40)
  return {
    statusRow: 1,
    chatStart: 2,
    chatEnd:   rows - 2,
    inputRow:  rows,
    columns,
  }
}

// The number of lines available for chat history.
export function chatLines(layout: TUILayout): number {
  return Math.max(1, layout.chatEnd - layout.chatStart + 1)
}
