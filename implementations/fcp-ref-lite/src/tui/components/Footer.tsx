import { Box, Text } from 'ink'
import type { FooterState, AgentState } from '../types.js'

interface Props {
  state: FooterState
  ctrlCPending: boolean
  terminalWidth: number
}

function stateLabel(s: AgentState, activeTool: string | null): string {
  switch (s) {
    case 'idle':              return 'idle'
    case 'thinking':          return 'thinking'
    case 'tool':              return `tool:${activeTool ?? '?'}` as string
    case 'sleeping':          return 'sleeping'
    case 'awaiting_approval': return '⏸ awaiting approval'
  }
}

function stateColor(s: AgentState): string {
  switch (s) {
    case 'idle':              return 'green'
    case 'thinking':          return 'cyan'
    case 'tool':              return 'yellow'
    case 'sleeping':          return 'magenta'
    case 'awaiting_approval': return 'red'
  }
}

function elapsed(startIso: string): string {
  const ms = Date.now() - new Date(startIso).getTime()
  const s = Math.floor(ms / 1000)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return [h, m, sec].map(n => String(n).padStart(2, '0')).join(':')
}

export function Footer({ state, ctrlCPending, terminalWidth }: Props) {
  if (ctrlCPending) {
    return (
      <Box width={terminalWidth} borderStyle="single" borderTop borderBottom={false} borderLeft={false} borderRight={false}>
        <Text color="yellow">⚠ pressione ctrl+c novamente para fechar  </Text>
        <Text dimColor>(sem closure payload)</Text>
      </Box>
    )
  }

  const label = stateLabel(state.agentState, state.activeTool)
  const color = stateColor(state.agentState)
  const shortId = state.sessionId.slice(0, 8)
  const time = elapsed(state.sessionStartTs)

  const parts: Array<{ text: string; color?: string; dim?: boolean }> = [
    { text: label, color },
    { text: `cycle ${state.cycleCount}` },
    { text: shortId, dim: true },
    { text: time, dim: true },
    { text: state.profile, color: state.profile === 'haca-core' ? 'blue' : 'magenta' },
    { text: `v${state.version}`, dim: true },
  ]

  if (state.verbose) parts.push({ text: 'verbose', color: 'yellow' })
  if (state.debug)   parts.push({ text: 'debug',   color: 'red' })

  return (
    <Box width={terminalWidth} borderStyle="single" borderTop borderBottom={false} borderLeft={false} borderRight={false}>
      {parts.map((p, i) => (
        <Box key={i}>
          {i > 0 && <Text dimColor> · </Text>}
          {p.color
            ? <Text color={p.color} dimColor={p.dim ?? false}>{p.text}</Text>
            : <Text dimColor={p.dim ?? false}>{p.text}</Text>
          }
        </Box>
      ))}
    </Box>
  )
}
