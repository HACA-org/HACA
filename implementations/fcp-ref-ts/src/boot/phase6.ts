// Phase 6: Critical Condition Check — distress beacon, pending proposals, drift probes.
//
// Boot is blocked until:
//   1. distress.beacon is absent
//   2. All evolution proposals are approved or rejected (interactive gate)
//   3. No drift probes exceed their threshold
//
// Proposals that were pending at the end of the previous session are reviewed
// interactively here before the entity is allowed to start. Drift probe failures
// require manual operator resolution — they do not have an interactive gate.
import { fileExists } from '../store/io.js'
import { loadDriftProbes, runDriftEvaluation } from '../sil/drift.js'
import { readPendingProposals } from '../sil/endure.js'
import { runProposalGate } from './proposal-gate.js'
import { BootError } from '../types/boot.js'
import type { BootPhase, BootContext } from '../types/boot.js'

export const phase6: BootPhase = {
  id:   6,
  name: 'vital-status',
  async run(ctx: BootContext): Promise<void> {
    const { layout, logger } = ctx

    // ── 1. Distress beacon ────────────────────────────────────────────────────
    if (await fileExists(layout.state.distressBeacon)) {
      throw new BootError(
        6,
        'Distress beacon is active — resolve the condition and remove state/distress.beacon before booting',
      )
    }

    // ── 2. Pending proposals gate ─────────────────────────────────────────────
    // If any proposals are unapproved, present the interactive gate.
    // The gate persists decisions and returns; BootError is thrown only if the
    // gate throws (e.g. UserCancelledError from Ctrl-C mid-review).
    const allProposals = await readPendingProposals(layout)
    const unapproved   = allProposals.filter(p => !p.approvedAt)
    if (unapproved.length > 0) {
      try {
        await runProposalGate(layout, logger)
      } catch (e: unknown) {
        throw new BootError(
          6,
          'Boot aborted — all evolution proposals must be reviewed before the entity can start',
          e,
        )
      }
    }

    // ── 3. Drift probes ───────────────────────────────────────────────────────
    // Re-evaluate probes against current files. If any exceed their threshold,
    // the operator must resolve the drift before booting.
    const probes = await loadDriftProbes(layout)
    if (probes.length > 0) {
      const reports = await runDriftEvaluation(layout, logger)
      const failing = reports.filter(r => r.exceeds)
      if (failing.length > 0) {
        const ids = failing.map(r => r.probeId).join(', ')
        throw new BootError(
          6,
          `Drift detected in probe(s): ${ids} — resolve the drift and retry boot`,
        )
      }
    }

    logger.info('boot:phase6:ok')
  },
}
