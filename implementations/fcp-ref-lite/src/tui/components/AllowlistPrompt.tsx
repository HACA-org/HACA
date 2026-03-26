import { useState } from 'react'
import { Box, Text, useInput } from 'ink'
import type { AllowlistPrompt as AllowlistPromptType, AllowDecision } from '../types.js'

interface Props {
  prompt: AllowlistPromptType
}

const OPTIONS: Array<{ label: string; value: AllowDecision }> = [
  { label: 'allow once',         value: 'once'    },
  { label: 'allow this session', value: 'session' },
  { label: 'add to allowlist',   value: 'persist' },
  { label: 'deny',               value: 'deny'    },
]

export function AllowlistPrompt({ prompt }: Props) {
  const [selected, setSelected] = useState(0)

  useInput((_input, key) => {
    if (key.upArrow) {
      setSelected(i => (i - 1 + OPTIONS.length) % OPTIONS.length)
    } else if (key.downArrow) {
      setSelected(i => (i + 1) % OPTIONS.length)
    } else if (key.return) {
      const opt = OPTIONS[selected]
      if (opt) prompt.resolve(opt.value)
    }
  })

  // Format input preview (truncate long values)
  const inputPreview = JSON.stringify(prompt.toolInput).slice(0, 80)

  return (
    <Box flexDirection="column" marginLeft={1} marginBottom={1}>
      <Box>
        <Text color="yellow">⏸ </Text>
        <Text bold>{prompt.toolName}  </Text>
        <Text dimColor>{inputPreview}{inputPreview.length >= 80 ? '…' : ''}</Text>
      </Box>
      <Box flexDirection="column" marginLeft={2} borderStyle="single" paddingX={1} marginTop={0}>
        <Text dimColor>permissão necessária</Text>
        <Text> </Text>
        {OPTIONS.map((opt, i) => (
          <Box key={opt.value}>
            {i === selected
              ? <Text color="cyan">▶ {opt.label}</Text>
              : <Text>  {opt.label}</Text>
            }
          </Box>
        ))}
        <Text> </Text>
        <Text dimColor>[↑↓ navegar · enter confirmar]</Text>
      </Box>
    </Box>
  )
}
