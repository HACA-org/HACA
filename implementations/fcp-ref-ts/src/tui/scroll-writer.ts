// Scroll writer — appends lines to the DECSTBM scroll region.
// The scroll region is defined by setScrollRegion(top, bottom). Writing a \n
// at the bottom row of the region scrolls the region up and keeps the cursor
// at that row. Rows outside the region are unaffected.
import type { Output } from './renderer.js'
import { moveTo, eraseLine } from './renderer.js'

// Append a single line to the scroll region. The cursor is moved to
// scrollBottom, the line is written, and a \n triggers the scroll.
export function appendLine(out: Output, scrollBottom: number, line: string): void {
  out.write(moveTo(scrollBottom, 1))
  out.write('\n')            // scroll the region up one row
  out.write(eraseLine())     // clear the new blank row
  out.write(line)
}

// Append multiple lines in batch. Each line scrolls the region up by one.
export function appendLines(out: Output, scrollBottom: number, lines: string[]): void {
  for (const line of lines) {
    appendLine(out, scrollBottom, line)
  }
}
