// Chat message formatting — converts content into styled terminal lines for
// the scroll region. Replaces history.ts with a simpler line-at-a-time model.
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
    for (const rawWord of paragraph.split(' ')) {
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

const ROLE_PREFIX = {
  operator:  chalk.bold.cyan('You     ') + chalk.dim('▎ '),
  assistant: chalk.bold.green('Agent   ') + chalk.dim('▎ '),
  tool:      chalk.bold.yellow('Tool    ') + chalk.dim('▎ '),
  system:    chalk.bold.dim('System  ') + chalk.dim('▎ '),
} as const

const CONT_PAD = '         ' + chalk.dim('▎ ')  // 8 spaces + ▎

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
  return formatRole('operator', content, cols)
}

export function formatToolUse(name: string, input: unknown, cols: number): string[] {
  const summary = typeof input === 'object' && input !== null
    ? Object.keys(input as Record<string, unknown>).join(', ')
    : String(input ?? '')
  const text = `${chalk.yellow(name)}${summary ? chalk.dim(` (${summary})`) : ''}`
  return [ROLE_PREFIX.tool + text]
}

export function formatToolResult(name: string, ok: boolean, output: string, cols: number): string[] {
  const status = ok ? chalk.green('ok') : chalk.red('error')
  const short = output.length > cols - 30
    ? output.slice(0, cols - 33) + '...'
    : output
  return [CONT_PAD + `${chalk.dim(name)}: ${status}${short ? ' — ' + chalk.dim(short) : ''}`]
}

export function formatSystem(text: string, cols: number): string[] {
  return formatRole('system', text, cols)
}
