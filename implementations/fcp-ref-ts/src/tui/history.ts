// Chat history — wraps messages to terminal width and paginates to fit the chat region.
import type { AppMessage } from '../types/tui.js'
import type { TUILayout } from './layout.js'
import { chatLines } from './layout.js'

export interface RenderedLine {
  readonly text: string
  readonly role: AppMessage['role']
}

// Role prefixes (padded for alignment)
const PREFIX: Record<AppMessage['role'], string> = {
  operator:  'You     ',
  assistant: 'Agent   ',
  tool:      'Tool    ',
  system:    'System  ',
}

// Wrap text at maxWidth and return individual lines, all prefixed with `prefix` (first)
// or blank padding for continuation lines.
function wrapMessage(msg: AppMessage, maxWidth: number): RenderedLine[] {
  const prefix      = PREFIX[msg.role] ?? '        '
  const contPad     = ' '.repeat(prefix.length)
  const contentCols = Math.max(1, maxWidth - prefix.length - 3)  // '▎ ' delimiter
  const lines: RenderedLine[] = []

  const words = msg.content.replace(/\r\n/g, '\n').split('\n')
  for (const paragraph of words) {
    if (paragraph.trim() === '') {
      lines.push({ text: '', role: msg.role })
      continue
    }
    let current = ''
    for (const word of paragraph.split(' ')) {
      if (current.length === 0) {
        current = word
      } else if (current.length + 1 + word.length <= contentCols) {
        current += ' ' + word
      } else {
        lines.push({ text: (lines.length === 0 ? prefix : contPad) + '▎ ' + current, role: msg.role })
        current = word
      }
    }
    if (current.length > 0) {
      lines.push({ text: (lines.length === 0 ? prefix : contPad) + '▎ ' + current, role: msg.role })
    }
  }

  return lines.length > 0 ? lines : [{ text: prefix + '▎', role: msg.role }]
}

// Render the last N lines of chat history that fit in the chat region.
export function renderHistory(messages: AppMessage[], layout: TUILayout): RenderedLine[] {
  const maxLines = chatLines(layout)
  const allLines: RenderedLine[] = []

  for (const msg of messages) {
    allLines.push(...wrapMessage(msg, layout.columns))
  }

  // Show only the last `maxLines` lines (virtual scroll at bottom)
  return allLines.slice(-maxLines)
}
