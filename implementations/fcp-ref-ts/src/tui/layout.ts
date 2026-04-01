// Terminal layout — computes the fixed regions of the TUI.
// Scroll region (rows 1..R-9) uses DECSTBM for natural scrolling.
// Fixed bar (9 rows at bottom): separator, input, separator, footer, dynamic (5).
import type { Output } from './renderer.js'

export interface TUILayout {
  readonly rows:          number
  readonly columns:       number
  readonly scrollTop:     number    // always 1
  readonly scrollBottom:  number    // rows - 9
  readonly sepAboveInput: number    // rows - 8
  readonly inputRow:      number    // rows - 7
  readonly sepBelowInput: number    // rows - 6
  readonly footerRow:     number    // rows - 5
  readonly dynamicStart:  number    // rows - 4
  readonly dynamicEnd:    number    // rows
}

// Minimum terminal size for full TUI. Below this, caller should degrade.
export const MIN_ROWS = 18
export const MIN_COLS = 40

export function computeLayout(out: Output): TUILayout {
  const rows    = Math.max(out.rows, MIN_ROWS)
  const columns = Math.max(out.columns, MIN_COLS)
  return {
    rows,
    columns,
    scrollTop:     1,
    scrollBottom:  rows - 9,
    sepAboveInput: rows - 8,
    inputRow:      rows - 7,
    sepBelowInput: rows - 6,
    footerRow:     rows - 5,
    dynamicStart:  rows - 4,
    dynamicEnd:    rows,
  }
}

// The number of lines available for chat (scroll region height).
export function chatLines(layout: TUILayout): number {
  return Math.max(1, layout.scrollBottom - layout.scrollTop + 1)
}
