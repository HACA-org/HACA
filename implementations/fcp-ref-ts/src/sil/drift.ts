// SIL Drift — evaluate drift probes against current memory state.
// Deterministic layer: hash or string match against target file.
// Writes updated scores to state/semantic-digest.json.
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { fileExists, readJson, writeJson, readJsonl } from '../store/io.js'
import { sha256Hex } from '../boot/integrity.js'
import { DriftProbeSchema, SemanticDigestSchema } from '../types/formats/sil.js'
import type { DriftProbe, SemanticDigest, ProbeScore } from '../types/formats/sil.js'
import type { Layout }  from '../types/store.js'
import type { Logger }  from '../types/logger.js'
import type { DriftReport } from '../types/sil.js'

// ─── Probe loading ───────────────────────────────────────────────────────────

export async function loadDriftProbes(layout: Layout): Promise<DriftProbe[]> {
  if (!await fileExists(layout.state.driftProbes)) return []
  try {
    const lines = await readJsonl(layout.state.driftProbes)
    return lines.map(l => DriftProbeSchema.parse(l))
  } catch {
    return []
  }
}

// ─── Probe evaluation ────────────────────────────────────────────────────────

async function evalProbe(probe: DriftProbe, layout: Layout): Promise<DriftReport> {
  const targetPath = path.join(layout.root, probe.target)
  if (!await fileExists(targetPath)) {
    return { probeId: probe.id, layer: 'deterministic', score: 1.0, exceeds: true }
  }

  const content = await fs.readFile(targetPath, 'utf8')

  if (probe.deterministic) {
    const det = probe.deterministic
    let score = 0.0

    if (det.type === 'hash') {
      const actual = sha256Hex(content)
      score = actual !== det.value ? 1.0 : 0.0
    } else if (det.type === 'string') {
      score = content.includes(det.value) ? 0.0 : 1.0
    } else if (det.type === 'pattern') {
      const re = new RegExp(det.value)
      score = re.test(content) ? 0.0 : 1.0
    }

    return { probeId: probe.id, layer: 'deterministic', score, exceeds: score > 0 }
  }

  // Probabilistic fallback: compare against reference string if provided
  if (probe.reference) {
    const lenA = content.length
    const lenB = probe.reference.length
    const maxLen = Math.max(lenA, lenB)
    if (maxLen === 0) return { probeId: probe.id, layer: 'probabilistic', score: 0.0, exceeds: false }
    const score = 1.0 - Math.min(lenA, lenB) / maxLen
    return { probeId: probe.id, layer: 'probabilistic', score, exceeds: score > 0.5 }
  }

  return { probeId: probe.id, layer: 'probabilistic', score: 0.0, exceeds: false }
}

// ─── Digest update ───────────────────────────────────────────────────────────

async function loadDigest(layout: Layout): Promise<SemanticDigest> {
  if (!await fileExists(layout.state.semanticDigest)) {
    return { version: '1.0', lastUpdated: new Date().toISOString(), cyclesEvaluated: 0, probes: {} }
  }
  try {
    return SemanticDigestSchema.parse(await readJson(layout.state.semanticDigest))
  } catch {
    return { version: '1.0', lastUpdated: new Date().toISOString(), cyclesEvaluated: 0, probes: {} }
  }
}

// ─── Public API ──────────────────────────────────────────────────────────────

export async function runDriftEvaluation(layout: Layout, logger: Logger): Promise<DriftReport[]> {
  const probes = await loadDriftProbes(layout)
  if (probes.length === 0) return []

  const reports: DriftReport[] = []
  for (const probe of probes) {
    const report = await evalProbe(probe, layout)
    reports.push(report)
  }

  // Update semantic digest
  const digest = await loadDigest(layout)
  const updatedProbes: Record<string, ProbeScore> = { ...digest.probes }
  for (const r of reports) {
    const prev   = digest.probes[r.probeId]
    const count  = (digest.cyclesEvaluated || 0) + 1
    const mean   = prev ? (prev.meanScore * (count - 1) + r.score) / count : r.score
    const maxVal = prev ? Math.max(prev.maxScore, r.score) : r.score
    updatedProbes[r.probeId] = { lastScore: r.score, meanScore: mean, maxScore: maxVal }
  }

  const updated: SemanticDigest = {
    version:         '1.0',
    lastUpdated:     new Date().toISOString(),
    cyclesEvaluated: (digest.cyclesEvaluated || 0) + 1,
    probes:          updatedProbes,
  }
  await writeJson(layout.state.semanticDigest, updated)

  const exceeding = reports.filter(r => r.exceeds)
  if (exceeding.length > 0) {
    logger.warn('sil:drift_detected', { probes: exceeding.map(r => r.probeId) })
  }

  return reports
}
