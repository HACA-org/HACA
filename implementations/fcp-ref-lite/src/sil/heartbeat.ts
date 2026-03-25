import { existsSync } from 'node:fs'
import { readdir } from 'node:fs/promises'
import { join } from 'node:path'
import { homedir } from 'node:os'
import { resolve } from 'node:path'
import type { Layout } from '../store/layout.js'
import { readJson, writeJson, appendJsonl } from '../store/io.js'
import type { Logger } from '../logger/logger.js'
import type { ImprintRecord } from '../boot/types.js'
import { verifyDrift } from './integrity.js'
import { logHeartbeat, logCritical } from './chain.js'
import type { HeartbeatConfig } from './types.js'

const DEFAULT_HEARTBEAT: HeartbeatConfig = {
  cycleThreshold: 10,
  intervalSeconds: 300,
}

const FCP_DIR = resolve(homedir(), '.fcp')

export interface VitalCheckState {
  cyclesSinceCheck: number
  lastCheckTs: number      // Date.now()
  sessionId: string
  contextCriticalTriggered: boolean
}

export function createVitalCheckState(sessionId: string): VitalCheckState {
  return {
    cyclesSinceCheck: 0,
    lastCheckTs: Date.now(),
    sessionId,
    contextCriticalTriggered: false,
  }
}

export function tick(state: VitalCheckState): void {
  state.cyclesSinceCheck++
}

export async function loadHeartbeatConfig(layout: Layout): Promise<HeartbeatConfig> {
  if (!existsSync(layout.baseline)) return DEFAULT_HEARTBEAT
  try {
    const baseline = await readJson<{ heartbeat?: { cycle_threshold?: number; interval_seconds?: number } }>(layout.baseline)
    return {
      cycleThreshold: baseline.heartbeat?.cycle_threshold ?? DEFAULT_HEARTBEAT.cycleThreshold,
      intervalSeconds: baseline.heartbeat?.interval_seconds ?? DEFAULT_HEARTBEAT.intervalSeconds,
    }
  } catch {
    return DEFAULT_HEARTBEAT
  }
}

export function shouldRun(state: VitalCheckState, config: HeartbeatConfig): boolean {
  const cycleDue = state.cyclesSinceCheck >= config.cycleThreshold
  const timeDue = (Date.now() - state.lastCheckTs) >= config.intervalSeconds * 1000
  return cycleDue || timeDue
}

/**
 * Run all vital checks. Returns list of critical condition names raised.
 * Logs a HEARTBEAT entry to integrity chain.
 */
export async function runVitalChecks(
  layout: Layout,
  state: VitalCheckState,
  logger: Logger,
  opts: {
    tokensUsed: number
    contextWindow: number
    compactPct: number
    workspaceFocus: string | null
    profile: 'haca-core' | 'haca-evolve'
  },
): Promise<string[]> {
  const criticals: string[] = []

  // Check 1: Context budget
  const budget = await _checkContextBudget(layout, state, logger, opts.tokensUsed, opts.contextWindow, opts.compactPct)
  if (budget) criticals.push(budget)

  // Check 2: Workspace focus validation
  const focus = await _checkWorkspaceFocus(layout, logger, opts.workspaceFocus)
  if (focus) criticals.push(focus)

  // Check 3: Pre-session buffer overflow
  await _checkPresessionBuffer(layout, logger)

  // Check 4: Identity drift
  const drift = await _checkIdentityDrift(layout, logger, opts.profile)
  criticals.push(...drift)

  await logHeartbeat(layout, state.sessionId)
  await logger.info('sil', 'heartbeat', { sessionId: state.sessionId, criticals: criticals.length })

  // Reset counters
  state.cyclesSinceCheck = 0
  state.lastCheckTs = Date.now()

  return criticals
}

// ---------------------------------------------------------------------------
// Check 1 — Context budget
// ---------------------------------------------------------------------------
async function _checkContextBudget(
  layout: Layout,
  state: VitalCheckState,
  logger: Logger,
  tokensUsed: number,
  contextWindow: number,
  compactPct: number,
): Promise<string | null> {
  if (contextWindow <= 0) return null
  const pct = tokensUsed / contextWindow
  if (pct >= compactPct && !state.contextCriticalTriggered) {
    state.contextCriticalTriggered = true
    const detail = { tokensUsed, contextWindow, pct: Math.round(pct * 100) }
    await logCritical(layout, 'CONTEXT_BUDGET_CRITICAL', detail)
    await logger.warn('sil', 'context_budget_critical', detail)
    // Signal CPE to close session via inbox
    await appendJsonl(join(layout.inbox, `sil-compact-${Date.now()}.json`), {
      type: 'sil_compact_request',
      ts: new Date().toISOString(),
      reason: 'CONTEXT_BUDGET_CRITICAL',
      pct: Math.round(pct * 100),
    })
    return 'context_budget'
  }
  return null
}

// ---------------------------------------------------------------------------
// Check 2 — Workspace focus
// ---------------------------------------------------------------------------
async function _checkWorkspaceFocus(
  layout: Layout,
  logger: Logger,
  workspaceFocus: string | null,
): Promise<string | null> {
  if (!workspaceFocus) return null
  const abs = resolve(workspaceFocus)
  const entityRoot = resolve(layout.root)

  // Cannot be inside entity root
  if (abs.startsWith(entityRoot + '/') || abs === entityRoot) {
    const detail = { path: abs, entityRoot }
    await logCritical(layout, 'WORKSPACE_FOCUS_INSIDE_ENTITY', detail)
    await logger.warn('sil', 'workspace_focus_inside_entity', detail)
    return 'workspace_focus_inside_entity'
  }

  // Cannot be an ancestor of entity root
  if (entityRoot.startsWith(abs + '/')) {
    const detail = { path: abs, entityRoot }
    await logCritical(layout, 'WORKSPACE_FOCUS_ANCESTOR', detail)
    await logger.warn('sil', 'workspace_focus_ancestor', detail)
    return 'workspace_focus_ancestor'
  }

  // Cannot be inside ~/.fcp
  if (abs.startsWith(FCP_DIR + '/') || abs === FCP_DIR) {
    const detail = { path: abs }
    await logCritical(layout, 'WORKSPACE_FOCUS_INSIDE_FCP', detail)
    await logger.warn('sil', 'workspace_focus_inside_fcp', detail)
    return 'workspace_focus_inside_fcp'
  }

  return null
}

// ---------------------------------------------------------------------------
// Check 3 — Pre-session buffer
// ---------------------------------------------------------------------------
async function _checkPresessionBuffer(layout: Layout, logger: Logger): Promise<void> {
  if (!existsSync(layout.inboxPresession)) return
  try {
    const entries = await readdir(layout.inboxPresession)
    if (entries.length > 10) {
      await logger.warn('sil', 'presession_buffer_overflow', { count: entries.length })
      // Write notification to operator notifications
      const notifPath = join(layout.notifications, `sil-presession-overflow-${Date.now()}.json`)
      const { writeJson: wj } = await import('../store/io.js')
      await wj(notifPath, {
        type: 'PRESESSION_BUFFER_OVERFLOW',
        count: entries.length,
        ts: new Date().toISOString(),
      })
    }
  } catch {
    // non-critical
  }
}

// ---------------------------------------------------------------------------
// Check 4 — Identity drift
// ---------------------------------------------------------------------------
async function _checkIdentityDrift(
  layout: Layout,
  logger: Logger,
  profile: 'haca-core' | 'haca-evolve',
): Promise<string[]> {
  const drifts = await verifyDrift(layout)
  if (drifts.length === 0) return []

  const detail = { drifts, profile }
  await logCritical(layout, 'IDENTITY_DRIFT', detail)
  await logger.warn('sil', 'identity_drift', detail)

  if (profile === 'haca-core') {
    // Zero tolerance: activate distress beacon
    try {
      const { touchFile } = await import('../store/io.js')
      await touchFile(layout.distressBeacon)
      await logger.error('sil', 'distress_beacon_activated', { reason: 'IDENTITY_DRIFT', drifts })
    } catch {
      // best effort
    }
  }

  // Notify operator via notifications dir
  try {
    const notifPath = join(layout.notifications, `sil-drift-${Date.now()}.json`)
    const { writeJson: wj } = await import('../store/io.js')
    await wj(notifPath, {
      type: 'IDENTITY_DRIFT',
      drifts,
      profile,
      ts: new Date().toISOString(),
    })
  } catch {
    // best effort
  }

  return drifts.map(() => 'identity_drift')
}
