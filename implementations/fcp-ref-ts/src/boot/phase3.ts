// Phase 3: Integrity Verification — compare tracked file hashes vs. state/integrity.json.
import * as path from 'node:path'
import { fileExists, readJson } from '../store/io.js'
import { parseIntegrityDocument } from '../store/parse.js'
import { sha256File } from './integrity.js'
import { BootError } from '../types/boot.js'
import type { BootPhase, BootContext } from '../types/boot.js'

export const phase3: BootPhase = {
  id:   3,
  name: 'integrity-check',
  async run(ctx: BootContext): Promise<void> {
    const { layout, logger } = ctx

    if (!await fileExists(layout.state.integrity)) {
      throw new BootError(3, 'state/integrity.json not found — run fcp doctor --fix')
    }

    const raw = await readJson(layout.state.integrity)
    const doc = parseIntegrityDocument(raw)

    const drifted: string[] = []
    for (const [rel, expected] of Object.entries(doc.files)) {
      const abs = path.join(layout.root, rel)
      if (!await fileExists(abs)) continue
      const actual = await sha256File(abs)
      if (actual !== expected) {
        logger.error('boot:phase3:hash-mismatch', { file: rel })
        drifted.push(rel)
      }
    }

    if (drifted.length > 0) {
      throw new BootError(3, `Identity drift detected in: ${drifted.join(', ')}`)
    }

    logger.info('boot:phase3:ok', { checked: Object.keys(doc.files).length })
  },
}
