// AllowlistPolicy — 3-namespace persistent + session allowlist.
// Backed by state/allowlist.json. Operator can edit the file directly.
import { fileExists, readJson, writeJson } from '../store/io.js'
import { parseAllowlistData } from '../store/parse.js'
import type { Layout } from '../types/store.js'
import type { AllowlistPolicy } from '../types/exec.js'

export async function loadAllowlistPolicy(layout: Layout): Promise<AllowlistPolicy> {
  const sessionCommands = new Set<string>()
  const sessionDomains  = new Set<string>()
  const sessionSkills   = new Set<string>()

  // Load persistent allowlist into session sets
  if (await fileExists(layout.state.allowlist)) {
    try {
      const data = parseAllowlistData(await readJson(layout.state.allowlist))
      for (const c of data.commands) sessionCommands.add(c)
      for (const d of data.domains)  sessionDomains.add(d)
      for (const s of data.skills)   sessionSkills.add(s)
    } catch (e: unknown) {
      // Malformed allowlist — log and proceed with empty grants (don't crash startup)
      console.warn('[exec:allowlist] malformed allowlist.json, ignoring:', String(e))
    }
  }

  async function persistCurrent(): Promise<void> {
    await writeJson(layout.state.allowlist, {
      commands: [...sessionCommands],
      domains:  [...sessionDomains],
      skills:   [...sessionSkills],
    })
  }

  return {
    get commands() { return [...sessionCommands] },
    get domains()  { return [...sessionDomains] },
    get skills()   { return [...sessionSkills] },

    async addCommand(cmd, tier) {
      sessionCommands.add(cmd)
      if (tier === 'persistent') await persistCurrent()
    },
    async addDomain(domain, tier) {
      sessionDomains.add(domain)
      if (tier === 'persistent') await persistCurrent()
    },
    async addSkill(skill, tier) {
      sessionSkills.add(skill)
      if (tier === 'persistent') await persistCurrent()
    },
  }
}
