import { useState, useEffect } from 'react'
import { Box, Text, useInput } from 'ink'

export interface SlashCommand {
  name: string        // e.g. '/new'
  description: string
  hasPopup?: boolean
}

interface Props {
  query: string       // text after '/', e.g. 'mo' for '/mo'
  commands: SlashCommand[]
  onSelect: (cmd: SlashCommand) => void
  onComplete: (name: string) => void   // Tab — write completed name to input
  onClose: () => void                  // Esc
}

export function SlashMenu({ query, commands, onSelect, onComplete, onClose }: Props) {
  const [selected, setSelected] = useState(0)

  const filtered = commands.filter(c =>
    c.name.toLowerCase().includes(query.toLowerCase())
  )

  // Reset selection when filter changes
  useEffect(() => { setSelected(0) }, [query])

  useInput((_input, key) => {
    if (key.escape) { onClose(); return }
    if (key.upArrow) {
      setSelected(i => (i - 1 + filtered.length) % filtered.length)
      return
    }
    if (key.downArrow) {
      setSelected(i => (i + 1) % filtered.length)
      return
    }
    if (key.tab && filtered[selected]) {
      onComplete(filtered[selected]!.name)
      return
    }
    if (key.return && filtered[selected]) {
      onSelect(filtered[selected]!)
      return
    }
  })

  if (filtered.length === 0) return null

  return (
    <Box
      flexDirection="column"
      borderStyle="single"
      marginBottom={0}
      paddingX={1}
    >
      <Text dimColor>commands</Text>
      {filtered.slice(0, 8).map((cmd, i) => (
        <Box key={cmd.name}>
          {i === selected
            ? <Text color="cyan">▶ <Text bold>{cmd.name}</Text>{'  '}<Text dimColor>{cmd.description}</Text>{cmd.hasPopup ? <Text dimColor> ↗</Text> : null}</Text>
            : <Text>{'  '}{cmd.name}{'  '}<Text dimColor>{cmd.description}</Text>{cmd.hasPopup ? <Text dimColor> ↗</Text> : null}</Text>
          }
        </Box>
      ))}
      {filtered.length > 8 && (
        <Text dimColor>  +{filtered.length - 8} more</Text>
      )}
      <Text dimColor>[↑↓ navegar · tab completar · enter selecionar · esc fechar]</Text>
    </Box>
  )
}
