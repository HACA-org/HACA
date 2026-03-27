// Vital check: workspace focus — validate state/workspace_focus.json path safety.
import * as path from 'node:path'
import * as os from 'node:os'
import { fileExists, readJson } from '../../store/io.js'
import type { VitalCheck, HeartbeatContext, VitalResult } from '../../types/sil.js'

const FCP_DIR = path.resolve(os.homedir(), '.fcp')

export const focusCheck: VitalCheck = {
  name: 'workspace_focus',
  async run(ctx: HeartbeatContext): Promise<VitalResult> {
    if (!await fileExists(ctx.layout.state.workspaceFocus)) return { ok: true }

    let focus: string
    try {
      const raw = await readJson(ctx.layout.state.workspaceFocus)
      if (typeof raw !== 'object' || raw === null || typeof (raw as Record<string, unknown>)['path'] !== 'string') {
        return { ok: true }
      }
      focus = (raw as Record<string, string>)['path']!.trim()
    } catch {
      return { ok: true }  // malformed file is non-critical
    }

    const abs        = path.resolve(focus)
    const entityRoot = path.resolve(ctx.layout.root)

    if (abs === entityRoot || abs.startsWith(entityRoot + path.sep)) {
      return {
        ok:       false,
        severity: 'critical',
        message:  `workspace focus is inside entity root: ${abs}`,
      }
    }
    if (entityRoot.startsWith(abs + path.sep)) {
      return {
        ok:       false,
        severity: 'critical',
        message:  `workspace focus is an ancestor of entity root: ${abs}`,
      }
    }
    if (abs === FCP_DIR || abs.startsWith(FCP_DIR + path.sep)) {
      return {
        ok:       false,
        severity: 'critical',
        message:  `workspace focus is inside ~/.fcp: ${abs}`,
      }
    }

    return { ok: true }
  },
}
