// Chat message formatting — converts content into styled terminal lines for
// the scroll region.
import chalk from 'chalk'

// ─── Word wrap ────────────────────────────────────────────────────────────────

function wrapText(text: string, maxWidth: number): string[] {
  const result: string[] = []
  for (const paragraph of text.replace(/\r\n/g, '\n').split('\n')) {
    if (paragraph.trim() === '') {
      result.push('')
      continue
    }
    let current = ''
    for (const rawWord of paragraph.split(' ').filter(Boolean)) {
      // Split words longer than maxWidth into chunks
      const chunks: string[] = []
      let w = rawWord
      while (w.length > maxWidth) {
        chunks.push(w.slice(0, maxWidth))
        w = w.slice(maxWidth)
      }
      if (w.length > 0) chunks.push(w)

      for (const word of chunks) {
        if (current.length === 0) {
          current = word
        } else if (current.length + 1 + word.length <= maxWidth) {
          current += ' ' + word
        } else {
          result.push(current)
          current = word
        }
      }
    }
    if (current.length > 0) result.push(current)
  }
  return result.length > 0 ? result : ['']
}

// ─── Role formatting ──────────────────────────────────────────────────────────

// All labels padded to the same visible width (6 = len('System')) + 2 spaces = 8.
const LABEL_WIDTH = 8
function padLabel(s: string): string { return s.padEnd(LABEL_WIDTH) }

const ROLE_PREFIX = {
  operator:  chalk.bold.cyan(padLabel('You'))     + chalk.dim('▎ '),
  assistant: chalk.bold.green(padLabel('Agent'))   + chalk.dim('▎ '),
  tool:      chalk.bold.yellow(padLabel('Tool'))   + chalk.dim('▎ '),
  system:    chalk.bold.dim(padLabel('System'))    + chalk.dim('▎ '),
} as const

// Continuation indent: LABEL_WIDTH spaces + ▎ + space (matches prefix visible width)
const CONT_PAD = ' '.repeat(LABEL_WIDTH) + chalk.dim('▎ ')

function formatRole(role: keyof typeof ROLE_PREFIX, text: string, cols: number): string[] {
  const contentCols = Math.max(20, cols - 11) // prefix is ~11 visible chars
  const wrapped = wrapText(text, contentCols)
  return wrapped.map((line, i) =>
    (i === 0 ? ROLE_PREFIX[role] : CONT_PAD) + line,
  )
}

// ─── Public formatters ────────────────────────────────────────────────────────

export function formatAssistant(content: string, cols: number): string[] {
  if (!content) return []
  return formatRole('assistant', content, cols)
}

export function formatOperator(content: string, cols: number): string[] {
  if (!content) return []
  return formatRole('operator', content, cols)
}

export function formatToolUse(name: string, input: unknown, cols: number, verbose = false): string[] {
  const contentCols = Math.max(20, cols - LABEL_WIDTH - 2)
  if (verbose && typeof input === 'object' && input !== null) {
    // Verbose: show each key:value on its own continuation line
    const lines: string[] = [ROLE_PREFIX.tool + chalk.yellow(name)]
    for (const [k, v] of Object.entries(input as Record<string, unknown>)) {
      const valStr = typeof v === 'string' ? v : JSON.stringify(v)
      const line = `${chalk.dim(k + ': ')}${valStr}`
      // Wrap long values
      if (line.length > contentCols) {
        lines.push(CONT_PAD + line.slice(0, contentCols - 3) + '...')
      } else {
        lines.push(CONT_PAD + line)
      }
    }
    return lines
  }
  // Normal: show key names only, truncated
  const summary = typeof input === 'object' && input !== null
    ? Object.keys(input as Record<string, unknown>).join(', ')
    : String(input ?? '')
  const suffix = summary ? ` (${summary})` : ''
  const full = name + suffix
  const display = full.length > contentCols ? full.slice(0, contentCols - 3) + '...' : full
  const nameEnd = Math.min(name.length, display.length)
  const text = chalk.yellow(display.slice(0, nameEnd)) +
    (display.length > nameEnd ? chalk.dim(display.slice(nameEnd)) : '')
  return [ROLE_PREFIX.tool + text]
}

export function formatToolResult(name: string, ok: boolean, output: string, cols: number, verbose = false): string[] {
  const status = ok ? chalk.green('ok') : chalk.red('error')
  if (verbose) {
    // Verbose: show full output, word-wrapped
    const contentCols = Math.max(20, cols - LABEL_WIDTH - 2)
    const header = CONT_PAD + `${chalk.dim(name)}: ${status}`
    if (!output) return [header]
    const wrapped = wrapText(output, contentCols)
    return [header, ...wrapped.map(l => CONT_PAD + chalk.dim(l))]
  }
  // Normal: single line, truncated
  const maxOutput = Math.max(0, cols - 33)
  const short = output.length > maxOutput
    ? output.slice(0, Math.max(0, maxOutput - 3)) + '...'
    : output
  return [CONT_PAD + `${chalk.dim(name)}: ${status}${short ? ' — ' + chalk.dim(short) : ''}`]
}

export function formatSystem(text: string, cols: number): string[] {
  return formatRole('system', text, cols)
}
