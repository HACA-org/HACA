// Interactive selection with arrow key navigation.
// Uses raw terminal control to capture arrow keys without waiting for Enter.
import chalk from 'chalk'

export interface SelectOption {
  label: string
  description?: string
}

/**
 * Interactive arrow-key selection.
 * Supports: ↑↓ to navigate, Enter to select, q/Ctrl-C to cancel.
 */
export async function selectInteractive(
  question: string,
  options: SelectOption[],
  defaultIdx = 0,
): Promise<{ index: number; label: string }> {
  if (options.length === 0) throw new Error('selectInteractive: no options provided')

  let selectedIdx = Math.min(defaultIdx, options.length - 1)
  const stdin = process.stdin
  const stdout = process.stdout

  // Display question
  stdout.write(`\n${question}\n`)

  // Set up raw mode
  stdin.setRawMode(true)
  stdin.resume()
  stdin.setEncoding('utf8')

  return new Promise(resolve => {
    function renderOption(idx: number): string {
      const opt = options[idx]!
      const num = chalk.dim(`${idx + 1}.`)
      if (idx === selectedIdx) {
        const label = chalk.cyan(`▸ ${opt.label}`)
        const desc = opt.description ? chalk.dim(` — ${opt.description}`) : ''
        return `  ${num} ${label}${desc}`
      } else {
        const label = opt.label
        const desc = opt.description ? chalk.dim(` — ${opt.description}`) : ''
        return `  ${num}   ${label}${desc}`
      }
    }

    function redraw() {
      // Move cursor up to the first option line
      stdout.write(`\x1b[${options.length}A`)
      // Clear all option lines and redraw them
      for (let i = 0; i < options.length; i++) {
        stdout.write('\r\x1b[K')
        stdout.write(renderOption(i))
        if (i < options.length - 1) {
          stdout.write('\n')
        }
      }
    }

    function cleanup() {
      stdin.removeListener('data', dataHandler!)
      stdin.setRawMode(false)
      stdin.pause()
      stdout.write('\x1b[?25h') // show cursor
    }

    let buffer = ''
    let dataHandler: ((chunk: string) => void) | null = null

    dataHandler = (chunk: string) => {
      buffer += chunk

      while (buffer.length > 0) {
        // Check for arrow keys first (3-byte sequences)
        if (buffer.startsWith('\x1b[A')) {
          // Up arrow
          selectedIdx = (selectedIdx - 1 + options.length) % options.length
          redraw()
          buffer = buffer.slice(3)
          continue
        }

        if (buffer.startsWith('\x1b[B')) {
          // Down arrow
          selectedIdx = (selectedIdx + 1) % options.length
          redraw()
          buffer = buffer.slice(3)
          continue
        }

        const char = buffer[0]!

        // Ctrl-C
        if (char === '\x03') {
          cleanup()
          resolve({ index: defaultIdx, label: options[defaultIdx]!.label })
          return
        }

        // 'q' to quit
        if (char.toLowerCase() === 'q') {
          cleanup()
          resolve({ index: defaultIdx, label: options[defaultIdx]!.label })
          return
        }

        // Enter (CR or LF)
        if (char === '\r' || char === '\n') {
          cleanup()
          stdout.write(`\n${chalk.dim('Selected:')} ${chalk.cyan(options[selectedIdx]!.label)}\n\n`)
          resolve({ index: selectedIdx, label: options[selectedIdx]!.label })
          return
        }

        // Number input (1-9)
        const num = parseInt(char, 10)
        if (!isNaN(num) && num >= 1 && num <= options.length) {
          selectedIdx = num - 1
          redraw()
          buffer = buffer.slice(1)
          continue
        }

        // Unknown character, skip it
        buffer = buffer.slice(1)
      }
    }

    stdin.on('data', dataHandler)

    // Initial render
    stdout.write('\x1b[?25l') // hide cursor
    for (let i = 0; i < options.length; i++) {
      stdout.write(renderOption(i))
      if (i < options.length - 1) {
        stdout.write('\n')
      }
    }
  })
}
