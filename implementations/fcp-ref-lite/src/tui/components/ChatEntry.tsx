import { Box, Text } from 'ink'
import type { ChatEntry as ChatEntryType } from '../types.js'
import { ToolCall } from './ToolCall.js'

interface Props {
  entry: ChatEntryType
  focused: boolean
}

function roleLabel(role: ChatEntryType['role']): string {
  switch (role) {
    case 'user':   return 'you'
    case 'agent':  return 'agent'
    case 'system': return 'system'
  }
}

function roleColor(role: ChatEntryType['role']): string {
  switch (role) {
    case 'user':   return 'blue'
    case 'agent':  return 'green'
    case 'system': return 'yellow'
  }
}

function shortTime(iso: string): string {
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export function ChatEntry({ entry, focused }: Props) {
  const label = roleLabel(entry.role)
  const color = roleColor(entry.role)
  const time = shortTime(entry.ts)

  return (
    <Box flexDirection="column" marginBottom={1}>
      {/* Header rule: ─ role ─────────── HH:MM ─ */}
      <Box>
        <Text color={color} bold> {label} </Text>
        <Text dimColor>{'─'.repeat(Math.max(0, 42 - label.length - time.length - 4))}</Text>
        <Text dimColor> {time} </Text>
      </Box>

      {/* Tool events (before text, since tools precede agent summary) */}
      {entry.toolEvents.map(te => (
        <ToolCall key={te.id} event={te} focused={focused} />
      ))}

      {/* Text content */}
      {entry.text && (
        <Box marginLeft={1}>
          <Text>{entry.text}{entry.streaming ? <Text color="cyan">▋</Text> : ''}</Text>
        </Box>
      )}

      {/* Streaming with no text yet */}
      {entry.streaming && !entry.text && entry.toolEvents.length === 0 && (
        <Box marginLeft={1}>
          <Text color="cyan">▋</Text>
        </Box>
      )}
    </Box>
  )
}
