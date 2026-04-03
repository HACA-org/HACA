// SIL integrity verification — integrity doc drift detection + chain validation.
import * as path from 'node:path'
import * as fs from 'node:fs/promises'
import { fileExists, readJson, writeJson, appendJsonl } from '../store/io.js'
import {
  sha256Digest, sha256File, sha256Hex,
  getTrackedFiles, hashTrackedFiles,
} from '../boot/integrity.js'
import { readChain } from './chain.js'
import type { Layout } from '../types/store.js'
import { IntegrityDocumentSchema } from '../types/formats/integrity.js'
import { ImprintRecordSchema } from '../types/formats/baseline.js'

export interface DriftMismatch {
  readonly file:     string
  readonly reason:   'missing' | 'hash_mismatch' | 'untracked'
  readonly expected?: string
  readonly actual?:   string
}

export interface DriftResult {
  readonly clean:      boolean
  readonly mismatches: DriftMismatch[]
}

export interface ChainVerificationResult {
  readonly valid:  boolean
  readonly reason?: string
}

// ─── integrity.log ────────────────────────────────────────────────────────────
// Append-only JSONL audit log at state/integrity.log.
// Events: PROPOSAL_PENDING, EVOLUTION_AUTH, EVOLUTION_REJECTED, SLEEP_COMPLETE.

export type IntegrityLogEvent =
  | { event: 'PROPOSAL_PENDING'; id: string; digest: string; ts: string }
  | { event: 'EVOLUTION_AUTH';   id: string; digest: string; ts: string; autoApproved: boolean }
  | { event: 'EVOLUTION_REJECTED'; id: string; digest: string; ts: string; reason: string }
  | { event: 'SLEEP_COMPLETE';   ts: string; proposed: number; executed: number }

export async function appendIntegrityLog(layout: Layout, entry: IntegrityLogEvent): Promise<void> {
  await appendJsonl(layout.state.integrityLog, entry)
}

// Re-hash all tracked files and compare to state/integrity.json.
export async function verifyIntegrityDoc(layout: Layout): Promise<DriftResult> {
  if (!await fileExists(layout.state.integrity)) {
    return { clean: false, mismatches: [{ file: 'state/integrity.json', reason: 'missing' }] }
  }

  const raw = await readJson(layout.state.integrity)
  const doc = IntegrityDocumentSchema.parse(raw)

  const mismatches: DriftMismatch[] = []
  for (const [rel, expected] of Object.entries(doc.files)) {
    const abs = path.join(layout.root, rel)
    if (!await fileExists(abs)) {
      mismatches.push({ file: rel, reason: 'missing', expected })
      continue
    }
    const actual = await sha256File(abs)
    if (actual !== expected) {
      mismatches.push({ file: rel, reason: 'hash_mismatch', expected, actual })
    }
  }

  // Detect tracked files on disk that are NOT in the integrity doc.
  const tracked = await getTrackedFiles(layout)
  for (const rel of tracked) {
    if (!(rel in doc.files)) {
      mismatches.push({ file: rel, reason: 'untracked' })
    }
  }

  return { clean: mismatches.length === 0, mismatches }
}

// Update state/integrity.json with current file hashes.
export async function refreshIntegrityDoc(layout: Layout): Promise<string> {
  const tracked = await getTrackedFiles(layout)
  const files   = await hashTrackedFiles(layout, tracked)
  await writeJson(layout.state.integrity, { version: '1.0', algorithm: 'sha256', lastCheckpoint: null, files })
  const buf = await fs.readFile(layout.state.integrity)
  return sha256Digest(buf)
}

// Compute sha256 hashes of current tracked files as `sha256:` prefixed values.
export async function currentFileHashes(layout: Layout): Promise<Record<string, string>> {
  const tracked = await getTrackedFiles(layout)
  const hashes: Record<string, string> = {}
  for (const rel of tracked) {
    hashes[rel] = 'sha256:' + sha256Hex(await sha256File(path.join(layout.root, rel)))
  }
  return hashes
}

// Verify the genesis entry and every subsequent link in integrity-chain.jsonl.
// An empty chain (entity never evolved past FAP) is valid.
export async function verifyChainFromImprint(layout: Layout): Promise<ChainVerificationResult> {
  if (!await fileExists(layout.memory.imprint)) {
    return { valid: false, reason: 'memory/imprint.json not found' }
  }

  let imprintRaw: unknown
  try {
    imprintRaw = await readJson(layout.memory.imprint)
    ImprintRecordSchema.parse(imprintRaw)
  } catch {
    return { valid: false, reason: 'memory/imprint.json is malformed or unreadable' }
  }

  const chain = await readChain(layout)
  if (chain.length === 0) return { valid: true }

  // Rule 1: first entry must be genesis with matching imprint_hash
  const first = chain[0]!
  if (first.type !== 'genesis') {
    return { valid: false, reason: `first entry is not genesis (got ${first.type})` }
  }

  // Genesis imprintHash must match sha256Digest of the imprint file at activation time.
  // We store the hash in FAP step 7 — compare against what's in the genesis entry.
  // The structuralBaseline hash in imprint can serve as a cross-check anchor.
  // (We can't re-derive the original FAP imprint hash, so we verify internal chain linkage only.)
  const genesisImprintHash: string = (first as Record<string, unknown>)['imprintHash'] as string
  if (!genesisImprintHash || !genesisImprintHash.startsWith('sha256:')) {
    return { valid: false, reason: 'genesis entry has no valid imprintHash' }
  }

  // Rules 2: verify prevHash linkage for subsequent entries
  for (let i = 1; i < chain.length; i++) {
    const prev    = chain[i - 1]!
    const current = chain[i]!
    const expectedPrevHash = sha256Digest(JSON.stringify(prev))
    const actualPrevHash   = (current as Record<string, unknown>)['prevHash'] as string | undefined

    if (actualPrevHash !== expectedPrevHash) {
      return {
        valid:  false,
        reason: `chain broken at seq ${current.seq}: prevHash mismatch`,
      }
    }

    // Rule 3: ENDURE_COMMIT must have evolutionAuthDigest
    if (current.type === 'ENDURE_COMMIT' && !current.evolutionAuthDigest) {
      return {
        valid:  false,
        reason: `ENDURE_COMMIT at seq ${current.seq} missing evolutionAuthDigest`,
      }
    }
  }

  return { valid: true }
}
