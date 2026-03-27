// Single approval gate — called exactly once per tool use.
// Order: persistent allowlist → session grants (via policy) → operator prompt.
import type { AllowDecision, SessionIO } from '../types/session.js'
import type { AllowlistPolicy } from '../types/exec.js'

export async function resolveToolApproval(
  skillName: string,
  input: unknown,
  policy: AllowlistPolicy,
  io: SessionIO,
): Promise<AllowDecision> {
  // 1. Persistent allowlist + session grants — no prompt needed.
  if (policy.isAllowed(skillName)) {
    return { granted: true, tier: 'persistent' }
  }

  // 2. Prompt operator.
  const preview = JSON.stringify(input, null, 2).slice(0, 300)
  io.write(`\nTool request: ${skillName}`)
  io.write(`Input: ${preview}`)
  io.write('Allow? [o]nce / [s]ession / [p]ersistent / [d]eny (default: o): ')
  const answer = (await io.prompt()).trim().toLowerCase()

  if (answer === 'p' || answer === 'persistent') {
    await policy.grant(skillName, 'persistent')
    return { granted: true, tier: 'persistent' }
  }
  if (answer === 's' || answer === 'session') {
    await policy.grant(skillName, 'session')
    return { granted: true, tier: 'session' }
  }
  if (answer === 'd' || answer === 'deny' || answer === 'n') {
    return { granted: false }
  }
  // Default (empty, 'o', 'once', 'y', 'yes') → one-time grant.
  return { granted: true, tier: 'one-time' }
}
