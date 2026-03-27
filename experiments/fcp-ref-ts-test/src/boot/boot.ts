import { existsSync } from 'node:fs'
import { randomUUID } from 'node:crypto'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import type { Layout } from '../store/layout.js'
import { readJson, readJsonl, touchFile, removeFile } from '../store/io.js'
import { BootError, type BootResult, type ImprintRecord, type ContextWindowConfig } from './types.js'
import type { Message } from '../cpe/types.js'
import { runFAP } from './fap.js'
import type { Logger } from '../logger/logger.js'

function sha256(data: string): string {
  return 'sha256:' + createHash('sha256').update(data, 'utf8').digest('hex')
}

async function hashFile(path: string): Promise<string> {
  const raw = await readFile(path, 'utf8')
  return sha256(raw)
}

// Pre-requisite: distress beacon check
function checkBeacon(layout: Layout): void {
  if (existsSync(layout.distressBeacon)) {
    throw new BootError(
      'Distress beacon is active. Resolve the issue and remove distress.beacon before booting.',
      'beacon'
    )
  }
}

// Phase 0: Operator bound verification
async function phase0(layout: Layout): Promise<ImprintRecord> {
  if (!existsSync(layout.imprint)) {
    throw new BootError('imprint.json not found — run fcp init', 'phase0')
  }
  try {
    const imprint = await readJson<ImprintRecord>(layout.imprint)
    if (!imprint.operatorBound?.hash) {
      throw new BootError('imprint.json is missing operator bound', 'phase0')
    }
    return imprint
  } catch (err) {
    if (err instanceof BootError) throw err
    throw new BootError(`imprint.json is invalid: ${String(err)}`, 'phase0')
  }
}

// Phase 1: Host introspection
async function phase1(layout: Layout, profile: 'haca-core' | 'haca-evolve'): Promise<void> {
  if (!existsSync(layout.baseline)) {
    throw new BootError('state/baseline.json not found', 'phase1')
  }
  const baseline = await readJson<{ cpe?: { topology?: string } }>(layout.baseline)
  const topology = baseline.cpe?.topology ?? 'transparent'
  if (profile === 'haca-core' && topology !== 'transparent') {
    throw new BootError('haca-core requires transparent topology', 'phase1')
  }
}

// Phase 2: Crash recovery
async function phase2(layout: Layout, logger: Logger): Promise<boolean> {
  if (!existsSync(layout.sessionToken)) return false

  await logger.warn('boot', 'crash_detected')
  await logger.increment('crashes')

  // Remove stale token — sleep cycle will be handled by session/sleep
  // For now: clear token and flag crash for session loop to handle
  await removeFile(layout.sessionToken)
  await logger.info('boot', 'crash_recovery_complete')
  return true
}

// Phase 3: Integrity verification
async function phase3(layout: Layout): Promise<void> {
  if (!existsSync(layout.integrity)) {
    throw new BootError('state/integrity.json not found', 'phase3')
  }

  // Canonical schema: { version, algorithm, files: { 'relative/path' -> hash } }
  const doc = await readJson<{ files?: Record<string, string> }>(layout.integrity)
  const files = doc.files ?? {}

  for (const [rel, expectedHash] of Object.entries(files)) {
    const absPath = rel.startsWith('/') ? rel : `${layout.root}/${rel}`
    if (!existsSync(absPath)) continue
    const actualHash = await hashFile(absPath)
    if (actualHash !== expectedHash) {
      throw new BootError(`Identity drift detected in ${rel}`, 'phase3')
    }
  }
}

// Phase 4: Skill index resolution
async function phase4(layout: Layout): Promise<void> {
  if (!existsSync(layout.skillsIndex)) {
    throw new BootError('skills/index.json not found', 'phase4')
  }
  try {
    await readJson(layout.skillsIndex)
  } catch {
    throw new BootError('skills/index.json is invalid', 'phase4')
  }
}

// Reconstruct conversation history from session.jsonl (after last session_reset)
async function loadHistory(layout: Layout): Promise<Message[]> {
  if (!existsSync(layout.sessionStore)) return []
  try {
    const events = await readJsonl<Record<string, unknown>>(layout.sessionStore)
    // Find last session_reset marker
    let startIdx = 0
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i]?.['type'] === 'session_reset') { startIdx = i + 1; break }
    }
    const messages: Message[] = []
    for (const ev of events.slice(startIdx)) {
      if (ev['type'] === 'message' && (ev['role'] === 'user' || ev['role'] === 'assistant')) {
        messages.push({ role: ev['role'] as 'user' | 'assistant', content: ev['content'] as Message['content'] })
      }
    }
    return messages
  } catch {
    return []
  }
}

// Read context window config from baseline.json
async function loadContextWindowConfig(layout: Layout): Promise<ContextWindowConfig> {
  const defaults: ContextWindowConfig = { warnPct: 0.90, compactPct: 0.95 }
  if (!existsSync(layout.baseline)) return defaults
  try {
    const baseline = await readJson<{ context_window?: { warn_pct?: number; compact_pct?: number } }>(layout.baseline)
    return {
      warnPct: baseline.context_window?.warn_pct ?? defaults.warnPct,
      compactPct: baseline.context_window?.compact_pct ?? defaults.compactPct,
    }
  } catch {
    return defaults
  }
}

// Phase 6: Critical condition check (simplified — full implementation after SIL)
async function phase6(_layout: Layout): Promise<[]> {
  // TODO: check sil.log for DRIFT_FAULT, IDENTITY_DRIFT, SIL_UNRESPONSIVE, SEVERANCE_PENDING
  return []
}

// Phase 7: Session token issuance
async function phase7(layout: Layout): Promise<string> {
  const sessionId = randomUUID()
  await touchFile(layout.sessionToken)
  return sessionId
}

export async function runBoot(
  layout: Layout,
  logger: Logger,
): Promise<BootResult> {
  await logger.info('boot', 'start')

  // Detect FAP (cold-start)
  const isFirstBoot = !existsSync(layout.imprint)

  const contextWindowConfig = await loadContextWindowConfig(layout)

  if (isFirstBoot) {
    // Profile is embedded in baseline if pre-configured, otherwise default to haca-core
    let profile: 'haca-core' | 'haca-evolve' = 'haca-core'
    if (existsSync(layout.baseline)) {
      const baseline = await readJson<{ haca_profile?: string }>(layout.baseline).catch(() => ({}))
      if ((baseline as Record<string, unknown>)['haca_profile'] === 'haca-evolve') {
        profile = 'haca-evolve'
      }
    }
    const sessionId = await runFAP(layout, profile, logger)
    await logger.increment('sessions')
    return { sessionId, isFirstBoot: true, crashRecovered: false, pendingProposals: [], history: [], contextWindowConfig }
  }

  // Warm boot
  checkBeacon(layout)
  await logger.info('boot', 'phase0_start')
  const imprint = await phase0(layout)

  await logger.info('boot', 'phase1_start')
  await phase1(layout, imprint.hacaProfile)

  await logger.info('boot', 'phase2_start')
  const crashRecovered = await phase2(layout, logger)

  await logger.info('boot', 'phase3_start')
  await phase3(layout)

  await logger.info('boot', 'phase4_start')
  await phase4(layout)

  await logger.info('boot', 'phase6_start')
  const pendingProposals = await phase6(layout)

  await logger.info('boot', 'phase7_start')
  const sessionId = await phase7(layout)

  const history = await loadHistory(layout)

  await logger.info('boot', 'complete', { sessionId, historyMessages: history.length })
  await logger.increment('sessions')

  return { sessionId, isFirstBoot: false, crashRecovered, pendingProposals, history, contextWindowConfig }
}
