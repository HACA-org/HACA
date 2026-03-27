// Single approval gate — called by tool handlers that require operator authorization.
// Two modes differ in available options: some tools cannot be added to allowlist.
import type { AllowDecision } from '../types/session.js'
import type { GateIO } from '../types/exec.js'

export type ApprovalMode =
  | 'once-session-deny'            // file-read (outside ws), file-write, agent-run
  | 'once-session-allowlist-deny'  // shell-run, web-fetch, skill-create

export async function resolveToolApproval(
  description: string,
  mode:        ApprovalMode,
  io:          GateIO,
): Promise<AllowDecision> {
  io.write(`\nApproval required: ${description}`)

  if (mode === 'once-session-deny') {
    io.write('Allow? [o]nce / [s]ession / [d]eny (default: o): ')
  } else {
    io.write('Allow? [o]nce / [s]ession / [a]dd-to-allowlist / [d]eny (default: o): ')
  }

  const answer = (await io.prompt()).trim().toLowerCase()

  if (answer === 'd' || answer === 'deny' || answer === 'n') {
    return { granted: false }
  }
  if (answer === 's' || answer === 'session') {
    return { granted: true, tier: 'session' }
  }
  if (mode === 'once-session-allowlist-deny' && (answer === 'a' || answer === 'allowlist')) {
    return { granted: true, tier: 'persistent' }
  }
  // Default (empty, 'o', 'once', 'y', 'yes') → one-time
  return { granted: true, tier: 'one-time' }
}
