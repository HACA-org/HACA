// Context budget tracking.
// Uses authoritative inputTokens from CPE response when available;
// falls back to heuristic estimation (length / 4).
import type { CPEMessage } from '../types/cpe.js'

export type BudgetStatus = 'ok' | 'warn' | 'critical'

export interface BudgetResult {
  readonly status:  BudgetStatus
  readonly usedPct: number
}

// Heuristic: ~4 chars per token. Only used before the first CPE response.
export function estimateTokens(messages: CPEMessage[]): number {
  let chars = 0
  for (const msg of messages) {
    chars += typeof msg.content === 'string'
      ? msg.content.length
      : JSON.stringify(msg.content).length
  }
  return Math.ceil(chars / 4)
}

// criticalPct is from baseline.context_window.critical_pct (0-100 integer).
// warn threshold is 10 percentage points below critical.
export function checkBudget(inputTokens: number, budgetTokens: number, criticalPct: number): BudgetResult {
  const usedPct = Math.round((inputTokens / budgetTokens) * 100)
  if (usedPct >= criticalPct)      return { status: 'critical', usedPct }
  if (usedPct >= criticalPct - 10) return { status: 'warn',     usedPct }
  return { status: 'ok', usedPct }
}
