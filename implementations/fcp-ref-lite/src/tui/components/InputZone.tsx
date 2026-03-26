import { useState } from 'react'
import { Box, Text, useInput } from 'ink'
import TextInput from 'ink-text-input'
import { SlashMenu } from './SlashMenu.js'
import { AllowlistPrompt } from './AllowlistPrompt.js'
import type { InputMode, AllowlistPrompt as AllowlistPromptType } from '../types.js'
import type { SlashCommand } from './SlashMenu.js'

interface Props {
  mode: InputMode
  allowlistPrompt: AllowlistPromptType | null
  commands: SlashCommand[]
  onSubmit: (text: string) => void
  onSlashCommand: (cmd: SlashCommand) => void
  onStop: () => void        // ctrl+x
  onCtrlC: () => void       // ctrl+c
  width: number
}

export function InputZone({
  mode,
  allowlistPrompt,
  commands,
  onSubmit,
  onSlashCommand,
  onStop,
  onCtrlC,
  width,
}: Props) {
  const [value, setValue] = useState('')

  const isSlash = value.startsWith('/') && mode !== 'allowlist' && mode !== 'locked' && mode !== 'popup'
  const slashQuery = isSlash ? value.slice(1) : ''

  useInput((_input, key) => {
    if (mode === 'allowlist' || mode === 'locked' || mode === 'popup') return
    if (key.ctrl && _input === 'x') { onStop(); return }
    if (key.ctrl && _input === 'c') { onCtrlC(); return }
  })

  function handleSubmit(text: string) {
    if (!text.trim()) return
    setValue('')
    onSubmit(text.trim())
  }

  function handleSlashSelect(cmd: SlashCommand) {
    setValue('')
    onSlashCommand(cmd)
  }

  function handleSlashComplete(name: string) {
    setValue(name + ' ')
  }

  function handleSlashClose() {
    setValue('')
  }

  const inputDisabled = mode === 'allowlist' || mode === 'locked' || mode === 'popup'

  return (
    <Box flexDirection="column" width={width}>
      {/* Allowlist prompt — shown inline above input */}
      {allowlistPrompt && mode === 'allowlist' && (
        <AllowlistPrompt prompt={allowlistPrompt} />
      )}

      {/* Slash menu — shown above input when typing / */}
      {isSlash && mode === 'normal' && (
        <SlashMenu
          query={slashQuery}
          commands={commands}
          onSelect={handleSlashSelect}
          onComplete={handleSlashComplete}
          onClose={handleSlashClose}
        />
      )}

      {/* Input line */}
      <Box>
        <Text bold color={inputDisabled ? 'gray' : 'cyan'}>{inputDisabled ? '  ' : '> '}</Text>
        {inputDisabled
          ? <Text dimColor>aguardando...</Text>
          : (
            <TextInput
              value={value}
              onChange={setValue}
              onSubmit={handleSubmit}
              placeholder="mensagem ou /comando"
            />
          )
        }
      </Box>
    </Box>
  )
}
