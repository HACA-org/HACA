// Unit tests for the single approval gate (resolveToolApproval).
import { describe, it, expect, vi } from 'vitest'
import { resolveToolApproval } from '../../src/session/approval.js'
import type { AllowlistPolicy } from '../../src/types/exec.js'
import type { SessionIO, SessionEvent } from '../../src/types/session.js'

function makePolicy(allowed: boolean): AllowlistPolicy {
  return {
    isAllowed: () => allowed,
    grant: vi.fn(async () => undefined),
  }
}

function makeIO(answer: string): SessionIO & { written: string[] } {
  const written: string[] = []
  return {
    written,
    prompt:  async () => answer,
    write:   (t) => { written.push(t) },
    emit:    (_e: SessionEvent) => undefined,
  }
}

describe('session/approval — resolveToolApproval', () => {
  it('grants immediately when policy allows (persistent)', async () => {
    const result = await resolveToolApproval('fcp_exec', {}, makePolicy(true), makeIO(''))
    expect(result.granted).toBe(true)
    if (result.granted) expect(result.tier).toBe('persistent')
  })

  it('does not prompt when policy allows', async () => {
    const io = makeIO('')
    await resolveToolApproval('fcp_exec', {}, makePolicy(true), io)
    expect(io.written).toHaveLength(0)
  })

  it('prompts when policy does not allow', async () => {
    const io = makeIO('o')
    await resolveToolApproval('fcp_exec', {}, makePolicy(false), io)
    expect(io.written.length).toBeGreaterThan(0)
  })

  it('default (empty answer) grants one-time', async () => {
    const result = await resolveToolApproval('fcp_exec', {}, makePolicy(false), makeIO(''))
    expect(result.granted).toBe(true)
    if (result.granted) expect(result.tier).toBe('one-time')
  })

  it('"o" answer grants one-time', async () => {
    const result = await resolveToolApproval('fcp_exec', {}, makePolicy(false), makeIO('o'))
    expect(result.granted).toBe(true)
    if (result.granted) expect(result.tier).toBe('one-time')
  })

  it('"s" answer grants session and calls policy.grant', async () => {
    const policy = makePolicy(false)
    const result = await resolveToolApproval('fcp_exec', {}, policy, makeIO('s'))
    expect(result.granted).toBe(true)
    if (result.granted) expect(result.tier).toBe('session')
    expect(policy.grant).toHaveBeenCalledWith('fcp_exec', 'session')
  })

  it('"p" answer grants persistent and calls policy.grant', async () => {
    const policy = makePolicy(false)
    const result = await resolveToolApproval('fcp_exec', {}, policy, makeIO('p'))
    expect(result.granted).toBe(true)
    if (result.granted) expect(result.tier).toBe('persistent')
    expect(policy.grant).toHaveBeenCalledWith('fcp_exec', 'persistent')
  })

  it('"d" answer denies', async () => {
    const result = await resolveToolApproval('fcp_exec', {}, makePolicy(false), makeIO('d'))
    expect(result.granted).toBe(false)
  })

  it('"n" answer denies', async () => {
    const result = await resolveToolApproval('fcp_exec', {}, makePolicy(false), makeIO('n'))
    expect(result.granted).toBe(false)
  })
})
