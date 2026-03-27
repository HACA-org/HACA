// Loop detection via tool-use fingerprinting.
// If the same fingerprint appears twice in a session, a tool loop is detected.
import { createHash } from 'node:crypto'
import type { ToolUseBlock } from '../types/cpe.js'

// Returns a 16-char hex fingerprint of the tool-use pattern in one CPE cycle.
export function makeFingerprint(toolUses: ToolUseBlock[]): string {
  const pattern = toolUses.map(tu => ({
    name:      tu.name,
    inputHash: createHash('sha256').update(JSON.stringify(tu.input)).digest('hex').slice(0, 8),
  }))
  return createHash('sha256').update(JSON.stringify(pattern)).digest('hex').slice(0, 16)
}
