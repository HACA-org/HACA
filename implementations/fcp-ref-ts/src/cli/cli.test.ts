// CLI unit tests — templates, dispatch command parsing.
import { describe, it, expect } from 'vitest'
import { makeBaselineJson } from './templates/baseline.js'
import { makeIntegrityDoc, personaIdentity, bootMd } from './templates/integrity.js'
import { buildProgram } from './dispatch.js'

// ─── Templates ────────────────────────────────────────────────────────────────

describe('CLI — makeBaselineJson', () => {
  it('generates a baseline with correct shape', () => {
    const b = makeBaselineJson({ topology: 'transparent', backend: 'anthropic:claude-opus-4-6', budgetTokens: 100000 })
    expect(b['version']).toBe('1.0')
    expect((b['cpe'] as Record<string, unknown>)['topology']).toBe('transparent')
    expect((b['cpe'] as Record<string, unknown>)['backend']).toBe('anthropic:claude-opus-4-6')
    expect((b['contextWindow'] as Record<string, unknown>)['budgetTokens']).toBe(100000)
  })

  it('sets drift threshold to 0 for transparent topology', () => {
    const b = makeBaselineJson({ topology: 'transparent', backend: 'anthropic:claude-opus-4-6', budgetTokens: 10000 })
    expect((b['drift'] as Record<string, unknown>)['threshold']).toBe(0.0)
  })

  it('sets drift threshold to 0.15 for opaque topology', () => {
    const b = makeBaselineJson({ topology: 'opaque', backend: 'anthropic:claude-opus-4-6', budgetTokens: 10000 })
    expect((b['drift'] as Record<string, unknown>)['threshold']).toBe(0.15)
  })

  it('accepts a custom entityId', () => {
    const b = makeBaselineJson({ entityId: 'my-entity', topology: 'transparent', backend: 'auto', budgetTokens: 1000 })
    expect(b['entityId']).toBe('my-entity')
  })
})

describe('CLI — makeIntegrityDoc', () => {
  it('returns a valid blank integrity document', () => {
    const doc = makeIntegrityDoc()
    expect(doc['version']).toBe('1.0')
    expect(doc['algorithm']).toBe('sha256')
    expect(doc['lastCheckpoint']).toBeNull()
    expect(doc['files']).toEqual({})
  })
})

describe('CLI — persona templates', () => {
  it('personaIdentity differs between core and evolve', () => {
    const core   = personaIdentity('haca-core')
    const evolve = personaIdentity('haca-evolve')
    expect(core).not.toBe(evolve)
    expect(core).toMatch(/HACA-Core/)
    expect(evolve).toMatch(/HACA-Evolve/)
  })

  it('bootMd includes tool names', () => {
    const md = bootMd()
    expect(md).toMatch(/fcp_file_read/)
    expect(md).toMatch(/fcp_web_fetch/)
    expect(md).toMatch(/fcp_skill_audit/)
  })
})

// ─── Program structure ────────────────────────────────────────────────────────

describe('CLI — buildProgram', () => {
  it('registers expected subcommands', () => {
    const program = buildProgram()
    const names   = program.commands.map(c => c.name())
    expect(names).toContain('init')
    expect(names).toContain('run')
    expect(names).toContain('status')
    expect(names).toContain('doctor')
  })

  it('program name is fcp', () => {
    const program = buildProgram()
    expect(program.name()).toBe('fcp')
  })
})
