import { useState } from 'react'
import { Box, Text, useInput } from 'ink'
import type { ToolEvent } from '../types.js'

interface Props {
  event: ToolEvent
  focused: boolean   // only the focused entry receives ctrl+o
}

function statusIcon(s: ToolEvent['status']): string {
  switch (s) {
    case 'pending':     return '○'
    case 'running':     return '⟳'
    case 'done':        return '✓'
    case 'error':       return '✗'
    case 'denied':      return '⊘'
    case 'interrupted': return '⊘'
  }
}

function statusColor(s: ToolEvent['status']): string {
  switch (s) {
    case 'pending':     return 'gray'
    case 'running':     return 'cyan'
    case 'done':        return 'green'
    case 'error':       return 'red'
    case 'denied':      return 'red'
    case 'interrupted': return 'yellow'
  }
}

function DiffView({ diff }: { diff: string }) {
  return (
    <Box flexDirection="column" marginLeft={2}>
      <Text dimColor>{'┄'.repeat(40)}</Text>
      {diff.split('\n').map((line, i) => {
        if (line.startsWith('+')) return <Text key={i} color="green">{line}</Text>
        if (line.startsWith('-')) return <Text key={i} color="red">{line}</Text>
        if (line.startsWith('@@')) return <Text key={i} color="cyan">{line}</Text>
        return <Text key={i}>{line}</Text>
      })}
      <Text dimColor>{'┄'.repeat(40)}</Text>
      <Text dimColor>[ctrl+o to collapse]</Text>
    </Box>
  )
}

function MemoryView({ slug, preview }: { slug: string; preview: string }) {
  return (
    <Box flexDirection="column" marginLeft={2}>
      <Text dimColor>slug: <Text color="cyan">{slug}</Text></Text>
      <Text dimColor>"{preview}{preview.length >= 120 ? '…' : ''}"</Text>
    </Box>
  )
}

export function ToolCall({ event, focused }: Props) {
  const [expanded, setExpanded] = useState(false)

  const hasDiff = event.type === 'fileWrite' && !!event.diff
  const hasDetail = hasDiff || event.type === 'memory'
  const canExpand = hasDetail && event.status === 'done'

  useInput((_input, key) => {
    if (!focused || !canExpand) return
    if (key.ctrl && _input === 'o') {
      setExpanded(e => !e)
    }
  })

  const icon = statusIcon(event.status)
  const color = statusColor(event.status)

  // Build summary line
  let summary = ''
  if (event.type === 'fileRead' || event.type === 'fileWrite') {
    summary = event.filePath ?? ''
  } else if (event.type === 'webFetch') {
    summary = event.url ?? ''
    if (event.httpStatus) summary += `  ${event.httpStatus}`
  } else if (event.type === 'memory') {
    summary = event.memorySlug ? `episodic · ${event.memorySlug}` : 'episodic'
  } else if (event.type === 'shellRun') {
    summary = event.summary ?? ''
  } else {
    summary = event.summary ?? ''
  }

  const expandHint = canExpand
    ? (expanded ? ' [ctrl+o]' : ' [ctrl+o to expand]')
    : ''

  return (
    <Box flexDirection="column" marginLeft={1}>
      <Box>
        <Text color={color}>{expanded ? '▼' : '▶'} </Text>
        <Text dimColor>{event.name}  </Text>
        <Text>{summary}</Text>
        {event.status === 'running' && <Text color="cyan">  ⟳</Text>}
        {canExpand && <Text dimColor>{expandHint}</Text>}
        {event.error && <Text color="red">  {event.error}</Text>}
        {event.status === 'interrupted' && <Text color="yellow">  interrompido pelo operador</Text>}
        {event.status === 'denied' && <Text color="red">  negado pelo operador</Text>}
      </Box>

      {expanded && hasDiff && event.diff && <DiffView diff={event.diff} />}
      {expanded && event.type === 'memory' && event.memorySlug && (
        <MemoryView slug={event.memorySlug} preview={event.memoryPreview ?? ''} />
      )}
    </Box>
  )
}
