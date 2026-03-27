// AllowlistPolicy implementation — persistent (state/allowlist.json) + session grants.
// loadAllowlistPolicy reads the persistent allowlist at startup.
import { fileExists, readJson, writeJson } from '../store/io.js'
import { parseAllowlistData } from '../store/parse.js'
import type { Layout } from '../types/store.js'
import type { AllowlistPolicy } from '../types/exec.js'

export async function loadAllowlistPolicy(layout: Layout): Promise<AllowlistPolicy> {
  const sessionGrants = new Set<string>()

  // Load persistent allowlist into session grants
  if (await fileExists(layout.state.allowlist)) {
    try {
      const data = parseAllowlistData(await readJson(layout.state.allowlist))
      for (const key of Object.keys(data)) sessionGrants.add(key)
    } catch (e: unknown) {
      // Malformed allowlist — log and proceed with empty grants (don't crash startup)
      console.warn('[exec:allowlist] malformed allowlist.json, ignoring:', String(e))
    }
  }

  return {
    isAllowed: (skillName) => sessionGrants.has(skillName),

    grant: async (skillName, tier) => {
      sessionGrants.add(skillName)
      if (tier !== 'persistent') return

      // Merge into persistent allowlist
      let data: Record<string, true> = {}
      if (await fileExists(layout.state.allowlist)) {
        try { data = parseAllowlistData(await readJson(layout.state.allowlist)) } catch { data = {} }
      }
      data[skillName] = true
      await writeJson(layout.state.allowlist, data)
    },
  }
}
