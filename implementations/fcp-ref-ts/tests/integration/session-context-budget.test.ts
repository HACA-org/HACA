// Unit tests for budget tracking (estimateTokens, checkBudget).
import { describe, it, expect } from 'vitest'
import { estimateTokens, checkBudget } from '../../src/session/budget.js'
import type { CPEMessage } from '../../src/types/cpe.js'

describe('session/budget — estimateTokens', () => {
  it('returns 0 for empty message list', () => {
    expect(estimateTokens([])).toBe(0)
  })

  it('estimates tokens from string content (~4 chars/token)', () => {
    const msgs: CPEMessage[] = [{ role: 'user', content: 'abcd' }] // 4 chars → 1 token
    expect(estimateTokens(msgs)).toBe(1)
  })

  it('handles array content (tool blocks)', () => {
    const msgs: CPEMessage[] = [{
      role: 'assistant',
      content: [{ type: 'text', text: 'hello' }],
    }]
    const est = estimateTokens(msgs)
    expect(est).toBeGreaterThan(0)
  })

  it('sums across multiple messages', () => {
    const msgs: CPEMessage[] = [
      { role: 'user',      content: 'abcd' },  // 4 chars
      { role: 'assistant', content: 'efgh' },  // 4 chars
    ]
    expect(estimateTokens(msgs)).toBe(2)
  })
})

describe('session/budget — checkBudget', () => {
  const BUDGET = 10000
  const CRITICAL_PCT = 90

  it('returns ok when well below budget', () => {
    const result = checkBudget(1000, BUDGET, CRITICAL_PCT) // 10%
    expect(result.status).toBe('ok')
    expect(result.usedPct).toBe(10)
  })

  it('returns warn when within 10% of critical threshold', () => {
    const result = checkBudget(8100, BUDGET, CRITICAL_PCT) // 81%
    expect(result.status).toBe('warn')
  })

  it('returns critical at the critical threshold', () => {
    const result = checkBudget(9000, BUDGET, CRITICAL_PCT) // 90%
    expect(result.status).toBe('critical')
    expect(result.usedPct).toBe(90)
  })

  it('returns critical above the critical threshold', () => {
    const result = checkBudget(9500, BUDGET, CRITICAL_PCT) // 95%
    expect(result.status).toBe('critical')
  })

  it('usedPct is rounded', () => {
    const result = checkBudget(333, BUDGET, CRITICAL_PCT) // 3.33%
    expect(Number.isInteger(result.usedPct)).toBe(true)
  })
})
