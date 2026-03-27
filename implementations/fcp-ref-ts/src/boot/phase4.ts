// Phase 4: Skill Index Validation — verify skills/index.json exists and is well-formed.
import { fileExists, readJson } from '../store/io.js'
import { parseSkillIndex } from '../store/parse.js'
import { BootError } from '../types/boot.js'
import type { BootPhase, BootContext } from '../types/boot.js'

export const phase4: BootPhase = {
  id:   4,
  name: 'skill-index-seal',
  async run(ctx: BootContext): Promise<void> {
    const { layout, logger } = ctx

    if (!await fileExists(layout.skills.index)) {
      throw new BootError(4, 'skills/index.json not found — run fcp doctor --fix')
    }

    const raw = await readJson(layout.skills.index)
    const index = parseSkillIndex(raw)

    logger.info('boot:phase4:ok', { skills: index.skills.length })
  },
}
