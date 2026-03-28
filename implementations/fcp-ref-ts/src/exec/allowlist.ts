// AllowlistPolicy — 3-namespace persistent + session allowlist.
// Backed by state/allowlist.json. Operator can edit the file directly.
//
// Invariant: session-only grants are never written to disk.
// persistCurrent() only serialises the persistent sets, not the session sets.
import { fileExists, readJson, writeJson } from '../store/io.js'
import { parseAllowlistData } from '../store/parse.js'
import type { Layout } from '../types/store.js'
import type { AllowlistPolicy } from '../types/exec.js'

export async function loadAllowlistPolicy(layout: Layout): Promise<AllowlistPolicy> {
  // Persistent grants — survive across sessions (backed by allowlist.json)
  const persistCommands = new Set<string>()
  const persistDomains  = new Set<string>()
  const persistSkills   = new Set<string>()

  // Session-only grants — discarded at process exit, never written to disk
  const sessionCommands = new Set<string>()
  const sessionDomains  = new Set<string>()
  const sessionSkills   = new Set<string>()

  // Load persistent allowlist
  if (await fileExists(layout.state.allowlist)) {
    try {
      const data = parseAllowlistData(await readJson(layout.state.allowlist))
      for (const c of data.commands) persistCommands.add(c)
      for (const d of data.domains)  persistDomains.add(d)
      for (const s of data.skills)   persistSkills.add(s)
    } catch (e: unknown) {
      // Malformed allowlist — log and proceed with empty grants (don't crash startup)
      console.warn('[exec:allowlist] malformed allowlist.json, ignoring:', String(e))
    }
  }

  async function persistCurrent(): Promise<void> {
    // Only write persistent sets — never session-only grants
    await writeJson(layout.state.allowlist, {
      commands: [...persistCommands],
      domains:  [...persistDomains],
      skills:   [...persistSkills],
    })
  }

  return {
    get commands() { return [...persistCommands, ...sessionCommands] },
    get domains()  { return [...persistDomains,  ...sessionDomains] },
    get skills()   { return [...persistSkills,   ...sessionSkills] },

    async addCommand(cmd, tier) {
      if (tier === 'persistent') {
        persistCommands.add(cmd)
        await persistCurrent()
      } else {
        sessionCommands.add(cmd)
      }
    },
    async addDomain(domain, tier) {
      if (tier === 'persistent') {
        persistDomains.add(domain)
        await persistCurrent()
      } else {
        sessionDomains.add(domain)
      }
    },
    async addSkill(skill, tier) {
      if (tier === 'persistent') {
        persistSkills.add(skill)
        await persistCurrent()
      } else {
        sessionSkills.add(skill)
      }
    },
  }
}
