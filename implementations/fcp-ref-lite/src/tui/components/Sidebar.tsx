import { Box, Text } from 'ink'
import type { SidebarState } from '../types.js'

interface Props {
  state: SidebarState
  height: number
}

function tokenBar(used: number, total: number, width = 10): string {
  if (total === 0) return '░'.repeat(width)
  const filled = Math.round((used / total) * width)
  return '█'.repeat(filled) + '░'.repeat(width - filled)
}

function shortPath(p: string): string {
  const home = process.env['HOME'] ?? ''
  return home ? p.replace(home, '~') : p
}

function truncate(s: string, max: number): string {
  return s.length > max ? '…' + s.slice(-(max - 1)) : s
}

export function Sidebar({ state, height }: Props) {
  const totalTokens = state.tokensIn + state.tokensOut
  const ctxPct = state.contextWindow > 0
    ? Math.round((totalTokens / state.contextWindow) * 100)
    : 0
  const bar = tokenBar(totalTokens, state.contextWindow)
  const barColor = ctxPct >= 95 ? 'red' : ctxPct >= 90 ? 'yellow' : 'green'

  const focus = state.workspaceFocus ? shortPath(state.workspaceFocus) : '(none)'

  return (
    <Box
      flexDirection="column"
      width={28}
      height={height}
      borderStyle="single"
      borderLeft
      borderTop={false}
      borderBottom={false}
      borderRight={false}
      paddingLeft={1}
    >
      {/* Provider + model */}
      <Text bold>{truncate(`${state.provider}:${state.model}`, 24)}</Text>
      <Text dimColor>↑ {(state.tokensIn / 1000).toFixed(1)}k  ↓ {(state.tokensOut / 1000).toFixed(1)}k</Text>
      <Box>
        <Text color={barColor}>{bar}</Text>
        <Text dimColor>  {ctxPct}%</Text>
      </Box>

      <Text> </Text>

      {/* Workspace */}
      <Text bold dimColor>workspace</Text>
      <Text>{truncate(focus, 24)}</Text>

      <Text> </Text>

      {/* Scope files */}
      <Text bold dimColor>scope</Text>
      {state.scopeFiles.length === 0
        ? <Text dimColor>(none)</Text>
        : state.scopeFiles.slice(0, 5).map(f => (
            <Box key={f.path} justifyContent="space-between">
              <Text>{truncate(f.path.split('/').pop() ?? f.path, 17)}</Text>
              <Text dimColor>[{f.op}]</Text>
            </Box>
          ))
      }

      <Text> </Text>

      {/* Inbox */}
      <Text bold dimColor>inbox</Text>
      {state.inbox.length === 0
        ? <Text dimColor>(empty)</Text>
        : state.inbox.slice(0, 3).map(item => (
            <Box key={item.id}>
              {item.read ? <Text>○ </Text> : <Text color="yellow">● </Text>}
              <Text>{truncate(item.text, 20)}</Text>
            </Box>
          ))
      }

      <Text> </Text>

      {/* Connections */}
      <Text bold dimColor>connections</Text>
      {(
        [
          ['CMI',     state.connections.cmi],
          ['MCP',     state.connections.mcp,     state.connections.mcpClientCount],
          ['Gateway', state.connections.gateway],
          ['Pairing', state.connections.pairing],
        ] as Array<[string, 'online' | 'offline', number?]>
      ).map(([name, status, count]) => (
        <Box key={name} justifyContent="space-between">
          <Text dimColor>{name}</Text>
          <Text color={status === 'online' ? 'green' : 'gray'}>
            {status === 'online' ? '●' : '○'}{' '}
            {status === 'online'
              ? count !== undefined ? `${count} clients` : 'online'
              : 'offline'}
          </Text>
        </Box>
      ))}
    </Box>
  )
}
