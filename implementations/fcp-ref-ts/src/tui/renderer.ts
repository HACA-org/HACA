// ANSI renderer primitives — zero external dependencies.
// All writes go through a single Output interface to allow testing without a real TTY.

export interface Output {
  write(data: string): void
  columns: number
  rows: number
}

export function makeStdoutOutput(): Output {
  return {
    write: (s) => process.stdout.write(s),
    get columns() { return process.stdout.columns || 80 },
    get rows()    { return process.stdout.rows    || 24 },
  }
}

// ─── ANSI escape sequences ────────────────────────────────────────────────────

export const ESC = '\x1b'

export function moveTo(row: number, col: number): string {
  return `${ESC}[${row};${col}H`
}

export function eraseToEOL(): string {
  return `${ESC}[K`
}

export function eraseLine(): string {
  return `${ESC}[2K`
}

export function eraseScreen(): string {
  return `${ESC}[2J`
}

export function hideCursor(): string {
  return `${ESC}[?25l`
}

export function showCursor(): string {
  return `${ESC}[?25h`
}

export function saveCursor(): string {
  return `${ESC}[s`
}

export function restoreCursor(): string {
  return `${ESC}[u`
}

export function bold(s: string): string {
  return `${ESC}[1m${s}${ESC}[0m`
}

export function dim(s: string): string {
  return `${ESC}[2m${s}${ESC}[0m`
}

export function color(s: string, code: number): string {
  return `${ESC}[${code}m${s}${ESC}[0m`
}

export const C_CYAN    = 36
export const C_GREEN   = 32
export const C_YELLOW  = 33
export const C_RED     = 31
export const C_MAGENTA = 35

// Write a line at a specific row, truncated to terminal width.
export function writeLine(out: Output, row: number, text: string, col = 1): void {
  const maxLen = out.columns - col + 1
  const line   = text.length > maxLen ? text.slice(0, maxLen - 1) + '…' : text
  out.write(moveTo(row, col) + eraseLine() + line)
}
