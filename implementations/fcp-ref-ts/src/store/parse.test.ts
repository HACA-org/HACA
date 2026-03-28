import { describe, it, expect } from 'vitest'
import {
  parseBaseline, parseSessionToken, parseSkillIndex, parseSkillManifest,
  parseIntegrityDocument, parseIntegrityChainEntry, parseWorkingMemory,
  parseClosurePayload, parseAllowlistData, parseSemanticDigest,
  parseDriftProbe, parseSessionHandoff, ParseError,
} from './parse.js'

const validBaseline = {
  version:  '1.0',
  entityId: 'test-entity',
  cpe: { topology: 'transparent', backend: 'anthropic:claude-opus-4-6' },
  heartbeat:        { cycleThreshold: 10, intervalSeconds: 300 },
  watchdog:         { silThresholdSeconds: 300 },
  contextWindow:    { budgetTokens: 200000, criticalPct: 85, warnPct: 65 },
  drift:            { comparisonMechanism: 'ncd-gzip-v1', threshold: 0.15 },
  sessionStore:     { rotationThresholdBytes: 2097152 },
  workingMemory:    { maxEntries: 20 },
  integrityChain:   { checkpointInterval: 10 },
  preSessionBuffer: { maxEntries: 50 },
  operatorChannel:  { notificationsDir: 'state/operator-notifications/' },
  fault:            { nBoot: 3, nChannel: 3, nRetry: 3 },
}

describe('store/parse', () => {
  describe('ParseError', () => {
    it('throws ParseError (not returns {}) on invalid input', () => {
      let result: unknown = 'sentinel'
      try { parseBaseline(null) } catch { result = undefined }
      expect(result).toBeUndefined()
    })

    it('ParseError carries schema name', () => {
      let err: unknown
      try { parseBaseline({}) } catch (e: unknown) { err = e }
      expect(err).toBeInstanceOf(ParseError)
      expect((err as ParseError).schema).toBe('Baseline')
    })

    it('ParseError wraps non-ZodError as ParseError', () => {
      // A schema whose .parse() throws something other than ZodError
      const brokenSchema = { parse: () => { throw new TypeError('internal') } }
      const parse = (raw: unknown) => {
        try { return brokenSchema.parse() } catch (e) {
          if (e instanceof Error && e.name !== 'ZodError') {
            throw new ParseError('BrokenSchema', { errors: [{ code: 'custom', path: [], message: String(e) }] } as never)
          }
          throw e
        }
      }
      expect(() => parse(null)).toThrow(ParseError)
    })
  })

  describe('parseBaseline', () => {
    it('accepts valid baseline', () => {
      expect(() => parseBaseline(validBaseline)).not.toThrow()
    })

    it('rejects unknown topology', () => {
      const bad = { ...validBaseline, cpe: { topology: 'opaque-ish', backend: 'x:y' } }
      expect(() => parseBaseline(bad)).toThrow(ParseError)
    })

    it('rejects missing required field', () => {
      const { entityId: _, ...bad } = validBaseline
      expect(() => parseBaseline(bad)).toThrow(ParseError)
    })

    it('rejects null budgetTokens', () => {
      const bad = { ...validBaseline, contextWindow: { budgetTokens: null, criticalPct: 85, warnPct: 65 } }
      expect(() => parseBaseline(bad)).toThrow(ParseError)
    })
  })

  describe('parseSessionToken', () => {
    const uuid = 'f47ac10b-58cc-4372-a567-0e02b2c3d479'

    it('accepts active token (no revokedAt)', () => {
      const token = parseSessionToken({ sessionId: uuid, issuedAt: '2026-03-27T12:00:00Z' })
      expect(token.revokedAt).toBeUndefined()
    })

    it('accepts revoked token', () => {
      const token = parseSessionToken({
        sessionId: uuid,
        issuedAt:  '2026-03-27T12:00:00Z',
        revokedAt: '2026-03-27T14:00:00Z',
      })
      expect(token.revokedAt).toBeDefined()
    })

    it('rejects non-UUID sessionId', () => {
      expect(() => parseSessionToken({ sessionId: 'not-a-uuid', issuedAt: '2026-03-27T12:00:00Z' }))
        .toThrow(ParseError)
    })
  })

  describe('parseIntegrityDocument', () => {
    it('accepts valid doc with null checkpoint', () => {
      const doc = {
        version: '1.0',
        algorithm: 'sha256',
        lastCheckpoint: null,
        files: { 'boot.md': 'abc123' },
      }
      expect(() => parseIntegrityDocument(doc)).not.toThrow()
    })

    it('accepts doc with checkpoint', () => {
      const doc = {
        version: '1.0',
        algorithm: 'sha256',
        lastCheckpoint: { seq: 5, digest: 'sha256:abc' },
        files: {},
      }
      expect(() => parseIntegrityDocument(doc)).not.toThrow()
    })
  })

  describe('parseIntegrityChainEntry', () => {
    it('parses genesis entry', () => {
      const entry = {
        seq: 0, type: 'genesis', ts: '2026-03-27T12:00:00Z',
        imprintHash: 'sha256:abc', prevHash: null,
      }
      const parsed = parseIntegrityChainEntry(entry)
      expect(parsed.type).toBe('genesis')
    })

    it('parses ENDURE_COMMIT entry', () => {
      const entry = {
        seq: 1, type: 'ENDURE_COMMIT', ts: '2026-03-27T13:00:00Z',
        evolutionAuthDigest: 'sha256:auth',
        files: { 'boot.md': 'sha256:file' },
        integrityDocHash: 'sha256:doc',
        prevHash: 'sha256:prev',
      }
      expect(() => parseIntegrityChainEntry(entry)).not.toThrow()
    })

    it('rejects unknown type', () => {
      expect(() => parseIntegrityChainEntry({ type: 'UNKNOWN', seq: 1, ts: '2026-03-27T00:00:00Z' }))
        .toThrow(ParseError)
    })
  })

  describe('parseWorkingMemory', () => {
    it('accepts valid working memory', () => {
      const wm = {
        version: '1.0',
        entries: [
          { priority: 10, path: 'memory/episodic/x.jsonl' },
          { priority: 90, path: 'memory/session-handoff.json' },
        ],
      }
      expect(() => parseWorkingMemory(wm)).not.toThrow()
    })

    it('rejects priority < 1', () => {
      const wm = { version: '1.0', entries: [{ priority: 0, path: 'memory/x.jsonl' }] }
      expect(() => parseWorkingMemory(wm)).toThrow(ParseError)
    })
  })

  describe('parseSkillIndex', () => {
    it('accepts valid index', () => {
      const idx = {
        version: '1.0',
        skills: [{ name: 'file_reader', desc: 'reads files', manifest: 'file_reader/manifest.json', class: 'custom' }],
        aliases: {},
      }
      expect(() => parseSkillIndex(idx)).not.toThrow()
    })

    it('rejects empty object', () => {
      expect(() => parseSkillIndex({})).toThrow(ParseError)
    })
  })

  describe('parseSkillManifest', () => {
    it('accepts manifest with null ttlSeconds when background=false', () => {
      const m = {
        name: 'shell_run', class: 'custom', version: '1.0.0',
        description: 'runs shell commands', timeoutSeconds: 30,
        background: false, ttlSeconds: null, permissions: [], dependencies: [],
      }
      expect(() => parseSkillManifest(m)).not.toThrow()
    })
  })

  describe('parseClosurePayload', () => {
    it('accepts valid closure payload', () => {
      const cp = {
        type: 'closure_payload',
        consolidation: 'session summary',
        promotion: ['slug-1'],
        workingMemory: [{ priority: 1, path: 'memory/session-handoff.json' }],
        sessionHandoff: { pendingTasks: ['task A'], nextSteps: 'do X' },
      }
      expect(() => parseClosurePayload(cp)).not.toThrow()
    })

    it('rejects wrong type discriminant', () => {
      const cp = { type: 'wrong', consolidation: 'x', promotion: [], workingMemory: [], sessionHandoff: {} }
      expect(() => parseClosurePayload(cp)).toThrow(ParseError)
    })
  })

  describe('parseAllowlistData', () => {
    it('accepts valid 3-namespace structure', () => {
      expect(() => parseAllowlistData({
        commands: ['ls', 'echo'], domains: ['example.com'], skills: ['my_skill'],
      })).not.toThrow()
    })

    it('accepts empty arrays', () => {
      expect(() => parseAllowlistData({ commands: [], domains: [], skills: [] })).not.toThrow()
    })

    it('rejects old flat record format', () => {
      expect(() => parseAllowlistData({ fcp_file_read: true })).toThrow(ParseError)
    })

    it('rejects missing namespaces', () => {
      expect(() => parseAllowlistData({ commands: ['ls'] })).toThrow(ParseError)
    })

    it('rejects non-object', () => {
      expect(() => parseAllowlistData(null)).toThrow(ParseError)
    })
  })

  describe('parseSemanticDigest', () => {
    it('accepts valid digest', () => {
      const sd = {
        version: '1.0',
        lastUpdated: '2026-03-27T12:00:00Z',
        cyclesEvaluated: 5,
        probes: {
          'probe-1': { lastScore: 0.8, meanScore: 0.75, maxScore: 0.9 },
        },
      }
      expect(() => parseSemanticDigest(sd)).not.toThrow()
    })

    it('accepts empty probes', () => {
      const sd = { version: '1.0', lastUpdated: '2026-03-27T12:00:00Z', cyclesEvaluated: 0, probes: {} }
      expect(() => parseSemanticDigest(sd)).not.toThrow()
    })

    it('rejects score out of range', () => {
      const sd = {
        version: '1.0', lastUpdated: '2026-03-27T12:00:00Z', cyclesEvaluated: 1,
        probes: { 'p': { lastScore: 1.5, meanScore: 0.5, maxScore: 0.9 } },
      }
      expect(() => parseSemanticDigest(sd)).toThrow(ParseError)
    })
  })

  describe('parseDriftProbe', () => {
    it('accepts probe with null deterministic and null reference', () => {
      const probe = {
        id: 'probe-1',
        description: 'checks identity drift',
        target: 'memory/semantic/identity.md',
        deterministic: null,
        reference: null,
      }
      expect(() => parseDriftProbe(probe)).not.toThrow()
    })

    it('accepts probe with hash deterministic layer', () => {
      const probe = {
        id: 'probe-2',
        description: 'hash check',
        target: 'memory/semantic/values.md',
        deterministic: { type: 'hash', value: 'sha256:abc123' },
        reference: null,
      }
      expect(() => parseDriftProbe(probe)).not.toThrow()
    })

    it('rejects target not starting with memory/', () => {
      const probe = {
        id: 'probe-3', description: 'bad', target: 'state/baseline.json',
        deterministic: null, reference: null,
      }
      expect(() => parseDriftProbe(probe)).toThrow(ParseError)
    })
  })

  describe('parseSessionHandoff', () => {
    it('accepts valid handoff file', () => {
      const h = { pendingTasks: ['task A'], nextSteps: 'continue X' }
      expect(() => parseSessionHandoff(h)).not.toThrow()
    })

    it('accepts empty pendingTasks', () => {
      const h = { pendingTasks: [], nextSteps: '' }
      expect(() => parseSessionHandoff(h)).not.toThrow()
    })

    it('rejects missing nextSteps', () => {
      expect(() => parseSessionHandoff({ pendingTasks: [] })).toThrow(ParseError)
    })
  })
})
