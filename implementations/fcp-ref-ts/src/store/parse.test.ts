import { describe, it, expect } from 'vitest'
import {
  parseBaseline, parseSessionToken, parseSkillIndex, parseSkillManifest,
  parseIntegrityDocument, parseIntegrityChainEntry, parseWorkingMemory,
  parseClosurePayload, ParseError,
} from './parse.js'

const validBaseline = {
  version: '1.0',
  entity_id: 'test-entity',
  cpe: { topology: 'transparent', backend: 'anthropic:claude-opus-4-6' },
  heartbeat: { cycle_threshold: 10, interval_seconds: 300 },
  watchdog: { sil_threshold_seconds: 300 },
  context_window: { budget_tokens: 200000, critical_pct: 85 },
  drift: { comparison_mechanism: 'ncd-gzip-v1', threshold: 0.15 },
  session_store: { rotation_threshold_bytes: 2097152 },
  working_memory: { max_entries: 20 },
  integrity_chain: { checkpoint_interval: 10 },
  pre_session_buffer: { max_entries: 50 },
  operator_channel: { notifications_dir: 'state/operator_notifications/' },
  fault: { n_boot: 3, n_channel: 3, n_retry: 3 },
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
      const { entity_id: _, ...bad } = validBaseline
      expect(() => parseBaseline(bad)).toThrow(ParseError)
    })

    it('rejects null budget_tokens', () => {
      const bad = { ...validBaseline, context_window: { budget_tokens: null, critical_pct: 85 } }
      expect(() => parseBaseline(bad)).toThrow(ParseError)
    })
  })

  describe('parseSessionToken', () => {
    const uuid = 'f47ac10b-58cc-4372-a567-0e02b2c3d479'

    it('accepts active token (no revoked_at)', () => {
      const token = parseSessionToken({ session_id: uuid, issued_at: '2026-03-27T12:00:00Z' })
      expect(token.revoked_at).toBeUndefined()
    })

    it('accepts revoked token', () => {
      const token = parseSessionToken({
        session_id: uuid,
        issued_at:  '2026-03-27T12:00:00Z',
        revoked_at: '2026-03-27T14:00:00Z',
      })
      expect(token.revoked_at).toBeDefined()
    })

    it('rejects non-UUID session_id', () => {
      expect(() => parseSessionToken({ session_id: 'not-a-uuid', issued_at: '2026-03-27T12:00:00Z' }))
        .toThrow(ParseError)
    })
  })

  describe('parseIntegrityDocument', () => {
    it('accepts valid doc with null checkpoint', () => {
      const doc = {
        version: '1.0',
        algorithm: 'sha256',
        last_checkpoint: null,
        files: { 'boot.md': 'abc123' },
      }
      expect(() => parseIntegrityDocument(doc)).not.toThrow()
    })

    it('accepts doc with checkpoint', () => {
      const doc = {
        version: '1.0',
        algorithm: 'sha256',
        last_checkpoint: { seq: 5, digest: 'sha256:abc' },
        files: {},
      }
      expect(() => parseIntegrityDocument(doc)).not.toThrow()
    })
  })

  describe('parseIntegrityChainEntry', () => {
    it('parses genesis entry', () => {
      const entry = {
        seq: 0, type: 'genesis', ts: '2026-03-27T12:00:00Z',
        imprint_hash: 'sha256:abc', prev_hash: null,
      }
      const parsed = parseIntegrityChainEntry(entry)
      expect(parsed.type).toBe('genesis')
    })

    it('parses ENDURE_COMMIT entry', () => {
      const entry = {
        seq: 1, type: 'ENDURE_COMMIT', ts: '2026-03-27T13:00:00Z',
        evolution_auth_digest: 'sha256:auth',
        files: { 'boot.md': 'sha256:file' },
        integrity_doc_hash: 'sha256:doc',
        prev_hash: 'sha256:prev',
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
        skills: [{ name: 'file_reader', desc: 'reads files', manifest: 'skills/lib/file_reader/manifest.json', class: 'builtin' }],
        aliases: {},
      }
      expect(() => parseSkillIndex(idx)).not.toThrow()
    })

    it('rejects empty object', () => {
      expect(() => parseSkillIndex({})).toThrow(ParseError)
    })
  })

  describe('parseSkillManifest', () => {
    it('accepts manifest with null ttl_seconds when background=false', () => {
      const m = {
        name: 'shell_run', class: 'builtin', version: '1.0.0',
        description: 'runs shell commands', timeout_seconds: 30,
        background: false, ttl_seconds: null, permissions: [], dependencies: [],
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
        working_memory: [{ priority: 1, path: 'memory/session-handoff.json' }],
        session_handoff: { pending_tasks: ['task A'], next_steps: 'do X' },
      }
      expect(() => parseClosurePayload(cp)).not.toThrow()
    })

    it('rejects wrong type discriminant', () => {
      const cp = { type: 'wrong', consolidation: 'x', promotion: [], working_memory: [], session_handoff: {} }
      expect(() => parseClosurePayload(cp)).toThrow(ParseError)
    })
  })
})
