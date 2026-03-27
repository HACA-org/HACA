// Unit tests for fingerprint-based loop detection.
import { describe, it, expect } from 'vitest'
import { makeFingerprint } from '../../src/session/fingerprint.js'
import type { ToolUseBlock } from '../../src/types/cpe.js'

function tu(name: string, input: unknown): ToolUseBlock {
  return { type: 'tool_use', id: `id-${name}`, name, input }
}

describe('session/fingerprint — makeFingerprint', () => {
  it('returns a 16-char hex string', () => {
    const fp = makeFingerprint([tu('fcp_exec', { action: 'x' })])
    expect(fp).toMatch(/^[0-9a-f]{16}$/)
  })

  it('same tool calls produce the same fingerprint', () => {
    const calls = [tu('fcp_exec', { action: 'x' }), tu('file_read', { path: '/foo' })]
    expect(makeFingerprint(calls)).toBe(makeFingerprint(calls))
  })

  it('different tool names produce different fingerprints', () => {
    const fp1 = makeFingerprint([tu('tool_a', { x: 1 })])
    const fp2 = makeFingerprint([tu('tool_b', { x: 1 })])
    expect(fp1).not.toBe(fp2)
  })

  it('different inputs produce different fingerprints', () => {
    const fp1 = makeFingerprint([tu('fcp_exec', { action: 'a' })])
    const fp2 = makeFingerprint([tu('fcp_exec', { action: 'b' })])
    expect(fp1).not.toBe(fp2)
  })

  it('different tool order produces different fingerprints', () => {
    const fp1 = makeFingerprint([tu('tool_a', {}), tu('tool_b', {})])
    const fp2 = makeFingerprint([tu('tool_b', {}), tu('tool_a', {})])
    expect(fp1).not.toBe(fp2)
  })

  it('empty tool list always returns the same fingerprint', () => {
    expect(makeFingerprint([])).toBe(makeFingerprint([]))
  })

  it('loop is detectable via fingerprint array', () => {
    const calls = [tu('fcp_exec', { action: 'x' })]
    const fingerprints: string[] = []

    const fp1 = makeFingerprint(calls)
    expect(fingerprints.includes(fp1)).toBe(false)
    fingerprints.push(fp1)

    const fp2 = makeFingerprint(calls) // same calls = same fp
    expect(fingerprints.includes(fp2)).toBe(true) // loop detected
  })
})
