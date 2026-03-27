// Unit tests for the approval gate (resolveToolApproval).
import { describe, it, expect } from 'vitest'
import { resolveToolApproval } from '../../src/session/approval.js'
import type { GateIO } from '../../src/types/exec.js'

function makeIO(answer: string): GateIO & { written: string[] } {
  const written: string[] = []
  return {
    written,
    async prompt() { return answer },
    write(t) { written.push(t) },
  }
}

describe('session/approval — resolveToolApproval', () => {
  describe('mode: once-session-deny', () => {
    it('default (empty answer) grants one-time', async () => {
      const result = await resolveToolApproval('read outside workspace', 'once-session-deny', makeIO(''))
      expect(result.granted).toBe(true)
      if (result.granted) expect(result.tier).toBe('one-time')
    })

    it('"o" grants one-time', async () => {
      const result = await resolveToolApproval('read outside workspace', 'once-session-deny', makeIO('o'))
      expect(result.granted).toBe(true)
      if (result.granted) expect(result.tier).toBe('one-time')
    })

    it('"s" grants session', async () => {
      const result = await resolveToolApproval('read outside workspace', 'once-session-deny', makeIO('s'))
      expect(result.granted).toBe(true)
      if (result.granted) expect(result.tier).toBe('session')
    })

    it('"d" denies', async () => {
      const result = await resolveToolApproval('read outside workspace', 'once-session-deny', makeIO('d'))
      expect(result.granted).toBe(false)
    })

    it('"n" denies', async () => {
      const result = await resolveToolApproval('read outside workspace', 'once-session-deny', makeIO('n'))
      expect(result.granted).toBe(false)
    })

    it('"a" falls through to one-time (no allowlist option in this mode)', async () => {
      const result = await resolveToolApproval('read outside workspace', 'once-session-deny', makeIO('a'))
      expect(result.granted).toBe(true)
      if (result.granted) expect(result.tier).toBe('one-time')
    })

    it('writes prompt to io', async () => {
      const io = makeIO('o')
      await resolveToolApproval('read outside workspace', 'once-session-deny', io)
      expect(io.written.length).toBeGreaterThan(0)
      expect(io.written.some(w => w.includes('[o]'))).toBe(true)
      expect(io.written.some(w => w.includes('allowlist'))).toBe(false)
    })
  })

  describe('mode: once-session-allowlist-deny', () => {
    it('"a" grants persistent (add to allowlist)', async () => {
      const result = await resolveToolApproval('run command: git', 'once-session-allowlist-deny', makeIO('a'))
      expect(result.granted).toBe(true)
      if (result.granted) expect(result.tier).toBe('persistent')
    })

    it('"allowlist" also grants persistent', async () => {
      const result = await resolveToolApproval('run command: git', 'once-session-allowlist-deny', makeIO('allowlist'))
      expect(result.granted).toBe(true)
      if (result.granted) expect(result.tier).toBe('persistent')
    })

    it('"s" grants session', async () => {
      const result = await resolveToolApproval('run command: git', 'once-session-allowlist-deny', makeIO('s'))
      expect(result.granted).toBe(true)
      if (result.granted) expect(result.tier).toBe('session')
    })

    it('"d" denies', async () => {
      const result = await resolveToolApproval('run command: git', 'once-session-allowlist-deny', makeIO('d'))
      expect(result.granted).toBe(false)
    })

    it('prompt includes allowlist option', async () => {
      const io = makeIO('o')
      await resolveToolApproval('run command: git', 'once-session-allowlist-deny', io)
      expect(io.written.some(w => w.includes('allowlist'))).toBe(true)
    })
  })
})
