import { Box, Static, Text } from 'ink'
import type { ChatEntry as ChatEntryType } from '../types.js'
import { ChatEntry } from './ChatEntry.js'

interface Props {
  entries: ChatEntryType[]
  height: number
  width: number
}

export function Chat({ entries, height, width }: Props) {
  // Split: completed entries go into <Static> (rendered once, never re-rendered)
  // The last streaming entry (if any) goes into the live area
  const lastEntry = entries[entries.length - 1]
  const isStreaming = lastEntry?.streaming === true

  const staticEntries = isStreaming ? entries.slice(0, -1) : entries
  const liveEntry = isStreaming ? lastEntry : undefined

  return (
    <Box flexDirection="column" height={height} width={width} overflow="hidden">
      {/* Completed entries — rendered once */}
      <Static items={staticEntries}>
        {(entry) => (
          <ChatEntry key={entry.id} entry={entry} focused={false} />
        )}
      </Static>

      {/* Currently streaming entry */}
      {liveEntry && (
        <ChatEntry entry={liveEntry} focused={true} />
      )}

      {/* Empty state */}
      {entries.length === 0 && (
        <Box marginTop={2} marginLeft={2}>
          <Text dimColor>sessão iniciada · digite para começar</Text>
        </Box>
      )}
    </Box>
  )
}
