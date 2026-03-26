import { Box, Text, useInput } from 'ink'

interface Props {
  title: string
  onClose: () => void
  width?: number
  children: React.ReactNode
}

export function Popup({ title, onClose, width = 70, children }: Props) {
  useInput((_input, key) => {
    if (key.escape) onClose()
  })

  return (
    <Box
      position="absolute"
      flexDirection="column"
      borderStyle="single"
      width={width}
      paddingX={1}
    >
      <Box justifyContent="space-between">
        <Text bold>{title}</Text>
        <Text dimColor>[esc]</Text>
      </Box>
      <Text dimColor>{'─'.repeat(width - 4)}</Text>
      {children}
    </Box>
  )
}
